"""
Agent X — Bridge Filter Diagnostic (Wave 38, Agents 2–8 + Supervisor).

In-Silico: Ablation, Permutation, K-Fold.
Ex-Post: On-chain fetch, attribution, error source, threshold tuning.

Skeleton: envelope + interfaces only — no V3 data load, no CTE, no verdict math.
Pre-reg: docs/BRIDGE_DIAGNOSTIC_PREREG.md (bindend 2026-08-22)
"""

from __future__ import annotations

import uuid
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.types import AgentEnvelope, DiagnosticRunInput


def make_response(
    status: str,
    job_id: str,
    *,
    artifacts: list[dict[str, Any]] | None = None,
    error: str | None = None,
    logs: list[str] | None = None,
) -> AgentEnvelope:
    return {
        "status": status,  # type: ignore[typeddict-item]
        "job_id": job_id,
        "artifacts": artifacts or [],
        "error": error,
        "logs": logs or [],
    }


class _SkeletonAgent:
    """Base for agents without confirmatory implementation."""

    agent_name: str = "SkeletonAgent"

    def __init__(self, user_id: str = "diagnostic"):
        self.user_id = user_id

    def _not_implemented(self, job_id: str, artifact_type: str) -> AgentEnvelope:
        return make_response(
            "failed",
            job_id,
            error=f"{self.agent_name}: confirmatory logic not implemented (skeleton)",
            artifacts=[
                {
                    "type": artifact_type,
                    "format": "json",
                    "metadata": {"skeleton": True, "agent": self.agent_name},
                }
            ],
            logs=[f"{self.agent_name} stub — no CTE computation"],
        )


class AblationSensitivityAgent(_SkeletonAgent):
    agent_name = "AblationSensitivityAgent"

    def run(self, run_input: DiagnosticRunInput, job_id: str) -> AgentEnvelope:
        return self._not_implemented(job_id, "ablation_sensitivity")


class PermutationNullTestAgent(_SkeletonAgent):
    agent_name = "PermutationNullTestAgent"

    def run(self, run_input: DiagnosticRunInput, job_id: str) -> AgentEnvelope:
        return self._not_implemented(job_id, "permutation_null")


class KFoldLocalizationAgent(_SkeletonAgent):
    agent_name = "KFoldLocalizationAgent"

    def run(self, run_input: DiagnosticRunInput, job_id: str) -> AgentEnvelope:
        return self._not_implemented(job_id, "kfold_localization")


class OnChainOutcomeFetcher(_SkeletonAgent):
    agent_name = "OnChainOutcomeFetcher"

    def run(self, run_input: DiagnosticRunInput, job_id: str) -> AgentEnvelope:
        return self._not_implemented(job_id, "onchain_outcomes")


class AttributionMatrixBuilder(_SkeletonAgent):
    agent_name = "AttributionMatrixBuilder"

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        onchain_artifact: dict[str, Any] | None = None,
    ) -> AgentEnvelope:
        return self._not_implemented(job_id, "attribution_matrix")


class ErrorSourceClassifier(_SkeletonAgent):
    agent_name = "ErrorSourceClassifier"

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        phase1_fragments: dict[str, Any] | None = None,
        matrix_artifact: dict[str, Any] | None = None,
    ) -> AgentEnvelope:
        return self._not_implemented(job_id, "error_classification")


class ThresholdTuningAdvisor(_SkeletonAgent):
    agent_name = "ThresholdTuningAdvisor"

    def run(
        self,
        run_input: DiagnosticRunInput,
        job_id: str,
        classification_artifact: dict[str, Any] | None = None,
    ) -> AgentEnvelope:
        return self._not_implemented(job_id, "threshold_recommendations")


class DiagnosticSupervisor:
    """Unified API for Wave 38 diagnostic agents."""

    def __init__(self, user_id: str = "diagnostic"):
        self.user_id = user_id
        self.config = DiagnosticConfig()
        self.ablation = AblationSensitivityAgent(user_id)
        self.permutation = PermutationNullTestAgent(user_id)
        self.kfold = KFoldLocalizationAgent(user_id)
        self.onchain = OnChainOutcomeFetcher(user_id)
        self.matrix = AttributionMatrixBuilder(user_id)
        self.classifier = ErrorSourceClassifier(user_id)
        self.tuning = ThresholdTuningAdvisor(user_id)

    def run_bridge_diagnosis(
        self,
        run_input: DiagnosticRunInput | None = None,
        *,
        skip_ex_post: bool = True,
    ) -> AgentEnvelope:
        from agents_b2g.diagnostic.diagnostic_orchestrator import (
            DiagnosticPipelineOrchestrator,
        )

        orch = DiagnosticPipelineOrchestrator(user_id=self.user_id)
        payload: DiagnosticRunInput = run_input or {
            "user_id": self.user_id,
            "domain": "bridge_cte",
            "options": {"skip_ex_post": skip_ex_post, "confirmatory": False},
        }
        return orch.run_full_diagnosis(payload)
