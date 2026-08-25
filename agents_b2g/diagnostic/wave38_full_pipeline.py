"""Wave 38 full fixture E2E: stages 1→9 (Capture + Analysis + Envelope).

Never --live. Composes CaptureAssemble (1–5) + Wave38AnalysisPipeline (6–9).
"""

from __future__ import annotations

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds, load_wave38_thresholds
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput
from agents_b2g.diagnostic.wave38_analysis_pipeline import Wave38AnalysisPipeline
from agents_b2g.diagnostic.wave38_capture_pipeline import (
    CaptureAssembleSuccess,
    Wave38CaptureToCTEPipeline,
)

# Envelope contract keys (Agent 9 DiagnosticSignalEnvelope.to_dict)
ENVELOPE_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "verdict",
        "gate_action",
        "s_tau",
        "fdr_status",
        "collapse_info",
        "released_signals",
        "blocked_signals",
        "cause",
        "run_id",
        "seed",
        "prereg_version",
    }
)


class Wave38FullPipeline:
    """Fixture E2E 1→9 — last integration gate before Live-Pre-Reg finalization."""

    def __init__(self, user_id: str = "wave38_full"):
        self.user_id = user_id
        self.capture = Wave38CaptureToCTEPipeline(user_id)
        self.analysis = Wave38AnalysisPipeline(user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)

    def run_stages_1_to_9(
        self,
        *,
        job_id: str = "e2e-1-9",
        seed: int | None = None,
        n_bins: int = 128,
        window_start_ts: int = 1_700_000_000,
        thresholds: Wave38Thresholds | None = None,
        run_input: DiagnosticRunInput | None = None,
    ) -> AgentEnvelope:
        thresholds = thresholds or load_wave38_thresholds()
        seed = seed if seed is not None else thresholds.seed_default

        captured = self.capture.run_capture_1_to_5(
            job_id=job_id,
            seed=seed,
            n_bins=n_bins,
            window_start_ts=window_start_ts,
            thresholds=thresholds,
            run_input=run_input,
            forbid_live=True,
        )
        if not isinstance(captured, CaptureAssembleSuccess):
            return captured

        analysis_input: DiagnosticRunInput = {
            "run_id": job_id,
            "user_id": self.user_id,
            "options": {
                "fixture": True,
                "seed": captured.seed,
                "live": False,
                "prereg_version": "WAVE38_LIVE_PREREG.md",
            },
        }
        gate = self.analysis.run_stages_6_7_8_9(
            captured.bundle,
            job_id=job_id,
            thresholds=thresholds,
            run_input=analysis_input,
            seed=captured.seed,
        )
        if gate["status"] != "completed":
            return make_response(
                "failed",
                job_id,
                error=f"Analysis 6→9 failed: {gate.get('error')}",
                artifacts=gate.get("artifacts") or [],
            )

        # Reference guard across full 1→9 chain
        guard_fail = self.capture._assert_reference_guard(
            captured.ref_hashes_before, job_id
        )
        if guard_fail is not None:
            return guard_fail

        env = gate["artifacts"][0]["metadata"]
        missing = ENVELOPE_REQUIRED_KEYS - set(env.keys())
        if missing:
            return make_response(
                "failed",
                job_id,
                error=f"Envelope contract missing keys: {sorted(missing)}",
            )

        if env.get("gate_action") == "BLOCKED" and env.get("cause") is None:
            return make_response(
                "failed",
                job_id,
                error="Envelope BLOCKED without cause",
            )
        if env.get("gate_action") == "RELEASED" and not env.get("s_tau"):
            return make_response(
                "failed",
                job_id,
                error="Envelope RELEASED without s_tau payload",
            )

        pipe = env.get("pipeline") or {}
        resampling_fragment = pipe.get("resampling_fragment")
        if resampling_fragment not in ("KFOLD_STABLE", "KFOLD_UNSTABLE"):
            return make_response(
                "failed",
                job_id,
                error=f"missing/invalid resampling_fragment: {resampling_fragment!r}",
            )

        verdict = env.get("verdict")
        if verdict not in (
            "DIAG_SIGNAL_VALID",
            "DIAG_FILTER_ARTIFACT",
            "DIAG_INCONCLUSIVE",
        ):
            return make_response(
                "failed",
                job_id,
                error=f"invalid verdict: {verdict!r}",
            )

        # Thresholds from Live Pre-Reg must be present on analysis path
        th_meta = pipe.get("thresholds") or {}
        if "RHO_SPEARMAN_MIN" not in th_meta or float(th_meta["RHO_SPEARMAN_MIN"]) < 0.90:
            return make_response(
                "failed",
                job_id,
                error="Live Pre-Reg RHO_SPEARMAN_MIN not applied (≥0.90 required)",
            )
        if "N_UNSTABLE_FOLDS_MAX" not in th_meta:
            return make_response(
                "failed",
                job_id,
                error="N_UNSTABLE_FOLDS_MAX missing from pipeline thresholds",
            )

        meta = {
            "pipeline": "1→9",
            "fixture_mode": True,
            "live": False,
            "seed": captured.seed,
            "n_bins": captured.n_bins,
            "raw_db_path": captured.raw_db_path,
            "captures": {
                k: {
                    "status": v.status,
                    "occupancy_path": v.occupancy_path,
                    "n_events": v.metadata.get("n_events")
                    or v.metadata.get("n_occupied"),
                }
                for k, v in captured.captures.items()
            },
            "format_ok": captured.format_ok,
            "bundle_source": captured.bundle.source,
            "bundle_candidates": list(captured.bundle.candidate_ids),
            "z_neu_occupied": {
                cid: sum(captured.bundle.z_neu_occ[cid])
                for cid in captured.bundle.candidate_ids
            },
            "envelope": env,
            "analysis_pipeline": pipe,
            "resampling_fragment": resampling_fragment,
            "rho_min": pipe.get("rho_min"),
            "perm_fragment": pipe.get("perm_fragment"),
            "verdict": verdict,
            "gate_action": env.get("gate_action"),
            "reference_guard_unchanged": True,
            "reference_write_blocked": True,
            "stages": [
                "1_ingestion",
                "2_oracle",
                "3_mev",
                "4_liquidations",
                "5_intent_stable",
                "6_cte",
                "7_resampling",
                "8_prereg",
                "9_gatekeeper",
            ],
        }
        return make_response(
            "completed",
            job_id,
            artifacts=[{"type": "e2e_1_to_9", "format": "json", "metadata": meta}],
            logs=[
                f"seed={captured.seed}",
                f"verdict={verdict}",
                f"gate_action={env.get('gate_action')}",
                f"resampling_fragment={resampling_fragment}",
            ],
        )


__all__ = [
    "ENVELOPE_REQUIRED_KEYS",
    "Wave38FullPipeline",
]
