"""Typed contracts for Wave 38 — Causal Audit & Signal Guard.

Frozen dataclasses define the Agent 9 output contract (DiagnosticSignalEnvelope).
Bridge study types remain for confirmatory/read-only paths.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Mapping, TypedDict


# ---------------------------------------------------------------------------
# Wave 38 — primary verdict & gate contracts
# ---------------------------------------------------------------------------


class DiagnosticVerdict(str, Enum):
    """Operative verdict taxonomy (Agent 9 output)."""

    DIAG_SIGNAL_VALID = "DIAG_SIGNAL_VALID"
    DIAG_FILTER_ARTIFACT = "DIAG_FILTER_ARTIFACT"
    DIAG_INCONCLUSIVE = "DIAG_INCONCLUSIVE"
    DIAG_OVERCONSERVATIVE = "DIAG_OVERCONSERVATIVE"
    DIAG_INFRA_DOMINATED = "DIAG_INFRA_DOMINATED"


class BlockCause(str, Enum):
    """Mandatory reason when gate_action == BLOCKED."""

    FILTER_ARTIFACT = "FILTER_ARTIFACT"
    INERT_ENCODING = "INERT_ENCODING"
    FDR_FAIL = "FDR_FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INFRA_DOMINATED = "INFRA_DOMINATED"
    CENSORSHIP_DETECTED = "CENSORSHIP_DETECTED"
    ETHICAL_BOUNDARY = "ETHICAL_BOUNDARY"  # Wave 39 — highest gate priority


class GateAction(str, Enum):
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"


class DirectionId(str, Enum):
    AB = "ab"
    BA = "ba"


class CandidateRole(str, Enum):
    INERT = "inert"
    CLEANSING_WORKER = "cleansing_worker"
    NEUTRAL = "neutral"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class FDRResult:
    n_tests: int
    q: float
    n_rejected: int
    passed: bool
    bh_adjusted_p: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_tests": self.n_tests,
            "q": self.q,
            "n_rejected": self.n_rejected,
            "passed": self.passed,
            "bh_adjusted_p": dict(self.bh_adjusted_p),
        }


@dataclass(frozen=True)
class CollapseInfo:
    perm_fail_candidates: tuple[str, ...] = ()
    perm_collapse_by_candidate: Mapping[str, float] = field(default_factory=dict)
    inert_candidates: tuple[str, ...] = ()
    cleansing_workers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "perm_fail_candidates": list(self.perm_fail_candidates),
            "perm_collapse_by_candidate": dict(self.perm_collapse_by_candidate),
            "inert_candidates": list(self.inert_candidates),
            "cleansing_workers": list(self.cleansing_workers),
        }


@dataclass(frozen=True)
class ReleasedSignal:
    candidate_id: str
    direction: DirectionId
    s_tau: float
    role: CandidateRole
    peak_lag_min: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "direction": self.direction.value,
            "s_tau": self.s_tau,
            "role": self.role.value,
            "peak_lag_min": self.peak_lag_min,
        }


@dataclass(frozen=True)
class BlockedSignal:
    candidate_id: str
    direction: DirectionId
    cause: BlockCause
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "direction": self.direction.value,
            "cause": self.cause.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DiagnosticSignalEnvelope:
    """Agent 9 output contract — must not degrade to a bare bool."""

    verdict: DiagnosticVerdict
    gate_action: GateAction
    s_tau: Mapping[str, Mapping[str, float]]
    fdr_status: FDRResult
    collapse_info: CollapseInfo
    released_signals: tuple[ReleasedSignal, ...]
    blocked_signals: tuple[BlockedSignal, ...]
    run_id: str
    seed: int
    prereg_version: str
    timestamp_utc: str
    cause: BlockCause | None = None
    live_pre_reg_hash: str = ""
    reference_only: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "gate_action": self.gate_action.value,
            "s_tau": {k: dict(v) for k, v in self.s_tau.items()},
            "fdr_status": self.fdr_status.to_dict(),
            "collapse_info": self.collapse_info.to_dict(),
            "released_signals": [s.to_dict() for s in self.released_signals],
            "blocked_signals": [s.to_dict() for s in self.blocked_signals],
            "cause": self.cause.value if self.cause else None,
            "run_id": self.run_id,
            "seed": self.seed,
            "prereg_version": self.prereg_version,
            "timestamp_utc": self.timestamp_utc,
            "live_pre_reg_hash": self.live_pre_reg_hash,
            "reference_only": list(self.reference_only),
        }


def validate_signal_envelope(envelope: DiagnosticSignalEnvelope) -> list[str]:
    """Return human-readable contract violations (empty == valid)."""
    errors: list[str] = []

    if envelope.gate_action == GateAction.BLOCKED and envelope.cause is None:
        errors.append(
            "BLOCKED requires cause (FILTER_ARTIFACT | INERT_ENCODING | FDR_FAIL | "
            "ETHICAL_BOUNDARY | …)"
        )

    if envelope.gate_action == GateAction.RELEASED:
        if envelope.verdict not in {
            DiagnosticVerdict.DIAG_SIGNAL_VALID,
            DiagnosticVerdict.DIAG_OVERCONSERVATIVE,
        }:
            errors.append(
                "RELEASED requires verdict DIAG_SIGNAL_VALID or DIAG_OVERCONSERVATIVE"
            )

    if not envelope.s_tau:
        errors.append("s_tau must be non-empty")

    if not envelope.run_id:
        errors.append("run_id required")

    if not envelope.prereg_version:
        errors.append("prereg_version required")

    if envelope.gate_action == GateAction.BLOCKED and not envelope.blocked_signals:
        errors.append("BLOCKED should include at least one blocked_signal entry")

    return errors


def envelope_for_verdict(
    *,
    verdict: DiagnosticVerdict,
    run_id: str,
    seed: int,
    prereg_version: str,
    s_tau: Mapping[str, Mapping[str, float]],
    fdr_status: FDRResult,
    collapse_info: CollapseInfo,
    released_signals: tuple[ReleasedSignal, ...] = (),
    blocked_signals: tuple[BlockedSignal, ...] = (),
    cause: BlockCause | None = None,
    live_pre_reg_hash: str = "",
    reference_only: tuple[str, ...] = (),
) -> DiagnosticSignalEnvelope:
    """Factory with gate_action derived from verdict."""
    if verdict == DiagnosticVerdict.DIAG_SIGNAL_VALID:
        gate_action = GateAction.RELEASED
        cause = None
    elif verdict in {
        DiagnosticVerdict.DIAG_FILTER_ARTIFACT,
        DiagnosticVerdict.DIAG_INCONCLUSIVE,
        DiagnosticVerdict.DIAG_INFRA_DOMINATED,
    }:
        gate_action = GateAction.BLOCKED
        if cause is None:
            cause = _default_cause_for_verdict(verdict)
    else:
        gate_action = GateAction.BLOCKED
        if cause is None:
            cause = BlockCause.INCONCLUSIVE

    envelope = DiagnosticSignalEnvelope(
        verdict=verdict,
        gate_action=gate_action,
        s_tau=s_tau,
        fdr_status=fdr_status,
        collapse_info=collapse_info,
        released_signals=released_signals,
        blocked_signals=blocked_signals,
        cause=cause,
        run_id=run_id,
        seed=seed,
        prereg_version=prereg_version,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        live_pre_reg_hash=live_pre_reg_hash,
        reference_only=reference_only,
    )
    violations = validate_signal_envelope(envelope)
    if violations:
        raise ValueError("; ".join(violations))
    return envelope


def _default_cause_for_verdict(verdict: DiagnosticVerdict) -> BlockCause:
    mapping = {
        DiagnosticVerdict.DIAG_FILTER_ARTIFACT: BlockCause.FILTER_ARTIFACT,
        DiagnosticVerdict.DIAG_INCONCLUSIVE: BlockCause.INCONCLUSIVE,
        DiagnosticVerdict.DIAG_INFRA_DOMINATED: BlockCause.INFRA_DOMINATED,
    }
    return mapping.get(verdict, BlockCause.INCONCLUSIVE)


# ---------------------------------------------------------------------------
# Subagent / stage contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubagentResult:
    """Result from a single Wave 38 subagent (W38-A{n}-S{m})."""

    subagent_id: str
    status: Literal["ok", "skipped", "failed"]
    metrics: Mapping[str, float | int | str] = field(default_factory=dict)
    artifacts: tuple[dict[str, Any], ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageContext:
    """Mutable pipeline context passed through stages 1–9."""

    run_id: str
    user_id: str
    job_id: str
    data_root: str
    seed: int
    prereg_version: str
    live_pre_reg_hash: str = ""
    stage_outputs: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Bridge study / legacy types (confirmatory path, read-only)
# ---------------------------------------------------------------------------


class PermFragmentVerdict(str, Enum):
    PERM_PASS = "PERM_PASS"
    PERM_FAIL = "PERM_FAIL"


class KFoldFragmentVerdict(str, Enum):
    KFOLD_STABLE = "KFOLD_STABLE"
    KFOLD_LOCALIZED_BREAK = "KFOLD_LOCALIZED_BREAK"


class InSilicoFragmentVerdict(str, Enum):
    DIAG_IN_SILICO_PASS = "DIAG_IN_SILICO_PASS"
    DIAG_FILTER_ARTIFACT = "DIAG_FILTER_ARTIFACT"


# Alias — confirmatory imports FinalDiagnosticVerdict
FinalDiagnosticVerdict = DiagnosticVerdict


class InformativityStatus(str, Enum):
    OK = "OK"
    INERT_ENCODING = "INERT_ENCODING"
    UNTESTABLE = "DIAG_UNTESTABLE"


class AttributionCell(str, Enum):
    TP = "TP"
    FP_INFRA = "FP_infra"
    FN_MODEL = "FN_model"
    TN = "TN"


class DiagnosticRunOptions(TypedDict, total=False):
    seed: int
    n_surrogates: int
    n_perm_shifts: int
    skip_ex_post: bool
    allow_smoke: bool
    confirmatory: bool
    informativity_gate: str
    live: bool
    prereg_version: str


class V3Refs(TypedDict, total=False):
    integrity_gate: str
    coverage_gate: str
    ergebnis: str


class DiagnosticRunInput(TypedDict, total=False):
    run_id: str
    user_id: str
    domain: str
    pre_reg: str
    v3_refs: V3Refs
    inputs: dict[str, Any]
    options: DiagnosticRunOptions


class AgentEnvelope(TypedDict):
    status: Literal["started", "completed", "failed"]
    job_id: str
    artifacts: list[dict[str, Any]]
    error: str | None
    logs: list[str]


@dataclass
class PipelineState:
    """Orchestrator progress — bridge skeleton pipeline."""

    job_id: str
    user_id: str
    steps_completed: list[str] = field(default_factory=list)
    skip_ex_post: bool = True
    skeleton_mode: bool = True
