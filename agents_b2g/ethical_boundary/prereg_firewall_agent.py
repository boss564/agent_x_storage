"""Agent 1 — PreRegFirewallAgent (Wave 39).

Validates bindend Pre-Reg documents, WORM hash integrity, §1.0.E negation clause,
and offensive-purpose markers before any downstream ethical stage runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agents_b2g.ethical_boundary.agents import make_response
from agents_b2g.ethical_boundary.config import (
    EthicalBoundaryConfig,
    OFFENSIVE_MARKER_REGISTRY,
)
from agents_b2g.ethical_boundary.logging_utils import JSONLogger, _safe_call
from agents_b2g.ethical_boundary.subagents.prereg import (
    ExclusionEnforcer,
    NegativClauseValidator,
    PreRegHashArchiver,
    PreRegLoader,
)
from agents_b2g.ethical_boundary.types import (
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)


@dataclass(frozen=True)
class PreRegFirewallResult:
    violations: tuple[ViolationRecord, ...]
    validated_hashes: dict[str, str]
    registry_version: str
    documents_loaded: int


class PreRegFirewallAgent:
    """Stage 1 — Pre-Reg integrity firewall (subagents S1–S4 critical path)."""

    agent_name = "PreRegFirewallAgent"

    def __init__(self, user_id: str = "wave39", config: EthicalBoundaryConfig | None = None):
        self.user_id = user_id
        self.config = config or EthicalBoundaryConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self.loader = PreRegLoader()
        self.hash_archiver = PreRegHashArchiver()
        self.negativ_validator = NegativClauseValidator()
        self.exclusion_enforcer = ExclusionEnforcer()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(
            self.logger,
            self.agent_name,
            self._run_inner,
            payload,
            job_id,
        )

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
    ) -> PreRegFirewallResult:
        return self._enforce(payload, job_id=job_id)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._enforce(payload, job_id=job_id)
        status = "blocked" if result.violations else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "prereg_firewall_result",
                    "documents_loaded": result.documents_loaded,
                    "validated_hash_keys": sorted(result.validated_hashes.keys()),
                    "registry_version": result.registry_version,
                    "violation_count": len(result.violations),
                    "marker_registry_version": OFFENSIVE_MARKER_REGISTRY.version,
                }
            ],
            logs=[
                f"documents_loaded={result.documents_loaded}",
                f"violations={len(result.violations)}",
            ],
        )

    def _enforce(self, payload: Mapping[str, Any], *, job_id: str) -> PreRegFirewallResult:
        _ = job_id
        violations: list[ViolationRecord] = []

        try:
            loader_result = self.loader.run(self.config.project_root)
            for key in loader_result.missing:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.CONFIG_INTEGRITY,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.loader.subagent_id,
                        message=f"pre-reg document missing: {key}",
                        evidence={"key": key},
                    )
                )

            registry_path = self._resolve_registry_path()
            hash_result = self.hash_archiver.run(
                self.config.project_root,
                registry_path=registry_path,
            )
            if hash_result.registry_error:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.CONFIG_INTEGRITY,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.hash_archiver.subagent_id,
                        message=f"WORM registry unreadable: {hash_result.registry_error}",
                        evidence={"registry_path": str(registry_path)},
                    )
                )
            for key in hash_result.missing_registry_keys:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.CONFIG_INTEGRITY,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.hash_archiver.subagent_id,
                        message=f"WORM registry missing hash for {key}",
                        evidence={"key": key},
                    )
                )
            for mismatch in hash_result.mismatches:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.CONFIG_INTEGRITY,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.hash_archiver.subagent_id,
                        message=f"pre-reg hash mismatch for {mismatch.key}",
                        evidence={
                            "key": mismatch.key,
                            "expected": mismatch.expected,
                            "actual": mismatch.actual,
                            "path": mismatch.path,
                        },
                    )
                )

            negativ_result = self.negativ_validator.run(
                payload,
                documents=loader_result.documents,
            )
            for key in negativ_result.not_bindend_keys:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.PREREG_NEGATION,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.negativ_validator.subagent_id,
                        message=f"pre-reg not marked bindend: {key}",
                        evidence={"key": key},
                    )
                )
            for flag in negativ_result.bypass_flags:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.PREREG_NEGATION,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.negativ_validator.subagent_id,
                        message=f"negation clause bypass flag: {flag}",
                        evidence={"flag": flag, "charter_ref": "§1.0.E"},
                    )
                )
            for hit in negativ_result.hits:
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.PREREG_NEGATION,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.negativ_validator.subagent_id,
                        message=f"§1.0.E negation violated at {hit.location}: {hit.marker}",
                        evidence={
                            "marker": hit.marker,
                            "location": hit.location,
                            "charter_ref": hit.charter_ref,
                        },
                    )
                )

            exclusion_result = self.exclusion_enforcer.run(payload)
            for hit in exclusion_result.hits:
                if any(
                    v.evidence.get("marker") == hit.marker
                    and v.evidence.get("json_path") == hit.json_path
                    for v in violations
                ):
                    continue
                violations.append(
                    ViolationRecord(
                        violation_type=ViolationType.PREREG_NEGATION,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.exclusion_enforcer.subagent_id,
                        message=f"offensive purpose marker at {hit.json_path}: {hit.marker}",
                        evidence={
                            "marker": hit.marker,
                            "json_path": hit.json_path,
                            "charter_ref": hit.charter_ref,
                            "registry_version": OFFENSIVE_MARKER_REGISTRY.version,
                        },
                    )
                )

            registry_version = self._registry_version(registry_path)
            return PreRegFirewallResult(
                violations=tuple(violations),
                validated_hashes=dict(hash_result.validated_hashes),
                registry_version=registry_version,
                documents_loaded=len(loader_result.documents),
            )

        except Exception as exc:
            return PreRegFirewallResult(
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PIPELINE_FAULT,
                        severity=ViolationSeverity.critical(),
                        source_agent=self.agent_name,
                        message=f"PreRegFirewallAgent fault: {exc}",
                    ),
                ),
                validated_hashes={},
                registry_version="unknown",
                documents_loaded=0,
            )

    def _resolve_registry_path(self) -> Path:
        env_path = os.getenv("ETHICAL_PREREG_HASH_REGISTRY")
        if env_path:
            return Path(env_path)
        user_path = PreRegHashArchiver.user_registry_path(
            self.config.data_root,
            self.user_id,
        )
        if user_path.is_file():
            return user_path
        return PreRegHashArchiver.default_registry_path(self.config.project_root)

    @staticmethod
    def _registry_version(registry_path: Path) -> str:
        if not registry_path.is_file():
            return "unknown"
        import json

        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            return str(data.get("version", "unknown"))
        except (OSError, json.JSONDecodeError):
            return "unknown"
