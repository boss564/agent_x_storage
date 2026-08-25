#!/usr/bin/env python3
"""DiagnosticPipelineOrchestrator — Wave 38 root agent (skeleton).

Sequenz: gate → in-silico → ex-post → report → verdict.
Confirmatory CTE/permutation/verdict: not implemented until post informativity gate.

Pre-reg: docs/BRIDGE_DIAGNOSTIC_PREREG.md (bindend 2026-08-22)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from agents_b2g.diagnostic.agents import (
    AblationSensitivityAgent,
    AttributionMatrixBuilder,
    ErrorSourceClassifier,
    KFoldLocalizationAgent,
    OnChainOutcomeFetcher,
    PermutationNullTestAgent,
    ThresholdTuningAdvisor,
    make_response,
)
from agents_b2g.diagnostic.config import PIPELINE_STEPS, DiagnosticConfig, PRE_REG_PATH
from agents_b2g.diagnostic.types import DiagnosticRunInput, PipelineState

logger = logging.getLogger("DiagnosticPipelineOrchestrator")


class DiagnosticPipelineOrchestrator:
    """Root orchestrator for Bridge Filter Diagnostic (Wave 38)."""

    def __init__(self, user_id: str = "diagnostic", data_root: str | None = None):
        self.user_id = user_id
        root = data_root or str(DiagnosticConfig.DATA_ROOT)
        self.data_root = os.path.join(root, user_id, "diagnostic")
        os.makedirs(self.data_root, exist_ok=True)

        self.ablation = AblationSensitivityAgent(user_id)
        self.permutation = PermutationNullTestAgent(user_id)
        self.kfold = KFoldLocalizationAgent(user_id)
        self.onchain = OnChainOutcomeFetcher(user_id)
        self.matrix = AttributionMatrixBuilder(user_id)
        self.classifier = ErrorSourceClassifier(user_id)
        self.tuning = ThresholdTuningAdvisor(user_id)

        logger.info("DiagnosticPipelineOrchestrator initialized (skeleton mode)")

    def run_full_diagnosis(self, run_input: DiagnosticRunInput) -> dict[str, Any]:
        """Run pipeline skeleton — no V3 CTE, no confirmatory verdict."""
        job_id = run_input.get("run_id") or str(uuid.uuid4())
        options = run_input.get("options") or {}
        skip_ex_post = bool(options.get("skip_ex_post", True))
        confirmatory = bool(options.get("confirmatory", False))

        if confirmatory:
            gate_path = options.get("informativity_gate")
            if not gate_path:
                return make_response(
                    "failed",
                    job_id,
                    error=(
                        "Confirmatory diagnostic run blocked: "
                        "informativity_gate path required (Pre-reg §4)."
                    ),
                    logs=["confirmatory=True rejected — run informativity gate first"],
                )
            from pathlib import Path
            import json

            gp = Path(str(gate_path))
            if not gp.is_file():
                return make_response(
                    "failed",
                    job_id,
                    error=f"Confirmatory blocked: missing {gp}",
                    logs=["confirmatory=True rejected"],
                )
            gate_body = json.loads(gp.read_text(encoding="utf-8"))
            if gate_body.get("status") != "PASS":
                return make_response(
                    "failed",
                    job_id,
                    error=f"Confirmatory blocked: informativity gate {gate_body.get('status')}",
                    logs=[f"blockers={gate_body.get('blockers')}"],
                )

        state = PipelineState(
            job_id=job_id,
            user_id=self.user_id,
            skip_ex_post=skip_ex_post,
            skeleton_mode=True,
        )

        gate = self._run_gate_stub(run_input, state)
        if gate.get("status") == "failed":
            return gate

        # In-silico stubs — explicitly no data/CTE
        for step, agent in (
            ("ablation", self.ablation),
            ("permutation", self.permutation),
            ("kfold", self.kfold),
        ):
            result = agent.run(run_input, job_id)
            state.steps_completed.append(step)
            if result["status"] == "failed" and not self._skeleton_allows_fail(result):
                return self._wrap_pipeline_result(state, gate, failed_step=step, detail=result)

        if not skip_ex_post:
            for step, agent in (
                ("onchain_fetch", self.onchain),
                ("attribution_matrix", self.matrix),
                ("error_classification", self.classifier),
                ("threshold_tuning", self.tuning),
            ):
                result = agent.run(run_input, job_id)
                state.steps_completed.append(step)

        state.steps_completed.extend(["report", "verdict"])
        return self._wrap_pipeline_result(state, gate)

    def run_in_silico_only(self, run_input: DiagnosticRunInput) -> dict[str, Any]:
        opts = dict(run_input.get("options") or {})
        opts["skip_ex_post"] = True
        opts["confirmatory"] = False
        merged: DiagnosticRunInput = {**run_input, "options": opts}
        return self.run_full_diagnosis(merged)

    def get_status(self, job_id: str) -> dict[str, Any]:
        return make_response(
            "completed",
            job_id,
            artifacts=[
                {
                    "type": "pipeline_status",
                    "format": "json",
                    "metadata": {"skeleton": True, "steps": list(PIPELINE_STEPS)},
                }
            ],
        )

    def _run_gate_stub(
        self, run_input: DiagnosticRunInput, state: PipelineState
    ) -> dict[str, Any]:
        """Informativity gate when paths provided; otherwise structural stub."""
        options = run_input.get("options") or {}
        if options.get("confirmatory"):
            gate_path = options.get("informativity_gate")
            if not gate_path:
                return make_response(
                    "failed",
                    state.job_id,
                    error="confirmatory requires informativity_gate path (Pre-reg §4)",
                )
            import json
            from pathlib import Path

            p = Path(str(gate_path))
            if not p.exists():
                return make_response(
                    "failed",
                    state.job_id,
                    error=f"missing informativity gate: {p}",
                )
            body = json.loads(p.read_text(encoding="utf-8"))
            if body.get("status") != "PASS":
                return make_response(
                    "failed",
                    state.job_id,
                    error=f"informativity gate blocked: {body.get('blockers')}",
                )

        pre_reg = run_input.get("pre_reg", PRE_REG_PATH)
        state.steps_completed.append("gate")
        return make_response(
            "completed",
            state.job_id,
            artifacts=[
                {
                    "type": "diagnostic_gate",
                    "format": "json",
                    "metadata": {
                        "pre_reg": pre_reg,
                        "informativity_checked": bool(options.get("informativity_gate")),
                    },
                }
            ],
            logs=["gate complete"],
        )

    @staticmethod
    def _skeleton_allows_fail(result: dict[str, Any]) -> bool:
        meta = (result.get("artifacts") or [{}])[0].get("metadata", {})
        return bool(meta.get("skeleton"))

    def _wrap_pipeline_result(
        self,
        state: PipelineState,
        gate: dict[str, Any],
        *,
        failed_step: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact = {
            "type": "diagnostic_run_skeleton",
            "format": "json",
            "metadata": {
                "skeleton": True,
                "user_id": state.user_id,
                "steps_completed": state.steps_completed,
                "skip_ex_post": state.skip_ex_post,
                "pipeline_steps": list(PIPELINE_STEPS),
                "failed_step": failed_step,
                "final_verdict": None,
                "pre_reg": PRE_REG_PATH,
            },
        }
        logs = ["skeleton pipeline complete — no ΔCTE, no verdict"]
        if failed_step:
            logs.append(f"non-skeleton failure at {failed_step}")
        return make_response(
            "completed",
            state.job_id,
            artifacts=[artifact, *(gate.get("artifacts") or [])],
            logs=logs,
        )
