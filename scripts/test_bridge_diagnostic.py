"""
Structural tests for Wave 38 — Bridge Filter Diagnostic (skeleton).

No V3 data load, no CTE values, no confirmatory verdict assertions.
Pre-reg §0.1: typenrein only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

from agents_b2g.diagnostic import (
    DiagnosticPipelineOrchestrator,
    DiagnosticReportComposer,
    DiagnosticSupervisor,
)
from agents_b2g.diagnostic import config as diag_config
from agents_b2g.diagnostic.agents import make_response
from agents_b2g.diagnostic.types import (
    CandidateRole,
    FinalDiagnosticVerdict,
    PermFragmentVerdict,
)


def test_pre_reg_constants_match_binding_doc():
    assert diag_config.EPS_INERT == 0.001
    assert diag_config.TAU_CLEANSING == 0.05
    assert diag_config.RHO_COLLAPSE == 0.50
    assert diag_config.OCC_SAT == 0.90
    assert diag_config.P_SIGN_MIN == 0.95
    assert diag_config.TAU_FN == 0.10
    assert diag_config.TAU_FP == 0.15
    assert diag_config.BRIDGE_DIAGNOSTIC_SEED == 20260822
    assert len(diag_config.CANDIDATE_IDS) == 5


def test_make_response_envelope():
    resp = make_response("completed", "job-1", artifacts=[{"type": "x"}], logs=["ok"])
    assert resp["status"] == "completed"
    assert resp["job_id"] == "job-1"
    assert resp["error"] is None
    assert len(resp["artifacts"]) == 1


def test_enum_values_for_verdict_taxonomy():
    assert PermFragmentVerdict.PERM_PASS.value == "PERM_PASS"
    assert FinalDiagnosticVerdict.DIAG_INCONCLUSIVE.value == "DIAG_INCONCLUSIVE"
    assert CandidateRole.CLEANSING_WORKER.value == "cleansing_worker"


def test_orchestrator_skeleton_no_verdict():
    orch = DiagnosticPipelineOrchestrator(user_id="test_skeleton")
    result = orch.run_full_diagnosis(
        {
            "user_id": "test_skeleton",
            "domain": "bridge_cte",
            "options": {"skip_ex_post": True, "confirmatory": False},
        }
    )
    assert result["status"] == "completed"
    meta = result["artifacts"][0]["metadata"]
    assert meta["skeleton"] is True
    assert meta["final_verdict"] is None
    assert "ablation" in meta["steps_completed"]
    assert "gate" in meta["steps_completed"]


def test_orchestrator_blocks_confirmatory_without_gate():
    orch = DiagnosticPipelineOrchestrator(user_id="test_skeleton")
    result = orch.run_full_diagnosis(
        {
            "options": {"confirmatory": True},
        }
    )
    assert result["status"] == "failed"
    assert "informativity_gate" in (result["error"] or "").lower()


def test_orchestrator_blocks_confirmatory_if_gate_missing_file():
    import tempfile

    orch = DiagnosticPipelineOrchestrator(user_id="test_skeleton")
    missing = Path(tempfile.gettempdir()) / "nonexistent_informativity_gate_xyz.json"
    result = orch.run_full_diagnosis(
        {
            "options": {
                "confirmatory": True,
                "informativity_gate": str(missing),
            },
        }
    )
    assert result["status"] == "failed"
    assert "missing" in (result["error"] or "").lower() or "blocked" in (result["error"] or "").lower()


def test_supervisor_entrypoint():
    sup = DiagnosticSupervisor(user_id="test_skeleton")
    result = sup.run_bridge_diagnosis(skip_ex_post=True)
    assert result["status"] == "completed"
    assert result["artifacts"][0]["metadata"]["skeleton"] is True


def test_report_composer_stub():
    comp = DiagnosticReportComposer(user_id="test_skeleton")
    result = comp.compose("job-x", {})
    assert result["status"] == "failed"
    assert result["artifacts"][0]["metadata"]["skeleton"] is True


def test_pipeline_steps_order():
    steps = list(diag_config.PIPELINE_STEPS)
    assert steps[0] == "gate"
    assert steps[-1] == "verdict"
    assert "permutation" in steps
    assert "ablation" in steps


def test_no_v3_imports_in_diagnostic_package():
    """Skeleton must not wire bridge_stufe_a_v3_load in orchestrator module."""
    text = Path(
        ROOT / "agents_b2g/diagnostic/diagnostic_orchestrator.py"
    ).read_text(encoding="utf-8")
    assert "bridge_stufe_a_v3_load" not in text
    assert "transfer_entropy" not in text


def run_all():
    tests = [
        test_pre_reg_constants_match_binding_doc,
        test_make_response_envelope,
        test_enum_values_for_verdict_taxonomy,
        test_orchestrator_skeleton_no_verdict,
        test_orchestrator_blocks_confirmatory_without_gate,
        test_orchestrator_blocks_confirmatory_if_gate_missing_file,
        test_supervisor_entrypoint,
        test_report_composer_stub,
        test_pipeline_steps_order,
        test_no_v3_imports_in_diagnostic_package,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_all())
