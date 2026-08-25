"""Wave 38 × Wave 39 ethical boundary pre-flight hook.

Additive only: methodical verdict priority (Pre-Reg §6) stays unchanged unless
Wave 39 reports a violation. ETHICAL_BOUNDARY is prepended as highest gate cause.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Mapping, Protocol

from agents_b2g.diagnostic.types import BlockCause, DiagnosticVerdict, GateAction
from agents_b2g.ethical_boundary.types import (
    EthicalBoundaryEnvelope,
    EthicalVerdict,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


class EthicalOrchestratorProtocol(Protocol):
    """Injectable Wave 39 orchestrator — Gatekeeper must not instantiate its own."""

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        wave38_gate_context: Mapping[str, Any] | None = None,
    ) -> EthicalBoundaryEnvelope: ...


class GateCausePriority(IntEnum):
    """Lower value = higher priority (evaluated first)."""

    ETHICAL_BOUNDARY = 0
    UNCLASSIFIED = 1  # maps to INCONCLUSIVE / inert encoding
    PERM_FAIL = 2  # FILTER_ARTIFACT
    KFOLD_UNSTABLE = 3  # INCONCLUSIVE
    SIGNAL_VALID = 4  # RELEASED path


# Documented Wave 38 Pre-Reg §6 order (methodical only — unchanged by this module)
WAVE38_METHODICAL_PRIORITY: tuple[str, ...] = (
    "unclassified",
    "PERM_FAIL",
    "KFOLD_UNSTABLE",
    "SIGNAL_VALID",
)

_BLOCK_CAUSE_TO_PRIORITY: dict[BlockCause, GateCausePriority] = {
    BlockCause.ETHICAL_BOUNDARY: GateCausePriority.ETHICAL_BOUNDARY,
    BlockCause.INERT_ENCODING: GateCausePriority.UNCLASSIFIED,
    BlockCause.INCONCLUSIVE: GateCausePriority.KFOLD_UNSTABLE,
    BlockCause.FILTER_ARTIFACT: GateCausePriority.PERM_FAIL,
    BlockCause.FDR_FAIL: GateCausePriority.KFOLD_UNSTABLE,
    BlockCause.INFRA_DOMINATED: GateCausePriority.KFOLD_UNSTABLE,
    BlockCause.CENSORSHIP_DETECTED: GateCausePriority.KFOLD_UNSTABLE,
}


@dataclass(frozen=True)
class EthicalPreflightResult:
    """Outcome of ethical pre-flight — consumed by GatekeeperDispatcherAgent."""

    passed: bool
    ethical_envelope: EthicalBoundaryEnvelope | None = None
    fault_message: str | None = None

    @property
    def should_block(self) -> bool:
        return not self.passed


def gate_cause_priority(cause: BlockCause | None) -> GateCausePriority:
    if cause is None:
        return GateCausePriority.SIGNAL_VALID
    return _BLOCK_CAUSE_TO_PRIORITY.get(cause, GateCausePriority.KFOLD_UNSTABLE)


def resolve_final_gate(
    *,
    methodical_verdict: DiagnosticVerdict,
    methodical_cause: BlockCause | None,
    ethical: EthicalPreflightResult,
) -> tuple[DiagnosticVerdict, BlockCause | None, GateAction]:
    """Apply ETHICAL_BOUNDARY only when ethical pre-flight failed — else unchanged."""
    if not ethical.should_block:
        gate_action = (
            GateAction.RELEASED
            if methodical_verdict == DiagnosticVerdict.DIAG_SIGNAL_VALID
            else GateAction.BLOCKED
        )
        return methodical_verdict, methodical_cause, gate_action

    return (
        DiagnosticVerdict.DIAG_INCONCLUSIVE,
        BlockCause.ETHICAL_BOUNDARY,
        GateAction.BLOCKED,
    )


def ethical_beats_methodical(
    methodical_cause: BlockCause | None,
) -> bool:
    """True when ethical boundary must override any methodical RELEASED/BLOCKED."""
    return gate_cause_priority(BlockCause.ETHICAL_BOUNDARY) < gate_cause_priority(
        methodical_cause
    )


def build_preflight_payload(
    *,
    run_input: Mapping[str, Any],
    job_id: str,
    stage_outputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Payload for Wave 39 — must not mutate Wave 38 stage context."""
    payload: dict[str, Any] = {
        "run_input": dict(run_input),
        "job_id": job_id,
    }
    if stage_outputs:
        payload["wave38_stage_outputs"] = dict(stage_outputs)
    receiver = run_input.get("receiver_metadata") or run_input.get("metadata")
    if receiver:
        payload["receiver_metadata"] = dict(receiver)
    return payload


