"""Wave 38 Capture→CTE E2E: stages 1→2→3→4→5→6 on fixture data (no --live).

Assembles OccupancyBundle from capture archives for Agent 6.
Bridge ETH/Gnosis + Z_alt are fixture-synthesized (required CTE baseline;
not produced by Agents 2–5). Intent Agent 5 OR series is split by family into
intent_relayers + stablecoin_mint_burn for the CTE candidate set.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import CANDIDATE_IDS, DiagnosticConfig
from agents_b2g.diagnostic.cte_entropy_engine_agent import CTEEntropyEngineAgent
from agents_b2g.diagnostic.cte_math import OccupancyBundle
from agents_b2g.diagnostic.data_ingestion_agent import DataIngestionAgent
from agents_b2g.diagnostic.intent_and_stablecoin_agent import IntentAndStablecoinAgent
from agents_b2g.diagnostic.intent_stable_lib import minute_index as is_minute_index
from agents_b2g.diagnostic.liquidation_cascade_agent import LiquidationCascadeAgent
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds, load_wave38_thresholds
from agents_b2g.diagnostic.mev_capture_agent import MEVCaptureAgent
from agents_b2g.diagnostic.oracle_signal_agent import OracleSignalAgent
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ReferenceWriteForbiddenError,
    ensure_live_directory,
)
from agents_b2g.diagnostic.subagents.data_ingestion import IngestionConfig
from agents_b2g.diagnostic.subagents.intent_stable_capture import IntentStableConfig
from agents_b2g.diagnostic.subagents.liquidation_capture import LiquidationConfig
from agents_b2g.diagnostic.subagents.mev_capture import MEVConfig
from agents_b2g.diagnostic.subagents.oracle_capture import OracleConfig
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput, StageContext

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_v3_pipeline import encode_z_neu_tertile  # noqa: E402

# Format contract: every capture archiver must emit these keys for Agent 6
OCCUPANCY_ARCHIVE_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"candidate_id", "occupancy", "n_bins", "occupancy_rate"}
)


@dataclass(frozen=True)
class CaptureStageResult:
    stage: str
    status: str
    metadata: dict[str, Any]
    occupancy_path: str | None = None


@dataclass(frozen=True)
class CaptureAssembleSuccess:
    """Successful Agents 1–5 + OccupancyBundle assembly (no CTE yet)."""

    bundle: OccupancyBundle
    captures: dict[str, CaptureStageResult]
    raw_db_path: str
    live_root: Path
    ref_hashes_before: dict[str, str]
    format_ok: dict[str, bool]
    seed: int
    n_bins: int
    run_input: DiagnosticRunInput


def load_occupancy_archive(path: Path | str) -> dict[str, Any]:
    """Load dense occupancy JSON; validate Agent-6 format contract."""
    p = Path(path)
    body = json.loads(p.read_text(encoding="utf-8"))
    missing = OCCUPANCY_ARCHIVE_REQUIRED_KEYS - set(body.keys())
    if missing:
        raise ValueError(f"occupancy archive {p} missing keys: {sorted(missing)}")
    occ = body["occupancy"]
    if not isinstance(occ, list) or not occ:
        raise ValueError(f"occupancy archive {p} has empty occupancy")
    if int(body["n_bins"]) != len(occ):
        raise ValueError(
            f"occupancy archive {p}: n_bins={body['n_bins']} != len(occupancy)={len(occ)}"
        )
    if any(int(x) not in (0, 1) for x in occ):
        raise ValueError(f"occupancy archive {p}: non-binary values")
    return body


def make_fixture_bridge_and_alt(
    n_bins: int, seed: int
) -> tuple[list[int], list[int], list[list[int]]]:
    """Deterministic bridge X/Y + Z_alt drivers for fixture CTE (not Bridge JSONs)."""
    rng = random.Random(seed)
    eth = [1 if rng.random() > 0.55 else 0 for _ in range(n_bins)]
    gno = [1 if rng.random() > 0.60 else 0 for _ in range(n_bins)]
    z_alt = [[rng.randint(0, 2) for _ in range(n_bins)] for _ in range(3)]
    return eth, gno, z_alt


def occupancy_from_events_by_family(
    events: list[dict[str, Any]],
    family: str,
    *,
    n_bins: int,
    window_start_ts: int,
) -> list[int]:
    occ = [0] * n_bins
    for ev in events:
        if str(ev.get("family")) != family:
            continue
        idx = is_minute_index(int(ev.get("timestamp") or 0), window_start_ts, n_bins)
        if idx is not None:
            occ[idx] = 1
    return occ


def assemble_bundle_from_captures(
    captures: dict[str, CaptureStageResult],
    *,
    n_bins: int,
    window_start_ts: int,
    seed: int,
    source: str = "fixture_e2e",
) -> OccupancyBundle:
    """Map Agents 2–5 archives → OccupancyBundle for Agent 6."""
    required = ("chainlink", "mev_cluster", "liquidations", "intent_stablecoin")
    for key in required:
        if key not in captures or captures[key].status != "completed":
            raise ValueError(f"missing completed capture for {key}")

    z_neu_occ: dict[str, list[int]] = {}

    # Oracle / MEV / Liquidations — direct archive load
    for cid, stage_key in (
        ("chainlink", "chainlink"),
        ("mev_cluster", "mev_cluster"),
        ("liquidations", "liquidations"),
    ):
        path = captures[stage_key].occupancy_path
        if not path:
            raise ValueError(f"{cid}: occupancy_path missing")
        body = load_occupancy_archive(path)
        if body["candidate_id"] != cid:
            raise ValueError(
                f"{cid}: candidate_id mismatch {body['candidate_id']!r}"
            )
        occ = [int(x) for x in body["occupancy"]]
        if len(occ) != n_bins:
            # Pad / trim to pipeline n_bins (fixture agents share n_bins)
            if len(occ) < n_bins:
                occ = occ + [0] * (n_bins - len(occ))
            else:
                occ = occ[:n_bins]
        z_neu_occ[cid] = occ

    # Intent+Stablecoin: split OR archive events into two CTE candidates
    is_meta = captures["intent_stablecoin"].metadata
    events_path = is_meta.get("events_path")
    if not events_path or not Path(events_path).is_file():
        raise ValueError("intent_stablecoin events_path missing for family split")
    events: list[dict[str, Any]] = []
    with Path(events_path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    z_neu_occ["intent_relayers"] = occupancy_from_events_by_family(
        events, "intent_relayers", n_bins=n_bins, window_start_ts=window_start_ts
    )
    z_neu_occ["stablecoin_mint_burn"] = occupancy_from_events_by_family(
        events, "stablecoin_mint_burn", n_bins=n_bins, window_start_ts=window_start_ts
    )

    for cid in CANDIDATE_IDS:
        if cid not in z_neu_occ:
            raise ValueError(f"assembled bundle missing candidate {cid}")

    eth, gno, z_alt = make_fixture_bridge_and_alt(n_bins, seed)
    z_neu_ter = {cid: encode_z_neu_tertile(z_neu_occ[cid]) for cid in CANDIDATE_IDS}
    return OccupancyBundle(
        bridge_eth=eth,
        bridge_gnosis=gno,
        z_alt=z_alt,
        z_neu_occ=z_neu_occ,
        z_neu_ter=z_neu_ter,
        candidate_ids=CANDIDATE_IDS,
        source=source,
    )


class Wave38CaptureToCTEPipeline:
    """E2E stages 1→6 — fixture only; never --live."""

    def __init__(self, user_id: str = "wave38_e2e"):
        self.user_id = user_id
        self.ingestion = DataIngestionAgent(user_id)
        self.oracle = OracleSignalAgent(user_id)
        self.mev = MEVCaptureAgent(user_id)
        self.liq = LiquidationCascadeAgent(user_id)
        self.intent_stable = IntentAndStablecoinAgent(user_id)
        self.cte = CTEEntropyEngineAgent(user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)

    def run_capture_1_to_5(
        self,
        *,
        job_id: str = "e2e-capture",
        seed: int | None = None,
        n_bins: int = 128,
        window_start_ts: int = 1_700_000_000,
        thresholds: Wave38Thresholds | None = None,
        run_input: DiagnosticRunInput | None = None,
        forbid_live: bool = True,
    ) -> CaptureAssembleSuccess | AgentEnvelope:
        """Agents 1–5 + bundle assemble. Returns Success or failed AgentEnvelope."""
        thresholds = thresholds or load_wave38_thresholds()
        seed = seed if seed is not None else thresholds.seed_default
        run_input = run_input or {
            "run_id": job_id,
            "user_id": self.user_id,
            "options": {"fixture": True, "seed": seed, "live": False},
        }
        if forbid_live and bool((run_input.get("options") or {}).get("live")):
            return make_response(
                "failed",
                job_id,
                error="E2E forbids --live; finalize WAVE38_LIVE_PREREG first",
            )

        live_root = ensure_live_directory(DiagnosticConfig.DATA_ROOT, self.user_id)
        self.reference_guard.verify_unchanged()
        ref_hashes_before = self.reference_guard.compute_hashes()

        ing = self.ingestion.run(
            run_input,
            f"{job_id}-ing",
            fixture_mode=True,
            cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=4),
        )
        if ing["status"] != "completed":
            return make_response(
                "failed", job_id, error=f"Agent1 failed: {ing.get('error')}"
            )
        raw_db = ing["artifacts"][0]["metadata"]["raw_db_path"]

        captures: dict[str, CaptureStageResult] = {}

        def _capture(
            key: str,
            stage: str,
            result: AgentEnvelope,
            *,
            path_key: str = "occupancy_path",
        ) -> None:
            if result["status"] != "completed":
                raise RuntimeError(f"{stage} failed: {result.get('error')}")
            meta = result["artifacts"][0]["metadata"]
            captures[key] = CaptureStageResult(
                stage=stage,
                status="completed",
                metadata=meta,
                occupancy_path=meta.get(path_key),
            )

        try:
            _capture(
                "chainlink",
                "oracle",
                self.oracle.run(
                    run_input,
                    f"{job_id}-oracle",
                    raw_db_path=raw_db,
                    fixture_mode=True,
                    cfg=OracleConfig(
                        fixture_mode=True,
                        n_bins=n_bins,
                        window_start_ts=window_start_ts,
                        fixture_min_events=10,
                    ),
                ),
            )
            _capture(
                "mev_cluster",
                "mev",
                self.mev.run(
                    run_input,
                    f"{job_id}-mev",
                    raw_db_path=raw_db,
                    fixture_mode=True,
                    cfg=MEVConfig(
                        fixture_mode=True,
                        n_bins=n_bins,
                        window_start_ts=window_start_ts,
                        fixture_min_occupied=3,
                    ),
                ),
            )
            _capture(
                "liquidations",
                "liquidations",
                self.liq.run(
                    run_input,
                    f"{job_id}-liq",
                    raw_db_path=raw_db,
                    fixture_mode=True,
                    cfg=LiquidationConfig(
                        fixture_mode=True,
                        n_bins=n_bins,
                        window_start_ts=window_start_ts,
                        fixture_min_events=8,
                    ),
                ),
            )
            _capture(
                "intent_stablecoin",
                "intent_stable",
                self.intent_stable.run(
                    run_input,
                    f"{job_id}-is",
                    raw_db_path=raw_db,
                    fixture_mode=True,
                    cfg=IntentStableConfig(
                        fixture_mode=True,
                        n_bins=n_bins,
                        window_start_ts=window_start_ts,
                        fixture_min_events=8,
                    ),
                ),
            )
        except RuntimeError as exc:
            return make_response("failed", job_id, error=str(exc))

        format_ok: dict[str, bool] = {}
        for key, cap in captures.items():
            path = cap.occupancy_path
            if not path:
                return make_response(
                    "failed", job_id, error=f"{key}: missing occupancy_path"
                )
            try:
                load_occupancy_archive(path)
                format_ok[key] = True
            except ValueError as exc:
                return make_response(
                    "failed", job_id, error=f"format contract failed for {key}: {exc}"
                )

        bundle = assemble_bundle_from_captures(
            captures,
            n_bins=n_bins,
            window_start_ts=window_start_ts,
            seed=seed,
            source=f"fixture_e2e:{live_root}",
        )
        return CaptureAssembleSuccess(
            bundle=bundle,
            captures=captures,
            raw_db_path=raw_db,
            live_root=live_root,
            ref_hashes_before=ref_hashes_before,
            format_ok=format_ok,
            seed=seed,
            n_bins=n_bins,
            run_input=run_input,
        )

    def _assert_reference_guard(
        self, ref_hashes_before: dict[str, str], job_id: str
    ) -> AgentEnvelope | None:
        self.reference_guard.verify_unchanged()
        ref_hashes_after = self.reference_guard.compute_hashes()
        if ref_hashes_before != ref_hashes_after:
            return make_response(
                "failed",
                job_id,
                error="reference_guard: sealed artifact hashes changed during E2E",
            )
        sealed = next(
            (p for p in self.reference_guard.registered_paths if p.is_file()),
            None,
        )
        write_blocked = False
        if sealed is not None:
            try:
                self.reference_guard.assert_write_allowed(sealed)
            except ReferenceWriteForbiddenError:
                write_blocked = True
        if sealed is not None and not write_blocked:
            return make_response(
                "failed",
                job_id,
                error="reference_guard: write to sealed path was not blocked",
            )
        return None

    def run_stages_1_to_6(
        self,
        *,
        job_id: str = "e2e-1-6",
        seed: int | None = None,
        n_bins: int = 128,
        window_start_ts: int = 1_700_000_000,
        thresholds: Wave38Thresholds | None = None,
        run_input: DiagnosticRunInput | None = None,
    ) -> AgentEnvelope:
        thresholds = thresholds or load_wave38_thresholds()
        captured = self.run_capture_1_to_5(
            job_id=job_id,
            seed=seed,
            n_bins=n_bins,
            window_start_ts=window_start_ts,
            thresholds=thresholds,
            run_input=run_input,
        )
        if not isinstance(captured, CaptureAssembleSuccess):
            return captured

        bundle = captured.bundle
        ctx = StageContext(
            run_id=job_id,
            user_id=self.user_id,
            job_id=job_id,
            data_root=str(captured.live_root),
            seed=captured.seed,
            prereg_version="WAVE38_LIVE_PREREG.md",
            stage_outputs={
                "raw_db_path": captured.raw_db_path,
                "captures": {k: v.metadata for k, v in captured.captures.items()},
            },
        )

        cte_result = self.cte.run(ctx, bundle=bundle, thresholds=thresholds)
        if cte_result["status"] != "completed":
            return make_response(
                "failed",
                job_id,
                error=f"Agent6 failed: {cte_result.get('error')}",
            )

        guard_fail = self._assert_reference_guard(captured.ref_hashes_before, job_id)
        if guard_fail is not None:
            return guard_fail

        analysis = ctx.stage_outputs.get("cte_analysis")
        cte_payload = {
            "sum_cte_ref": getattr(analysis, "sum_cte_ref", None),
            "s_tau_by_candidate": getattr(analysis, "s_tau_by_candidate", None),
            "perm_fragment": getattr(analysis, "perm_fragment", None),
            "rel_loo_by_candidate": getattr(analysis, "rel_loo_by_candidate", None),
            "n_unclassified": getattr(analysis, "n_unclassified", None),
        }

        meta = {
            "pipeline": "1→6",
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
            "bundle_source": bundle.source,
            "bundle_candidates": list(bundle.candidate_ids),
            "z_neu_occupied": {
                cid: sum(bundle.z_neu_occ[cid]) for cid in bundle.candidate_ids
            },
            "cte": cte_payload,
            "reference_guard_unchanged": True,
            "reference_write_blocked": True,
        }
        return make_response(
            "completed",
            job_id,
            artifacts=[{"type": "e2e_1_to_6", "format": "json", "metadata": meta}],
            logs=[
                f"seed={captured.seed}",
                f"perm_fragment={cte_payload.get('perm_fragment')}",
                f"candidates={list(bundle.candidate_ids)}",
            ],
        )


__all__ = [
    "OCCUPANCY_ARCHIVE_REQUIRED_KEYS",
    "CaptureAssembleSuccess",
    "CaptureStageResult",
    "Wave38CaptureToCTEPipeline",
    "assemble_bundle_from_captures",
    "load_occupancy_archive",
    "make_fixture_bridge_and_alt",
]
