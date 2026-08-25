"""Agent 9 — GatekeeperDispatcherAgent (Wave 38 control plane)."""

from __future__ import annotations

import hashlib
from typing import Any

from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.ethical_boundary_hook import (
    EthicalOrchestratorProtocol,
    EthicalPreflightResult,
    resolve_final_gate,
    run_ethical_preflight,
    synthetic_fail_closed_envelope,
)
from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard
from agents_b2g.diagnostic.subagents.gatekeeper.blocked_path_builder import (
    BlockedPathBuilder,
)
from agents_b2g.diagnostic.subagents.gatekeeper.released_path_builder import (
    ReleasedPathBuilder,
)
from agents_b2g.diagnostic.subagents.gatekeeper.signal_aggregator import (
    SignalAggregator,
)
from agents_b2g.diagnostic.types import (
    AgentEnvelope,
    BlockCause,
    CollapseInfo,
    DiagnosticRunInput,
    DiagnosticVerdict,
    FDRResult,
    GateAction,
    StageContext,
    envelope_for_verdict,
    validate_signal_envelope,
)


class GatekeeperDispatcherAgent:
    """Stage 9 — sole external emitter of DiagnosticSignalEnvelope."""

    agent_name = "GatekeeperDispatcherAgent"

    def __init__(
        self,
        user_id: str = "wave38",
        *,
        ethical_orchestrator: EthicalOrchestratorProtocol | None = None,
    ):
        self.user_id = user_id
        self.logger = JSONLogger(self.agent_name, user_id)
        self.aggregator = SignalAggregator()
        self.released_builder = ReleasedPathBuilder()
        self.blocked_builder = BlockedPathBuilder()
        self.reference_guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
        self._ethical_orchestrator = ethical_orchestrator

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        *,
        verdict: DiagnosticVerdict | None = None,
        cause: BlockCause | None = None,
        cte_by_candidate: dict[str, dict[str, float]] | None = None,
        candidate_roles: dict[str, str] | None = None,
        perm_fail_candidates: list[str] | None = None,
    ) -> AgentEnvelope:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            run_input,
            job_id,
            verdict,
            cause,
            cte_by_candidate,
            candidate_roles,
            perm_fail_candidates,
        )

    def _run_inner(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        verdict: DiagnosticVerdict | None,
        cause: BlockCause | None,
        cte_by_candidate: dict[str, dict[str, float]] | None,
        candidate_roles: dict[str, str] | None,
        perm_fail_candidates: list[str] | None,
    ) -> AgentEnvelope:
        options = run_input.get("options") or {}
        if options.get("live"):
            try:
                from agents_b2g.diagnostic.live_prereg import (
                    LivePreRegNotBoundError,
                    load_wave38_thresholds,
                )

                load_wave38_thresholds()
            except LivePreRegNotBoundError as exc:
                return make_response(
                    "failed",
                    job_id,
                    error=(
                        "Live run blocked: WAVE38_LIVE_PREREG.md must exist and be "
                        f"marked bindend before --live ({exc})"
                    ),
                )
            except FileNotFoundError as exc:
                return make_response(
                    "failed",
                    job_id,
                    error=(
                        "Live run blocked: bind WAVE38_LIVE_PREREG.md before --live "
                        f"(expected {DiagnosticConfig.LIVE_PRE_REG}): {exc}"
                    ),
                )

        self.reference_guard.verify_unchanged()

        ctx = StageContext(
            run_id=run_input.get("run_id") or job_id,
            user_id=run_input.get("user_id") or self.user_id,
            job_id=job_id,
            data_root=str(DiagnosticConfig.wave38_live_root(self.user_id)),
            seed=int(options.get("seed", 0)),
            prereg_version=str(options.get("prereg_version", "skeleton")),
            live_pre_reg_hash=self._pre_reg_hash(),
            stage_outputs={
                "s_tau_input": cte_by_candidate or _default_skeleton_s_tau(),
                "candidate_roles": candidate_roles or _default_skeleton_roles(),
                "perm_fail_candidates": perm_fail_candidates or [],
            },
        )

        agg = self.aggregator.run(ctx)
        if agg.status == "failed":
            return make_response("failed", job_id, error=agg.error)

        methodical_verdict = verdict or DiagnosticVerdict.DIAG_SIGNAL_VALID
        methodical_cause = cause if methodical_verdict != DiagnosticVerdict.DIAG_SIGNAL_VALID else None

        ethical_preflight = self._run_ethical_preflight_if_injected(
            run_input,
            job_id,
            ctx.stage_outputs,
        )
        if ethical_preflight.should_block:
            resolved_verdict, resolved_cause, gate_action = resolve_final_gate(
                methodical_verdict=methodical_verdict,
                methodical_cause=methodical_cause,
                ethical=ethical_preflight,
            )
        else:
            resolved_verdict = methodical_verdict
            resolved_cause = methodical_cause
            gate_action = (
                GateAction.RELEASED
                if resolved_verdict == DiagnosticVerdict.DIAG_SIGNAL_VALID
                else GateAction.BLOCKED
            )

        if gate_action == GateAction.RELEASED:
            rel = self.released_builder.run(ctx, verdict=resolved_verdict)
            if rel.status == "failed":
                return make_response("failed", job_id, error=rel.error)
            self.blocked_builder.run(
                ctx,
                verdict=resolved_verdict,
                gate_action=gate_action,
                cause=None,
            )
        else:
            if resolved_cause is None:
                return make_response(
                    "failed",
                    job_id,
                    error="BLOCKED path requires explicit cause",
                )
            blk = self.blocked_builder.run(
                ctx,
                verdict=resolved_verdict,
                gate_action=gate_action,
                cause=resolved_cause,
            )
            if blk.status == "failed":
                return make_response("failed", job_id, error=blk.error)
            self.released_builder.run(ctx, verdict=resolved_verdict)

        envelope = self._build_envelope(
            ctx,
            verdict=resolved_verdict,
            cause=resolved_cause if gate_action == GateAction.BLOCKED else None,
        )
        violations = validate_signal_envelope(envelope)
        if violations:
            return make_response(
                "failed",
                job_id,
                error="; ".join(violations),
            )

        artifact_metadata = envelope.to_dict()
        # Always serialize Wave 39 outcome when present — CERTIFIED and BLOCKED alike.
        # Previously only attached on should_block, so live CERTIFIED runs left no markers.
        if ethical_preflight.ethical_envelope is not None:
            artifact_metadata["ethical_boundary"] = (
                ethical_preflight.ethical_envelope.to_dict()
            )
        elif ethical_preflight.fault_message:
            artifact_metadata["ethical_boundary"] = synthetic_fail_closed_envelope(
                job_id
            ).to_dict()
            artifact_metadata["ethical_boundary"]["fault_message"] = (
                ethical_preflight.fault_message
            )

        logs = [
            f"gate_action={envelope.gate_action.value}",
            f"verdict={envelope.verdict.value}",
        ]
        if ethical_preflight.ethical_envelope is not None:
            logs.append(
                f"ethical_boundary={ethical_preflight.ethical_envelope.status.value}"
            )
        elif self._ethical_orchestrator is None:
            logs.append("ethical_boundary=SKIPPED_NOT_INJECTED")
        elif ethical_preflight.fault_message:
            logs.append("ethical_boundary=PIPELINE_FAULT")

        return make_response(
            "completed",
            job_id,
            artifacts=[
                {
                    "type": "diagnostic_signal_envelope",
                    "format": "json",
                    "metadata": artifact_metadata,
                }
            ],
            logs=logs,
        )

    def _run_ethical_preflight_if_injected(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        stage_outputs: dict[str, Any],
    ) -> EthicalPreflightResult:
        if self._ethical_orchestrator is None:
            return EthicalPreflightResult(passed=True)
        return run_ethical_preflight(
            self._ethical_orchestrator,
            run_input=run_input,
            job_id=job_id,
            stage_outputs=stage_outputs,
        )

    def _build_envelope(
        self,
        ctx: StageContext,
        *,
        verdict: DiagnosticVerdict,
        cause: BlockCause | None,
    ):
        s_tau = ctx.stage_outputs.get("s_tau") or {}
        released = ctx.stage_outputs.get("released_signals") or ()
        blocked = ctx.stage_outputs.get("blocked_signals") or ()
        fdr = FDRResult(n_tests=310, q=0.05, n_rejected=0, passed=True)
        collapse = CollapseInfo(
            cleansing_workers=tuple(
                k
                for k, role in (ctx.stage_outputs.get("candidate_roles") or {}).items()
                if role == "cleansing_worker"
            ),
            inert_candidates=tuple(
                k
                for k, role in (ctx.stage_outputs.get("candidate_roles") or {}).items()
                if role == "inert"
            ),
        )
        ref_paths = tuple(
            str(p) for p in self.reference_guard.registered_paths if p.is_file()
        )
        return envelope_for_verdict(
            verdict=verdict,
            run_id=ctx.run_id,
            seed=ctx.seed,
            prereg_version=ctx.prereg_version,
            s_tau=s_tau,
            fdr_status=fdr,
            collapse_info=collapse,
            released_signals=tuple(released),
            blocked_signals=tuple(blocked),
            cause=cause,
            live_pre_reg_hash=ctx.live_pre_reg_hash,
            reference_only=ref_paths,
        )

    def _pre_reg_hash(self) -> str:
        path = DiagnosticConfig.LIVE_PRE_REG
        if not path.is_file():
            return ""
        digest = hashlib.sha3_256(path.read_bytes()).hexdigest()
        return digest[:32]


def _default_skeleton_s_tau() -> dict[str, dict[str, float]]:
    return {
        "chainlink": {"ab": 0.035686, "ba": 0.051061},
        "mev_cluster": {"ab": 0.033635, "ba": 0.047414},
        "liquidations": {"ab": 0.044338, "ba": 0.059771},
        "intent_relayers": {"ab": 0.047058, "ba": 0.063024},
        "stablecoin_mint_burn": {"ab": 0.047058, "ba": 0.063024},
    }


def _default_skeleton_roles() -> dict[str, str]:
    return {
        "chainlink": "cleansing_worker",
        "mev_cluster": "cleansing_worker",
        "liquidations": "cleansing_worker",
        "intent_relayers": "inert",
        "stablecoin_mint_burn": "inert",
    }