def run_ethical_preflight(
    orchestrator: EthicalOrchestratorProtocol,
    *,
    run_input: Mapping[str, Any],
    job_id: str,
    stage_outputs: Mapping[str, Any] | None = None,
) -> EthicalPreflightResult:
    """Run Wave 39 enforce — fail-closed on any fault."""
    payload = build_preflight_payload(
        run_input=run_input,
        job_id=job_id,
        stage_outputs=stage_outputs,
    )
    wave38_ctx = {
        "job_id": job_id,
        "user_id": run_input.get("user_id"),
        "options": run_input.get("options"),
    }
    try:
        envelope = orchestrator.enforce(
            payload,
            job_id=job_id,
            wave38_gate_context=wave38_ctx,
        )
    except Exception as exc:
        return EthicalPreflightResult(
            passed=False,
            ethical_envelope=None,
            fault_message=f"ethical preflight fault: {exc}",
        )

    if envelope.status == EthicalVerdict.CERTIFIED:
        return EthicalPreflightResult(passed=True, ethical_envelope=envelope)

    return EthicalPreflightResult(
        passed=False,
        ethical_envelope=envelope,
        fault_message=(
            f"ethical boundary {envelope.status.value}"
            if envelope.violations
            else f"ethical boundary {envelope.status.value}"
        ),
    )


def normalize_envelope_metadata_for_regression(metadata: Mapping[str, Any]) -> str:
    """Regression-only view of Gatekeeper metadata — NEVER use in production paths.

    Hard Wave-38×39 hook requirements (see ``docs/WAVE39_ETHICAL_BOUNDARY_SPEC.md`` §5.4):

    1. Additive, not overriding — methodical verdict priority unchanged on CERTIFIED
    2. Byte-identical methodical regression on compliance — compare via this helper
    3. Fail-closed on hook fault — Exception → BLOCKED, never RELEASED

    Production artifacts MUST retain ``ethical_boundary`` (CERTIFIED or BLOCKED) so
    the Vierfach-Sperre is GoBD-auditable. This function strips additive Wave-39
    markers and non-deterministic timestamps **only** for unit/regression compares
    of the Wave-38 methodical envelope. Calling it to write live results, EventBus
    payloads, or GoBD reports is a Charter violation.

    Context | ``ethical_boundary`` in metadata
    --------|--------------------------------
    Regression (this helper) | stripped before compare
    Production (Gatekeeper / live_result) | must be present
    """
    stripped = json.loads(json.dumps(metadata, sort_keys=True, default=str))
    stripped.pop("timestamp_utc", None)
    # Additive Wave-39 markers — methodical identity ignores them (regression only)
    stripped.pop("ethical_boundary", None)
    return json.dumps(stripped, sort_keys=True, separators=(",", ":"))


def synthetic_fail_closed_envelope(job_id: str) -> EthicalBoundaryEnvelope:
    """Minimal envelope when hook faults before orchestrator returns."""
    from agents_b2g.ethical_boundary.types import (
        ScopeFlag,
        SCOPE_DEFENSIVE,
        blocked_envelope,
        utc_now_iso,
    )

    scope = ScopeFlag(
        scope=SCOPE_DEFENSIVE,
        attached_at=utc_now_iso(),
        attached_by="EthicalBoundaryHook",
        content_hash="fail_closed",
    )
    return blocked_envelope(
        job_id=job_id,
        scope=scope,
        violations=(
            ViolationRecord(
                violation_type=ViolationType.PIPELINE_FAULT,
                severity=ViolationSeverity.critical(),
                source_agent="EthicalBoundaryHook",
                message="ethical preflight fail-closed",
            ),
        ),
    )
