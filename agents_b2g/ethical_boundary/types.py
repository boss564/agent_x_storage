"""Wave 39 typed contracts — contract-first; no orchestrator logic here.

Frozen dataclasses and versioned enums define ethical boundaries before any
pipeline code runs. Fail-closed semantics are encoded in validation helpers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Literal, Mapping

from agents_b2g.diagnostic.types import BlockCause
from agents_b2g.ethical_boundary.config import (
    ETHICAL_BLOCKING_SEVERITY_THRESHOLD,
    OFFENSIVE_PURPOSE_MARKERS,
)

# ---------------------------------------------------------------------------
# Scope (immutable)
# ---------------------------------------------------------------------------

SCOPE_DEFENSIVE: Literal["DEFENSIVE_CAUSAL_GROUNDING"] = "DEFENSIVE_CAUSAL_GROUNDING"

DEFENSIVE_PURPOSES = frozenset(
    {
        "RISK_MANAGEMENT",
        "SIGNAL_DENOISING",
        "CAUSAL_GROUNDING",
        "PERIMETER_DEFENSE",
        "AUDIT_OBSERVATION",
    }
)


# ---------------------------------------------------------------------------
# Verdict & violation taxonomy (versioned enums)
# ---------------------------------------------------------------------------


class EthicalVerdict(str, Enum):
    """Wave 39 pipeline outcome."""

    CERTIFIED = "CERTIFIED"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ViolationType(str, Enum):
    """Versioned violation taxonomy — maps to BlockCause.ETHICAL_BOUNDARY."""

    PREREG_NEGATION = "PREREG_NEGATION"
    OFFENSIVE_EXECUTION = "OFFENSIVE_EXECUTION"
    PROFIT_EXTRACTION = "PROFIT_EXTRACTION"
    SCOPE_TAMPER = "SCOPE_TAMPER"
    CHARTER_AIRGAP = "CHARTER_AIRGAP"
    AUDIT_INTEGRITY = "AUDIT_INTEGRITY"
    ASSERTION_FAILURE = "ASSERTION_FAILURE"
    CONFIG_INTEGRITY = "CONFIG_INTEGRITY"
    PIPELINE_FAULT = "PIPELINE_FAULT"


@dataclass(frozen=True)
class ViolationSeverity:
    """Validated severity band 0–100 (immutable)."""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or not 0 <= self.value <= 100:
            raise ValueError(f"ViolationSeverity must be int in [0, 100]; got {self.value!r}")

    @classmethod
    def critical(cls) -> ViolationSeverity:
        return cls(100)

    @classmethod
    def high(cls) -> ViolationSeverity:
        return cls(75)

    @classmethod
    def blocking_threshold(cls) -> int:
        """Registered threshold — Charter §9.1 / config.ETHICAL_BLOCKING_SEVERITY_THRESHOLD."""
        return ETHICAL_BLOCKING_SEVERITY_THRESHOLD

    def is_blocking(self) -> bool:
        return self.value >= self.blocking_threshold()

    def to_dict(self) -> dict[str, int]:
        return {"value": self.value}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EthicalBoundaryException(Exception):
    """Fail-closed: maps to Gatekeeper BLOCKED + BlockCause.ETHICAL_BOUNDARY."""

    def __init__(
        self,
        message: str,
        *,
        violation_type: ViolationType,
        agent: str,
        severity: ViolationSeverity | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.violation_type = violation_type
        self.agent = agent
        self.severity = severity or ViolationSeverity.critical()
        self.evidence = dict(evidence or {})

    def to_violation_record(self) -> ViolationRecord:
        return ViolationRecord(
            violation_type=self.violation_type,
            severity=self.severity,
            source_agent=self.agent,
            message=str(self),
            evidence=self.evidence,
        )


# ---------------------------------------------------------------------------
# Core frozen contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeFlag:
    """Immutable defensive scope marker attached to every payload."""

    scope: Literal["DEFENSIVE_CAUSAL_GROUNDING"]
    attached_at: str
    attached_by: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.scope != SCOPE_DEFENSIVE:
            raise ValueError(f"invalid scope {self.scope!r}; must be {SCOPE_DEFENSIVE!r}")
        if not self.attached_at:
            raise ValueError("attached_at required")
        if not self.attached_by:
            raise ValueError("attached_by required")
        if not self.content_hash:
            raise ValueError("content_hash required")

    def to_dict(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "attached_at": self.attached_at,
            "attached_by": self.attached_by,
            "content_hash": self.content_hash,
        }

    _ALLOWED_KEYS: ClassVar[frozenset[str]] = frozenset(
        {"scope", "attached_at", "attached_by", "content_hash"}
    )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScopeFlag:
        """Parse JSON/dict — reject unknown keys and invalid scope (anti-injection)."""
        extra = set(data.keys()) - cls._ALLOWED_KEYS
        if extra:
            raise ValueError(f"ScopeFlag rejects unknown keys: {sorted(extra)}")
        return cls(
            scope=data["scope"],  # type: ignore[arg-type]
            attached_at=str(data["attached_at"]),
            attached_by=str(data["attached_by"]),
            content_hash=str(data["content_hash"]),
        )


@dataclass(frozen=True)
class NonExtractionAssertion:
    """Runtime assertion input — receiver must not target profit extraction."""

    receiver_id: str
    allowed_purposes: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.receiver_id:
            raise ValueError("receiver_id required")
        for purpose in self.allowed_purposes:
            if purpose not in DEFENSIVE_PURPOSES:
                raise ValueError(
                    f"purpose {purpose!r} not in DEFENSIVE_PURPOSES"
                )

    def offensive_markers_present(self) -> tuple[str, ...]:
        found: list[str] = []
        meta = dict(self.metadata)
        purposes = meta.get("purposes") or meta.get("purpose") or []
        if isinstance(purposes, str):
            purposes = [purposes]
        for item in purposes:
            token = str(item).upper()
            if token in OFFENSIVE_PURPOSE_MARKERS:
                found.append(token)
        intent = str(meta.get("intent", "")).upper()
        for marker in OFFENSIVE_PURPOSE_MARKERS:
            if marker in intent:
                found.append(marker)
        return tuple(dict.fromkeys(found))


@dataclass(frozen=True)
class ViolationRecord:
    violation_type: ViolationType
    severity: ViolationSeverity
    source_agent: str
    message: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def is_auto_block(self) -> bool:
        if self.violation_type in {
            ViolationType.PREREG_NEGATION,
            ViolationType.OFFENSIVE_EXECUTION,
            ViolationType.PROFIT_EXTRACTION,
            ViolationType.SCOPE_TAMPER,
            ViolationType.CHARTER_AIRGAP,
            ViolationType.CONFIG_INTEGRITY,
            ViolationType.PIPELINE_FAULT,
        }:
            return True
        return self.severity.is_blocking()

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_type": self.violation_type.value,
            "severity": self.severity.to_dict(),
            "source_agent": self.source_agent,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ViolationObservation:
    """Deskriptives Wave-28-Envelope — keine Aktions-Felder erlaubt."""

    signature: str
    severity: ViolationSeverity
    timestamp_utc: str
    source_agent: str

    def __post_init__(self) -> None:
        if not self.signature:
            raise ValueError("signature required")
        if not self.timestamp_utc:
            raise ValueError("timestamp_utc required")
        if not self.source_agent:
            raise ValueError("source_agent required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "severity": self.severity.to_dict(),
            "timestamp_utc": self.timestamp_utc,
            "source_agent": self.source_agent,
        }

    _ALLOWED_KEYS: ClassVar[frozenset[str]] = frozenset(
        {"signature", "severity", "timestamp_utc", "source_agent"}
    )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ViolationObservation:
        """Deserialize — no action/execute/countermeasure fields permitted."""
        extra = set(data.keys()) - cls._ALLOWED_KEYS
        if extra:
            raise ValueError(
                f"ViolationObservation rejects action fields / unknown keys: {sorted(extra)}"
            )
        sev_raw = data["severity"]
        if isinstance(sev_raw, Mapping):
            severity = ViolationSeverity(int(sev_raw["value"]))
        else:
            severity = ViolationSeverity(int(sev_raw))
        return cls(
            signature=str(data["signature"]),
            severity=severity,
            timestamp_utc=str(data["timestamp_utc"]),
            source_agent=str(data["source_agent"]),
        )


@dataclass(frozen=True)
class EthicalBoundaryEnvelope:
    """Wave 39 output — consumed by Wave 38 Gatekeeper pre-flight."""

    status: EthicalVerdict
    job_id: str
    scope: ScopeFlag
    violations: tuple[ViolationRecord, ...] = ()
    prereg_hashes: Mapping[str, str] = field(default_factory=dict)
    charter_version: str = "1.0"
    certified_at: str | None = None
    block_cause: BlockCause | None = None
    wave28_observations: tuple[ViolationObservation, ...] = ()
    certificate_id: str | None = None

    def __post_init__(self) -> None:
        if self.status == EthicalVerdict.BLOCKED and self.block_cause != BlockCause.ETHICAL_BOUNDARY:
            raise ValueError(
                "BLOCKED EthicalBoundaryEnvelope requires block_cause=ETHICAL_BOUNDARY"
            )
        if self.status == EthicalVerdict.CERTIFIED and self.violations:
            raise ValueError("CERTIFIED envelope must not carry violations")
        if self.status == EthicalVerdict.CERTIFIED and not self.certificate_id:
            raise ValueError("CERTIFIED envelope requires certificate_id")
        if self.status == EthicalVerdict.BLOCKED and self.certificate_id:
            raise ValueError("BLOCKED envelope must not carry certificate_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "job_id": self.job_id,
            "scope": self.scope.to_dict(),
            "violations": [v.to_dict() for v in self.violations],
            "prereg_hashes": dict(self.prereg_hashes),
            "charter_version": self.charter_version,
            "certified_at": self.certified_at,
            "block_cause": self.block_cause.value if self.block_cause else None,
            "wave28_observations": [o.to_dict() for o in self.wave28_observations],
            "certificate_id": self.certificate_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EthicalBoundaryEnvelope:
        """Load from JSON — re-validates ScopeFlag and envelope contract."""
        scope_raw = data.get("scope")
        if not isinstance(scope_raw, Mapping):
            raise ValueError("envelope.scope must be a mapping")
        scope = ScopeFlag.from_dict(scope_raw)

        violations: list[ViolationRecord] = []
        for item in data.get("violations") or []:
            sev = item["severity"]
            severity = ViolationSeverity(
                int(sev["value"] if isinstance(sev, Mapping) else sev)
            )
            violations.append(
                ViolationRecord(
                    violation_type=ViolationType(str(item["violation_type"])),
                    severity=severity,
                    source_agent=str(item["source_agent"]),
                    message=str(item["message"]),
                    evidence=dict(item.get("evidence") or {}),
                )
            )

        observations = tuple(
            ViolationObservation.from_dict(o)
            for o in (data.get("wave28_observations") or [])
        )

        block_raw = data.get("block_cause")
        block_cause = BlockCause(block_raw) if block_raw else None

        envelope = cls(
            status=EthicalVerdict(str(data["status"])),
            job_id=str(data["job_id"]),
            scope=scope,
            violations=tuple(violations),
            prereg_hashes=dict(data.get("prereg_hashes") or {}),
            charter_version=str(data.get("charter_version", "1.0")),
            certified_at=data.get("certified_at"),
            block_cause=block_cause,
            wave28_observations=observations,
            certificate_id=data.get("certificate_id"),
        )
        contract_errors = validate_ethical_envelope(envelope)
        if contract_errors:
            raise ValueError("; ".join(contract_errors))
        return envelope


# ---------------------------------------------------------------------------
# Factories & validation
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCOPE_STRIP_KEYS = frozenset(
    {
        "scope",
        "ethical_boundary_job_id",
        "charter_version",
        "scope_attached_by",
        "scope_content_hash",
    }
)


def content_hash_without_scope(payload: Mapping[str, Any]) -> str:
    """SHA-256 of payload excluding scope and propagation metadata."""
    stripped = {k: v for k, v in payload.items() if k not in _SCOPE_STRIP_KEYS}
    blob = json.dumps(stripped, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def attach_scope_flag(
    payload: Mapping[str, Any],
    *,
    attached_by: str,
) -> ScopeFlag:
    return ScopeFlag(
        scope=SCOPE_DEFENSIVE,
        attached_at=utc_now_iso(),
        attached_by=attached_by,
        content_hash=content_hash_without_scope(payload),
    )


def validate_scope_immutable(
    payload: Mapping[str, Any],
    expected: ScopeFlag,
) -> ViolationRecord | None:
    """Return violation if scope tampered; None if intact."""
    scope_val = payload.get("scope")
    if scope_val != SCOPE_DEFENSIVE:
        return ViolationRecord(
            violation_type=ViolationType.SCOPE_TAMPER,
            severity=ViolationSeverity.critical(),
            source_agent="ScopeEnforcerAgent",
            message=f"scope tampered: expected {SCOPE_DEFENSIVE!r}, got {scope_val!r}",
            evidence={"expected": expected.to_dict(), "actual_scope": scope_val},
        )
    current_hash = content_hash_without_scope(payload)
    if current_hash != expected.content_hash:
        return ViolationRecord(
            violation_type=ViolationType.SCOPE_TAMPER,
            severity=ViolationSeverity.critical(),
            source_agent="ScopeEnforcerAgent",
            message="content hash mismatch after scope attach",
            evidence={
                "expected_hash": expected.content_hash,
                "actual_hash": current_hash,
            },
        )
    return None


def check_non_extraction(assertion: NonExtractionAssertion) -> ViolationRecord | None:
    markers = assertion.offensive_markers_present()
    if markers:
        return ViolationRecord(
            violation_type=ViolationType.PROFIT_EXTRACTION,
            severity=ViolationSeverity.critical(),
            source_agent="EthicalAssertionAgent",
            message="NonExtractionAssertion failed: offensive purpose markers",
            evidence={"markers": list(markers), "receiver_id": assertion.receiver_id},
        )
    return None


def check_charter_airgap(payload: Mapping[str, Any]) -> ViolationRecord | None:
    """Backward-compatible wrapper — delegates to Agent 6 AirGapValidator."""
    from agents_b2g.ethical_boundary.subagents.charter.air_gap_validator import (
        AirGapValidator,
    )

    return AirGapValidator().validate(payload)


def violations_to_observations(
    violations: tuple[ViolationRecord, ...],
) -> tuple[ViolationObservation, ...]:
    """Map violations to deskriptive Wave-28 observations (no action fields)."""
    observations: list[ViolationObservation] = []
    for v in violations:
        observations.append(
            ViolationObservation(
                signature=f"{v.violation_type.value}:{v.source_agent}",
                severity=v.severity,
                timestamp_utc=utc_now_iso(),
                source_agent="BoundaryViolationReporter",
            )
        )
    return tuple(observations)


def blocked_envelope(
    *,
    job_id: str,
    scope: ScopeFlag,
    violations: tuple[ViolationRecord, ...],
    charter_version: str = "1.0",
    prereg_hashes: Mapping[str, str] | None = None,
) -> EthicalBoundaryEnvelope:
    return EthicalBoundaryEnvelope(
        status=EthicalVerdict.BLOCKED,
        job_id=job_id,
        scope=scope,
        violations=violations,
        prereg_hashes=dict(prereg_hashes or {}),
        charter_version=charter_version,
        certified_at=None,
        block_cause=BlockCause.ETHICAL_BOUNDARY,
        wave28_observations=violations_to_observations(violations),
    )


def certified_envelope(
    *,
    job_id: str,
    scope: ScopeFlag,
    charter_version: str = "1.0",
    prereg_hashes: Mapping[str, str] | None = None,
    certificate_id: str,
) -> EthicalBoundaryEnvelope:
    return EthicalBoundaryEnvelope(
        status=EthicalVerdict.CERTIFIED,
        job_id=job_id,
        scope=scope,
        violations=(),
        prereg_hashes=dict(prereg_hashes or {}),
        charter_version=charter_version,
        certified_at=utc_now_iso(),
        block_cause=None,
        wave28_observations=(),
        certificate_id=certificate_id,
    )


def validate_ethical_envelope(envelope: EthicalBoundaryEnvelope) -> list[str]:
    """Return human-readable contract violations (empty == valid)."""
    errors: list[str] = []

    if envelope.status == EthicalVerdict.BLOCKED:
        if envelope.block_cause != BlockCause.ETHICAL_BOUNDARY:
            errors.append("BLOCKED requires block_cause=ETHICAL_BOUNDARY")
        if not envelope.violations:
            errors.append("BLOCKED requires at least one violation record")
        if envelope.certificate_id:
            errors.append("BLOCKED must not include certificate_id")

    if envelope.status == EthicalVerdict.CERTIFIED:
        if envelope.certified_at is None:
            errors.append("CERTIFIED requires certified_at")
        if envelope.violations:
            errors.append("CERTIFIED must not include violations")
        if not envelope.certificate_id:
            errors.append("CERTIFIED requires certificate_id")
        elif len(envelope.certificate_id) != 64 or any(
            c not in "0123456789abcdef" for c in envelope.certificate_id
        ):
            errors.append("certificate_id must be lowercase SHA-256 hex (64 chars)")

    if envelope.scope.scope != SCOPE_DEFENSIVE:
        errors.append("scope must be DEFENSIVE_CAUSAL_GROUNDING")

    try:
        ScopeFlag.from_dict(envelope.scope.to_dict())
    except ValueError as exc:
        errors.append(f"scope failed deserialization guard: {exc}")

    for obs in envelope.wave28_observations:
        obs_dict = obs.to_dict()
        forbidden = {"execute", "respond", "countermeasure", "action", "route"}
        if forbidden.intersection(obs_dict.keys()):
            errors.append("ViolationObservation must not carry action fields")

    return errors


def merge_violations(*groups: tuple[ViolationRecord, ...]) -> tuple[ViolationRecord, ...]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[ViolationRecord] = []
    for group in groups:
        for v in group:
            key = (v.violation_type.value, v.source_agent, v.message)
            if key in seen:
                continue
            seen.add(key)
            merged.append(v)
    return tuple(merged)


def should_block(violations: tuple[ViolationRecord, ...]) -> bool:
    return any(v.is_auto_block() for v in violations)
