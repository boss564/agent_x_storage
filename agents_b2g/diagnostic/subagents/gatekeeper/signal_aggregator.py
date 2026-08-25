"""W38-A9-S1 — aggregate S(tau) per candidate and direction."""

from __future__ import annotations

from typing import Mapping

from agents_b2g.diagnostic.types import StageContext, SubagentResult


class SignalAggregator:
    subagent_id = "W38-A9-S1"

    def run(
        self,
        ctx: StageContext,
        *,
        cte_by_candidate: Mapping[str, Mapping[str, float]] | None = None,
    ) -> SubagentResult:
        source = cte_by_candidate or ctx.stage_outputs.get("s_tau_input") or {}
        if not source:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="missing cte_by_candidate / s_tau_input",
            )
        aggregated = {
            candidate: {"ab": float(dirs.get("ab", 0.0)), "ba": float(dirs.get("ba", 0.0))}
            for candidate, dirs in source.items()
        }
        ctx.stage_outputs["s_tau"] = aggregated
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_candidates": len(aggregated)},
            artifacts=({"type": "s_tau", "data": aggregated},),
        )
