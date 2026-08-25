"""W38-A9-S3 — build Wave 28 blocked signal list (cause required)."""

from __future__ import annotations

from agents_b2g.diagnostic.types import (
    BlockCause,
    BlockedSignal,
    DiagnosticVerdict,
    DirectionId,
    GateAction,
    StageContext,
    SubagentResult,
)


class BlockedPathBuilder:
    subagent_id = "W38-A9-S3"

    def run(
        self,
        ctx: StageContext,
        *,
        verdict: DiagnosticVerdict,
        gate_action: GateAction,
        cause: BlockCause | None,
    ) -> SubagentResult:
        if gate_action != GateAction.BLOCKED:
            ctx.stage_outputs["blocked_signals"] = ()
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="skipped",
                metrics={"gate_action": gate_action.value},
            )
        if cause is None:
            return SubagentResult(
                subagent_id=self.subagent_id,
                status="failed",
                error="BLOCKED requires cause",
            )

        s_tau = ctx.stage_outputs.get("s_tau") or {}
        perm_fail: list[str] = list(ctx.stage_outputs.get("perm_fail_candidates") or [])
        blocked: list[BlockedSignal] = []

        if cause == BlockCause.FILTER_ARTIFACT and perm_fail:
            for candidate_id in perm_fail:
                for direction_key in ("ab", "ba"):
                    blocked.append(
                        BlockedSignal(
                            candidate_id=candidate_id,
                            direction=DirectionId(direction_key),
                            cause=cause,
                            detail=f"perm_fail on {candidate_id}",
                        )
                    )
        elif s_tau:
            first = next(iter(s_tau))
            blocked.append(
                BlockedSignal(
                    candidate_id=first,
                    direction=DirectionId.AB,
                    cause=cause,
                    detail=f"verdict={verdict.value}",
                )
            )
        else:
            blocked.append(
                BlockedSignal(
                    candidate_id="_aggregate",
                    direction=DirectionId.AB,
                    cause=cause,
                    detail=f"verdict={verdict.value}",
                )
            )

        ctx.stage_outputs["blocked_signals"] = tuple(blocked)
        return SubagentResult(
            subagent_id=self.subagent_id,
            status="ok",
            metrics={"n_blocked": len(blocked), "cause": cause.value},
            artifacts=({"type": "blocked_signals", "count": len(blocked)},),
        )
