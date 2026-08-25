"""W38-A9-S2 — build Wave 24 released signal list."""

from __future__ import annotations

from agents_b2g.diagnostic.types import (
    CandidateRole,
    DiagnosticVerdict,
    DirectionId,
    ReleasedSignal,
    StageContext,
    SubagentResult,
)


class ReleasedPathBuilder:
    subagent_id = "W38-A9-S2"

    def run(self, ctx: StageContext, *, verdict: DiagnosticVerdict) -> SubagentResult:
        s_tau = ctx.stage_outputs.get("s_tau") or {}
        roles: dict[str, str] = ctx.stage_outputs.get("candidate_roles") or {}
        released: list[ReleasedSignal] = []
        for candidate_id, dirs in s_tau.items():
            role_name = roles.get(candidate_id, CandidateRole.CLEANSING_WORKER.value)
            if role_name == CandidateRole.INERT.value:
                continue
            for direction_key, value in dirs.items():
                released.append(
                    ReleasedSignal(
                        candidate_id=candidate_id,
                        direction=DirectionId(direction_key),
                        s_tau=float(value),
                        role=CandidateRole(role_name),
                    )
                )
        ctx.stage_outputs["released_signals"] = tuple(released)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_released": len(released), "verdict": verdict.value},
            artifacts=({"type": "released_signals", "count": len(released)},),
        )
