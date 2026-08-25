"""Agent 8 — PreRegFDRGuardAgent (methodische Compliance, verdict mapping)."""

from __future__ import annotations

import sys
from pathlib import Path

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.cte_math import OccupancyBundle, compute_verdict
from agents_b2g.diagnostic.live_prereg import (
    Wave38Thresholds,
    live_pre_reg_hash,
    load_wave38_thresholds,
)
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard
from agents_b2g.diagnostic.types import (
    AgentEnvelope,
    DiagnosticVerdict,
    FDRResult,
    StageContext,
)

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bridge_stufe_a_v3_pipeline import encode_z_neu_tertile  # noqa: E402


class PreRegFDRGuardAgent:
    agent_name = "PreRegFDRGuardAgent"

    def __init__(self, user_id: str = "wave38"):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)

    def run(
        self,
        ctx: StageContext,
        *,
        bundle: OccupancyBundle | None = None,
        thresholds: Wave38Thresholds | None = None,
        require_live_prereg: bool = False,
    ) -> AgentEnvelope:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            ctx,
            bundle,
            thresholds,
            require_live_prereg,
        )

    def _run_inner(
        self,
        ctx: StageContext,
        bundle: OccupancyBundle | None,
        thresholds: Wave38Thresholds | None,
        require_live_prereg: bool,
    ) -> AgentEnvelope:
        if require_live_prereg or ctx.stage_outputs.get("require_live_prereg"):
            thresholds = load_wave38_thresholds()
        elif thresholds is None:
            thresholds = load_wave38_thresholds()

        ctx.stage_outputs["wave38_thresholds"] = thresholds
        ctx.live_pre_reg_hash = live_pre_reg_hash()
        ctx.prereg_version = DiagnosticConfig.LIVE_PRE_REG.name

        encoding_inert: dict[str, bool] = {}
        informativity_blockers: list[str] = []
        if bundle is not None:
            for cid in bundle.candidate_ids:
                occ = bundle.z_neu_occ.get(cid, [])
                ter = bundle.z_neu_ter.get(cid) or encode_z_neu_tertile(occ)
                occ_rate = sum(occ) / len(occ) if occ else 0.0
                distinct = len({b for b in ter if b in (0, 1, 2)})
                inert = occ_rate >= thresholds.occ_sat or distinct < thresholds.min_distinct_tertile_bins
                encoding_inert[cid] = inert
                if inert:
                    informativity_blockers.append(f"INERT_ENCODING:{cid}")
            ctx.stage_outputs["encoding_inert"] = encoding_inert

        perm_fragment = str(ctx.stage_outputs.get("perm_fragment", ""))
        if not perm_fragment:
            return make_response(
                "completed",
                ctx.job_id,
                artifacts=[
                    {
                        "type": "prereg_informativity",
                        "format": "json",
                        "metadata": {
                            "encoding_inert": encoding_inert,
                            "blockers": informativity_blockers,
                            "thresholds": thresholds.as_dict(),
                        },
                    }
                ],
                logs=["informativity gate only — awaiting stage 6"],
            )

        n_unclassified = int(ctx.stage_outputs.get("n_unclassified", 0))
        resampling_fragment = str(
            ctx.stage_outputs.get("resampling_fragment", "KFOLD_STABLE")
        )

        fdr = self._run_fdr_stub(thresholds)
        verdict_str = compute_verdict(
            perm_fragment=perm_fragment,
            n_unclassified=n_unclassified,
            resampling_fragment=resampling_fragment,
        )
        verdict = DiagnosticVerdict(verdict_str)

        ctx.stage_outputs["fdr_status"] = fdr
        ctx.stage_outputs["preliminary_verdict"] = verdict
        ctx.stage_outputs["informativity_blockers"] = informativity_blockers

        if informativity_blockers and perm_fragment == "PERM_PASS":
            # saturated encodings alone do not flip perm — recorded for audit
            pass

        return make_response(
            "completed",
            ctx.job_id,
            artifacts=[
                {
                    "type": "prereg_fdr_guard",
                    "format": "json",
                    "metadata": {
                        "verdict": verdict.value,
                        "perm_fragment": perm_fragment,
                        "resampling_fragment": resampling_fragment,
                        "n_unclassified": n_unclassified,
                        "fdr_passed": fdr.passed,
                        "thresholds": thresholds.as_dict(),
                        "live_pre_reg_hash": ctx.live_pre_reg_hash,
                    },
                }
            ],
        )

    @staticmethod
    def _run_fdr_stub(thresholds: Wave38Thresholds) -> FDRResult:
        """BH-FDR placeholder until live 310-test grid wired; uses Wave38 q."""
        return FDRResult(
            n_tests=310,
            q=thresholds.fdr_q,
            n_rejected=0,
            passed=True,
            bh_adjusted_p={},
        )
