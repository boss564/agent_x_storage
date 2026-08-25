#!/usr/bin/env python3
"""Wave 39 Ethical Boundary Enforcement — contract & fail-closed tests."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Mapping
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.diagnostic.gatekeeper_dispatcher_agent import GatekeeperDispatcherAgent
from agents_b2g.diagnostic.ethical_boundary_hook import (
    ethical_beats_methodical,
    gate_cause_priority,
    normalize_envelope_metadata_for_regression,
    resolve_final_gate,
)
from agents_b2g.diagnostic.types import BlockCause, DiagnosticVerdict
from agents_b2g.ethical_boundary.config import (
    ETHICAL_BLOCKING_SEVERITY_THRESHOLD,
    OFFENSIVE_MARKER_REGISTRY,
    EthicalBoundaryConfig,
    EthicalBoundaryConfigError,
)
from agents_b2g.ethical_boundary.ethical_assertion_agent import EthicalAssertionAgent
from agents_b2g.ethical_boundary.audit_constants import (
    AUDIT_GENESIS_HASH,
    AUDIT_PURPOSE_OBSERVATION_AND_DEFENSE,
)
from agents_b2g.ethical_boundary.charter_enforcer_agent import CharterEnforcerAgent
from agents_b2g.ethical_boundary.audit_trail_agent import AuditTrailAgent
from agents_b2g.ethical_boundary.audit_trail_writer import AuditTrailWriter, AuditTrailWriterFactory
from agents_b2g.ethical_boundary.subagents.charter.air_gap_validator import AirGapValidator
from agents_b2g.ethical_boundary.prereg_firewall_agent import PreRegFirewallAgent
from agents_b2g.ethical_boundary.defensive_scope_certifier import DefensiveScopeCertifier
from agents_b2g.ethical_boundary.boundary_violation_reporter import BoundaryViolationReporter
from agents_b2g.ethical_boundary.integrity_violation_detector import IntegrityViolationDetector
from agents_b2g.ethical_boundary.subagents.certifier.types import CertificationContext
from agents_b2g.ethical_boundary.orchestrator import EthicalBoundaryOrchestrator
from agents_b2g.ethical_boundary.scope_enforcer_agent import ScopeEnforcerAgent
from agents_b2g.ethical_boundary.types import (
    EthicalBoundaryEnvelope,
    EthicalBoundaryException,
    EthicalVerdict,
    NonExtractionAssertion,
    ScopeFlag,
    SCOPE_DEFENSIVE,
    ViolationObservation,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
    attach_scope_flag,
    blocked_envelope,
    certified_envelope,
    check_charter_airgap,
    check_non_extraction,
    should_block,
    validate_ethical_envelope,
    validate_scope_immutable,
)


class TestTypesAndEnvelope(unittest.TestCase):
    def test_scope_flag_frozen(self) -> None:
        flag = attach_scope_flag({"x": 1}, attached_by="test")
        self.assertEqual(flag.scope, SCOPE_DEFENSIVE)
        with self.assertRaises(FrozenInstanceError):
            flag.scope = "OTHER"  # type: ignore[misc]

    def test_block_cause_ethical_boundary_enum(self) -> None:
        self.assertEqual(BlockCause.ETHICAL_BOUNDARY.value, "ETHICAL_BOUNDARY")
        self.assertIsInstance(BlockCause.ETHICAL_BOUNDARY, BlockCause)

    def test_certified_envelope_valid(self) -> None:
        scope = attach_scope_flag({"a": 1}, attached_by="test")
        cid = DefensiveScopeCertifier._certificate_id("j1", scope)
        env = certified_envelope(job_id="j1", scope=scope, certificate_id=cid)
        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        self.assertEqual(env.certificate_id, cid)
        self.assertIsNone(env.block_cause)
        self.assertEqual(validate_ethical_envelope(env), [])
        self.assertEqual(env.to_dict()["certificate_id"], cid)

    def test_blocked_envelope_requires_ethical_boundary_cause(self) -> None:
        scope = attach_scope_flag({}, attached_by="test")
        env = blocked_envelope(
            job_id="j2",
            scope=scope,
            violations=(
                ViolationRecord(
                    violation_type=ViolationType.PROFIT_EXTRACTION,
                    severity=ViolationSeverity.critical(),
                    source_agent="EthicalAssertionAgent",
                    message="test",
                ),
            ),
        )
        self.assertEqual(env.block_cause, BlockCause.ETHICAL_BOUNDARY)
        self.assertEqual(validate_ethical_envelope(env), [])

    def test_violation_severity_bounds(self) -> None:
        ViolationSeverity(0)
        ViolationSeverity(100)
        with self.assertRaises(ValueError):
            ViolationSeverity(101)

    def test_blocking_threshold_from_config(self) -> None:
        self.assertEqual(ViolationSeverity.blocking_threshold(), ETHICAL_BLOCKING_SEVERITY_THRESHOLD)
        self.assertEqual(ETHICAL_BLOCKING_SEVERITY_THRESHOLD, 50)
        self.assertFalse(ViolationSeverity(49).is_blocking())
        self.assertTrue(ViolationSeverity(50).is_blocking())

    def test_severity_49_non_auto_block_does_not_trigger_should_block(self) -> None:
        v = ViolationRecord(
            violation_type=ViolationType.ASSERTION_FAILURE,
            severity=ViolationSeverity(49),
            source_agent="test",
            message="sub-threshold",
        )
        self.assertFalse(v.is_auto_block())
        self.assertFalse(should_block((v,)))

    def test_prereg_negation_always_auto_blocks(self) -> None:
        v = ViolationRecord(
            violation_type=ViolationType.PREREG_NEGATION,
            severity=ViolationSeverity(49),
            source_agent="test",
            message="§1.0.E hard block",
        )
        self.assertTrue(v.is_auto_block())
        self.assertTrue(should_block((v,)))

    def test_offensive_marker_registry_covers_charter(self) -> None:
        refs = OFFENSIVE_MARKER_REGISTRY.charter_refs
        self.assertIn("MEV_EXTRACTION", refs)
        self.assertEqual(refs["MEV_EXTRACTION"], "§1.0.E(a)")
        self.assertEqual(len(OFFENSIVE_MARKER_REGISTRY.covers_charter_negation()), 5)

    def test_scope_flag_from_dict_rejects_injection(self) -> None:
        valid = attach_scope_flag({"x": 1}, attached_by="test").to_dict()
        ScopeFlag.from_dict(valid)
        bad = dict(valid)
        bad["scope"] = "OFFENSIVE"
        with self.assertRaises(ValueError):
            ScopeFlag.from_dict(bad)
        with_extra = dict(valid)
        with_extra["execute"] = True
        with self.assertRaises(ValueError):
            ScopeFlag.from_dict(with_extra)

    def test_envelope_from_dict_revalidates_scope(self) -> None:
        scope = attach_scope_flag({"k": "v"}, attached_by="test")
        env = certified_envelope(
            job_id="jd",
            scope=scope,
            certificate_id=DefensiveScopeCertifier._certificate_id("jd", scope),
        )
        raw = env.to_dict()
        raw["scope"]["scope"] = "TAMPERED"
        with self.assertRaises(ValueError):
            EthicalBoundaryEnvelope.from_dict(raw)


class TestFailClosed(unittest.TestCase):
    def setUp(self) -> None:
        self.orch = EthicalBoundaryOrchestrator(user_id="test-failclosed")

    def test_disabled_env_rejected_at_config_load(self) -> None:
        with mock.patch.dict(os.environ, {"ETHICAL_ASSERTION_ENABLED": "false"}):
            with self.assertRaises(EthicalBoundaryConfigError):
                EthicalBoundaryConfig.load()

    def test_missing_charter_rejects_start(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AGENT_X_CHARTER_PATH": "/nonexistent/AGENT_X_CHARTER.md"},
        ):
            with self.assertRaises(EthicalBoundaryConfigError):
                EthicalBoundaryConfig.load()

    def test_unexpected_exception_blocks(self) -> None:
        with mock.patch.object(
            PreRegFirewallAgent,
            "enforce",
            side_effect=RuntimeError("boom"),
        ):
            env = self.orch.enforce({}, job_id="fault")
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)
        self.assertEqual(env.block_cause, BlockCause.ETHICAL_BOUNDARY)

    def test_ethical_boundary_exception_blocks(self) -> None:
        exc = EthicalBoundaryException(
            "assertion failed",
            violation_type=ViolationType.ASSERTION_FAILURE,
            agent="EthicalAssertionAgent",
        )
        with mock.patch.object(
            EthicalAssertionAgent,
            "assert_non_extraction",
            side_effect=exc,
        ):
            env = self.orch.enforce({}, job_id="exc")
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)


class TestNonExtractionAssertion(unittest.TestCase):
    def test_offensive_metadata_blocks(self) -> None:
        assertion = NonExtractionAssertion(
            receiver_id="r1",
            allowed_purposes=("RISK_MANAGEMENT",),
            metadata={"purposes": ["MEV_EXTRACTION"]},
        )
        hit = check_non_extraction(assertion)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.violation_type, ViolationType.PROFIT_EXTRACTION)

    def test_orchestrator_blocks_extraction_metadata(self) -> None:
        orch = EthicalBoundaryOrchestrator(user_id="test-extraction")
        env = orch.enforce(
            {
                "receiver_metadata": {
                    "receiver_id": "bad",
                    "allowed_purposes": ["RISK_MANAGEMENT"],
                    "purposes": ["SANDWICH_ATTACK"],
                }
            },
            job_id="extract",
        )
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)


class TestScopeTampering(unittest.TestCase):
    def test_scope_tamper_detected(self) -> None:
        scope = attach_scope_flag({"k": "v"}, attached_by="ScopeEnforcerAgent")
        payload = {"k": "v", "scope": "OFFENSIVE"}
        hit = validate_scope_immutable(payload, scope)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.violation_type, ViolationType.SCOPE_TAMPER)


class TestWave28Descriptive(unittest.TestCase):
    def test_violation_observation_rejects_kwargs_action_fields(self) -> None:
        with self.assertRaises(TypeError):
            ViolationObservation(
                signature="x",
                severity=ViolationSeverity(10),
                timestamp_utc="2026-08-23T12:00:00+00:00",
                source_agent="BoundaryViolationReporter",
                execute=True,  # type: ignore[call-arg]
            )

    def test_violation_observation_from_dict_rejects_action_fields(self) -> None:
        with self.assertRaises(ValueError):
            ViolationObservation.from_dict(
                {
                    "signature": "x",
                    "severity": {"value": 10},
                    "timestamp_utc": "2026-08-23T12:00:00+00:00",
                    "source_agent": "BoundaryViolationReporter",
                    "countermeasure": "ban",
                }
            )

    def test_violation_observation_has_no_action_fields(self) -> None:
        obs = ViolationObservation(
            signature="PROFIT_EXTRACTION:EthicalAssertionAgent",
            severity=ViolationSeverity.critical(),
            timestamp_utc="2026-08-23T12:00:00+00:00",
            source_agent="BoundaryViolationReporter",
        )
        data = obs.to_dict()
        forbidden = {"execute", "respond", "countermeasure", "action", "route"}
        self.assertFalse(forbidden.intersection(data.keys()))
        self.assertEqual(set(data.keys()), {"signature", "severity", "timestamp_utc", "source_agent"})

    def test_blocked_envelope_wave28_observations_descriptive_only(self) -> None:
        scope = attach_scope_flag({}, attached_by="test")
        env = blocked_envelope(
            job_id="w28",
            scope=scope,
            violations=(
                ViolationRecord(
                    violation_type=ViolationType.CHARTER_AIRGAP,
                    severity=ViolationSeverity.critical(),
                    source_agent="CharterEnforcerAgent",
                    message="airgap",
                ),
            ),
        )
        for obs in env.wave28_observations:
            keys = set(obs.to_dict().keys())
            self.assertFalse({"execute", "respond", "countermeasure"} & keys)


class TestScopeEnforcerAgent(unittest.TestCase):
    def test_attach_and_propagate_scope(self) -> None:
        agent = ScopeEnforcerAgent(user_id="test-scope")
        result = agent.enforce({"data": 1}, job_id="j-scope")
        self.assertEqual(result.scope.scope, SCOPE_DEFENSIVE)
        self.assertEqual(result.scoped_payload["scope"], SCOPE_DEFENSIVE)
        self.assertEqual(result.scoped_payload["ethical_boundary_job_id"], "j-scope")

    def test_pre_injected_bad_scope_blocks(self) -> None:
        agent = ScopeEnforcerAgent(user_id="test-scope")
        result = agent.enforce({"scope": "OFFENSIVE"}, job_id="j-bad")
        self.assertTrue(result.violations)
        self.assertEqual(result.violations[0].violation_type, ViolationType.SCOPE_TAMPER)


class TestEthicalAssertionAgent(unittest.TestCase):
    def test_requires_agent3_scope(self) -> None:
        scope_agent = ScopeEnforcerAgent(user_id="test-assert")
        scope_result = scope_agent.enforce({}, job_id="j1")
        assertion_agent = EthicalAssertionAgent(user_id="test-assert")
        result = assertion_agent.assert_non_extraction(
            scope_result.scoped_payload,
            scope=scope_result.scope,
        )
        self.assertFalse(result.violations)

    def test_agent3_output_required_for_agent2(self) -> None:
        scope_agent = ScopeEnforcerAgent(user_id="test-assert")
        scope_result = scope_agent.enforce({"receiver_metadata": {"receiver_id": "r"}}, job_id="j2")
        assertion_agent = EthicalAssertionAgent(user_id="test-assert")
        result = assertion_agent.assert_non_extraction(
            scope_result.scoped_payload,
            scope=scope_result.scope,
        )
        self.assertFalse(result.violations)
        self.assertTrue(result.assertion_ran)

    def test_blocks_without_defensive_scope_in_payload(self) -> None:
        scope = attach_scope_flag({}, attached_by="ScopeEnforcerAgent")
        assertion_agent = EthicalAssertionAgent(user_id="test-assert")
        result = assertion_agent.assert_non_extraction({}, scope=scope)
        self.assertTrue(result.violations)
        self.assertEqual(result.violations[0].violation_type, ViolationType.SCOPE_TAMPER)


class TestCharterAirGapRegression(unittest.TestCase):
    """Documented regression matrix — wrapper and Agent 6 must stay identical."""

    CASES: tuple[tuple[dict[str, Any], bool], ...] = (
        ({"execution_targets": ["titan-vault-router"]}, True),
        ({"routing_targets": ["profit-optimizer-main"]}, True),
        ({"execution_targets": ["offensive-searcher-bot"]}, True),
        ({"execution_targets": ["gnosis-safe-router"]}, False),
        ({"run_input": {"seed": 1}}, False),
    )

    def test_check_charter_airgap_regression_matrix(self) -> None:
        for payload, should_block in self.CASES:
            hit = check_charter_airgap(payload)
            if should_block:
                self.assertIsNotNone(hit, payload)
                assert hit is not None
                self.assertEqual(hit.violation_type, ViolationType.CHARTER_AIRGAP)
            else:
                self.assertIsNone(hit, payload)

    def test_air_gap_validator_matches_wrapper(self) -> None:
        validator = AirGapValidator()
        for payload, should_block in self.CASES:
            wrapped = check_charter_airgap(payload)
            direct = validator.validate(payload)
            self.assertEqual(wrapped, direct, payload)

    def test_charter_enforcer_agent_matches_air_gap(self) -> None:
        agent = CharterEnforcerAgent(user_id="test-charter-reg")
        for payload, should_block in self.CASES:
            result = agent.enforce(payload, job_id="reg")
            air_gap_hits = [
                v for v in result.violations if v.violation_type == ViolationType.CHARTER_AIRGAP
            ]
            if should_block:
                self.assertTrue(air_gap_hits, payload)
            else:
                self.assertFalse(
                    any(
                        v.source_agent == "CharterEnforcerAgent"
                        for v in air_gap_hits
                    ),
                    payload,
                )


class TestCharterEnforcerAgent(unittest.TestCase):
    def test_name_inheritance_blocks_unacknowledged_claim(self) -> None:
        agent = CharterEnforcerAgent(user_id="test-charter-agent")
        result = agent.enforce(
            {"claims_agent_x_identity": True},
            job_id="name-inherit",
        )
        self.assertTrue(result.violations)
        self.assertTrue(
            any("identity claimed" in v.message for v in result.violations)
        )

    def test_charter_audit_events_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                audit = AuditTrailAgent(user_id="test-charter-audit").begin_audit(
                    {},
                    job_id="charter-audit",
                    completed_stages=("PreRegFirewallAgent",),
                )
                assert audit.writer is not None
                agent = CharterEnforcerAgent(user_id="test-charter-audit")
                agent.enforce(
                    {"run_input": {"seed": 1}},
                    job_id="charter-audit",
                    audit_writer=audit.writer,
                )
                events = [
                    json.loads(line)["event"]
                    for line in audit.writer.audit_path.read_text().splitlines()
                ]
        self.assertIn("air_gap_check_pass", events)
        self.assertIn("name_inheritance_check_pass", events)
        self.assertIn("charter_enforcement_pass", events)


class TestCharterAirGap(unittest.TestCase):
    def test_profit_system_reference_blocks(self) -> None:
        hit = check_charter_airgap({"execution_targets": ["titan-vault-router"]})
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.violation_type, ViolationType.CHARTER_AIRGAP)

    def test_orchestrator_blocks_charter_airgap_after_agent1(self) -> None:
        """Agent 6 module blocks profit-system targets after Pre-Reg passes."""
        orch = EthicalBoundaryOrchestrator(user_id="test-charter")
        env = orch.enforce(
            {"execution_targets": ["titan-vault-router"]},
            job_id="charter",
        )
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)
        self.assertTrue(
            any(v.violation_type == ViolationType.CHARTER_AIRGAP for v in env.violations)
        )


class TestIntegrityViolationDetector(unittest.TestCase):
    """Output-side integrity detection — complements Agent 1/2 input guards."""

    BLOCK_CASES: tuple[tuple[dict[str, Any], ViolationType], ...] = (
        ({"uses_causal_signal_for_profit": True}, ViolationType.PROFIT_EXTRACTION),
        ({"liquidation_mode": "offensive"}, ViolationType.OFFENSIVE_EXECUTION),
        ({"sandwich_bundle": True}, ViolationType.OFFENSIVE_EXECUTION),
        (
            {
                "execution_calls": [
                    {"purpose": "MEV_EXTRACTION", "target": "vault-router"},
                ],
            },
            ViolationType.PROFIT_EXTRACTION,
        ),
        (
            {
                "execution_calls": [
                    {"purpose": "FRONTRUNNING"},
                    {"purpose": "BACKRUNNING"},
                ],
            },
            ViolationType.OFFENSIVE_EXECUTION,
        ),
    )

    PASS_CASES: tuple[dict[str, Any], ...] = (
        {"run_input": {"seed": 1}},
        {"execution_calls": [{"purpose": "OBSERVATION_ONLY", "target": "risk-monitor"}]},
    )

    def test_integrity_regression_matrix(self) -> None:
        agent = IntegrityViolationDetector(user_id="test-integrity-reg")
        for payload, expected_type in self.BLOCK_CASES:
            result = agent.enforce(payload, job_id="reg-block")
            self.assertTrue(result.violations, payload)
            self.assertTrue(
                any(v.violation_type == expected_type for v in result.violations),
                (payload, result.violations),
            )
            for record in result.violations:
                self.assertTrue(record.is_auto_block(), record)

    def test_integrity_pass_cases(self) -> None:
        agent = IntegrityViolationDetector(user_id="test-integrity-pass")
        for payload in self.PASS_CASES:
            result = agent.enforce(payload, job_id="reg-pass")
            self.assertFalse(result.violations, payload)

    def test_integrity_audit_events_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                audit = AuditTrailAgent(user_id="test-integrity-audit").begin_audit(
                    {},
                    job_id="integrity-audit",
                    completed_stages=("PreRegFirewallAgent",),
                )
                assert audit.writer is not None
                agent = IntegrityViolationDetector(user_id="test-integrity-audit")
                agent.enforce(
                    {"uses_causal_signal_for_profit": True},
                    job_id="integrity-audit",
                    audit_writer=audit.writer,
                )
                events = [
                    json.loads(line)["event"]
                    for line in audit.writer.audit_path.read_text().splitlines()
                ]
        self.assertIn("integrity_detection_start", events)
        self.assertIn("integrity_violation_detected", events)

    def test_integrity_fault_fail_closed(self) -> None:
        agent = IntegrityViolationDetector(user_id="test-integrity-fault")
        with mock.patch.object(
            agent._scorer,
            "score",
            side_effect=RuntimeError("scorer fault"),
        ):
            result = agent.enforce({"run_input": {"seed": 1}}, job_id="fault")
        self.assertTrue(result.violations)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.PIPELINE_FAULT
                and "IntegrityViolationDetector" in v.message
                for v in result.violations
            )
        )

    def test_orchestrator_blocks_integrity_before_reporter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-integrity-orch")
                env = orch.enforce(
                    {"uses_causal_signal_for_profit": True},
                    job_id="integrity-block",
                )
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.PROFIT_EXTRACTION
                and v.source_agent == "IntegrityViolationDetector"
                for v in env.violations
            ),
            env.violations,
        )
        self.assertFalse(
            any(
                v.violation_type == ViolationType.PIPELINE_FAULT
                and "BoundaryViolationReporter" in v.message
                for v in env.violations
            ),
            "integrity violation must block before reporter",
        )


class TestBoundaryViolationReporter(unittest.TestCase):
    """Agent 7 — aggregation, ranking, descriptive Wave 28 escalation."""

    def _sample_violations(self) -> tuple[ViolationRecord, ...]:
        return (
            ViolationRecord(
                violation_type=ViolationType.CHARTER_AIRGAP,
                severity=ViolationSeverity(60),
                source_agent="CharterEnforcerAgent",
                message="airgap hit",
            ),
            ViolationRecord(
                violation_type=ViolationType.PROFIT_EXTRACTION,
                severity=ViolationSeverity.critical(),
                source_agent="IntegrityViolationDetector",
                message="profit route",
            ),
            ViolationRecord(
                violation_type=ViolationType.PROFIT_EXTRACTION,
                severity=ViolationSeverity.critical(),
                source_agent="IntegrityViolationDetector",
                message="profit route",
            ),
        )

    def test_aggregator_dedupes_violations(self) -> None:
        reporter = BoundaryViolationReporter(user_id="test-reporter-agg")
        result = reporter.enforce(self._sample_violations(), job_id="agg")
        self.assertEqual(len(result.report.violations), 2)
        self.assertEqual(result.report.summary["total"], 2)

    def test_ranker_orders_by_severity(self) -> None:
        reporter = BoundaryViolationReporter(user_id="test-reporter-rank")
        result = reporter.enforce(self._sample_violations(), job_id="rank")
        ranked = result.report.ranked_violations
        self.assertEqual(ranked[0].violation_type, ViolationType.PROFIT_EXTRACTION)
        self.assertGreaterEqual(ranked[0].severity.value, ranked[1].severity.value)

    def test_escalation_uses_sha256_signature_and_source_agent(self) -> None:
        reporter = BoundaryViolationReporter(user_id="test-reporter-esc")
        violations = self._sample_violations()
        result = reporter.enforce(violations, job_id="esc")
        self.assertEqual(len(result.report.wave28_observations), 2)
        source = violations[1]
        expected_sig = hashlib.sha256(
            json.dumps(source.to_dict(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        obs = next(
            o for o in result.report.wave28_observations if o.source_agent == source.source_agent
        )
        self.assertEqual(obs.signature, expected_sig)
        self.assertEqual(obs.source_agent, "IntegrityViolationDetector")
        forbidden = {"execute", "respond", "countermeasure", "action", "route"}
        self.assertFalse(forbidden.intersection(obs.to_dict().keys()))

    def test_clean_report_produces_no_fault_violations(self) -> None:
        reporter = BoundaryViolationReporter(user_id="test-reporter-clean")
        result = reporter.enforce((), job_id="clean-report")
        self.assertFalse(result.violations)
        self.assertEqual(result.report.summary["total"], 0)
        self.assertEqual(result.report.wave28_observations, ())

    def test_reporter_audit_events_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                audit = AuditTrailAgent(user_id="test-reporter-audit").begin_audit(
                    {},
                    job_id="reporter-audit",
                    completed_stages=("PreRegFirewallAgent",),
                )
                assert audit.writer is not None
                reporter = BoundaryViolationReporter(user_id="test-reporter-audit")
                reporter.enforce(self._sample_violations(), job_id="reporter-audit", audit_writer=audit.writer)
                events = [
                    json.loads(line)["event"]
                    for line in audit.writer.audit_path.read_text().splitlines()
                ]
        self.assertIn("violation_report_start", events)
        self.assertIn("violation_report_complete", events)

    def test_reporter_fault_fail_closed(self) -> None:
        reporter = BoundaryViolationReporter(user_id="test-reporter-fault")
        with mock.patch.object(
            reporter._escalator,
            "escalate",
            side_effect=RuntimeError("escalation fault"),
        ):
            result = reporter.enforce(self._sample_violations(), job_id="fault")
        self.assertTrue(result.violations)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.PIPELINE_FAULT
                and "BoundaryViolationReporter" in v.message
                for v in result.violations
            )
        )

    def test_orchestrator_clean_payload_certified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-reporter-orch")
                env = orch.enforce({"run_input": {"seed": 1}}, job_id="clean-cert")
        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        self.assertIsNone(env.block_cause)
        self.assertEqual(len(env.prereg_hashes), 3)
        self.assertEqual(validate_ethical_envelope(env), [])


class TestDefensiveScopeCertifier(unittest.TestCase):
    """Agent 8 — positive certification gate."""

    def _clean_context(self) -> CertificationContext:
        return CertificationContext(
            prior_violations=(),
            prereg_validated_hashes={"spec": "a", "prereg": "b", "charter": "c"},
            charter_version="1.0",
            prereg_stage_passed=True,
            charter_stage_passed=True,
        )

    def test_clean_payload_certified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                scope_agent = ScopeEnforcerAgent(user_id="test-cert")
                scope_result = scope_agent.enforce({"run_input": {"seed": 1}}, job_id="cert")
                audit = AuditTrailAgent(user_id="test-cert").begin_audit(
                    scope_result.scoped_payload,
                    job_id="cert",
                    completed_stages=("PreRegFirewallAgent",),
                )
                assert audit.writer is not None
                certifier = DefensiveScopeCertifier(user_id="test-cert")
                result = certifier.certify(
                    scope_result.scoped_payload,
                    scope=scope_result.scope,
                    job_id="cert",
                    context=self._clean_context(),
                    audit_writer=audit.writer,
                )
        self.assertTrue(result.certified)
        self.assertFalse(result.violations)
        self.assertIsNotNone(result.certificate_id)

    def test_scope_tamper_blocks_certification(self) -> None:
        scope = attach_scope_flag({"run_input": {"seed": 1}}, attached_by="ScopeEnforcerAgent")
        payload = {"run_input": {"seed": 1}, "scope": "OFFENSIVE"}
        certifier = DefensiveScopeCertifier(user_id="test-cert-scope")
        result = certifier.certify(
            payload,
            scope=scope,
            job_id="tamper",
            context=self._clean_context(),
        )
        self.assertFalse(result.certified)
        self.assertTrue(
            any(v.violation_type == ViolationType.SCOPE_TAMPER for v in result.violations)
        )

    def test_open_violations_block_certification(self) -> None:
        scope = attach_scope_flag({}, attached_by="test")
        certifier = DefensiveScopeCertifier(user_id="test-cert-open")
        context = CertificationContext(
            prior_violations=(
                ViolationRecord(
                    violation_type=ViolationType.PROFIT_EXTRACTION,
                    severity=ViolationSeverity.critical(),
                    source_agent="IntegrityViolationDetector",
                    message="open",
                ),
            ),
            prereg_validated_hashes={"spec": "a"},
            charter_version="1.0",
            prereg_stage_passed=True,
            charter_stage_passed=True,
        )
        result = certifier.certify({}, scope=scope, job_id="open", context=context)
        self.assertFalse(result.certified)
        self.assertTrue(
            any("open violations" in v.message for v in result.violations)
        )

    def test_offensive_output_blocks_certification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                scope_agent = ScopeEnforcerAgent(user_id="test-cert-out")
                scope_result = scope_agent.enforce(
                    {"uses_causal_signal_for_profit": True},
                    job_id="out",
                )
                certifier = DefensiveScopeCertifier(user_id="test-cert-out")
                result = certifier.certify(
                    scope_result.scoped_payload,
                    scope=scope_result.scope,
                    job_id="out",
                    context=self._clean_context(),
                )
        self.assertFalse(result.certified)
        self.assertTrue(
            any(v.violation_type == ViolationType.ASSERTION_FAILURE for v in result.violations)
        )

    def test_prereg_reference_without_hashes_blocks(self) -> None:
        scope = attach_scope_flag({}, attached_by="test")
        certifier = DefensiveScopeCertifier(user_id="test-cert-prereg")
        context = CertificationContext(
            prior_violations=(),
            prereg_validated_hashes={},
            charter_version="1.0",
            prereg_stage_passed=True,
            charter_stage_passed=True,
        )
        result = certifier.certify({}, scope=scope, job_id="prereg", context=context)
        self.assertFalse(result.certified)
        self.assertTrue(
            any("pre-reg hashes" in v.message for v in result.violations)
        )

    def test_certifier_fault_fail_closed(self) -> None:
        scope = attach_scope_flag({}, attached_by="test")
        certifier = DefensiveScopeCertifier(user_id="test-cert-fault")
        with mock.patch.object(
            certifier._scope_certifier,
            "certify",
            side_effect=RuntimeError("certifier fault"),
        ):
            result = certifier.certify(
                {"scope": SCOPE_DEFENSIVE},
                scope=scope,
                job_id="fault",
                context=self._clean_context(),
            )
        self.assertFalse(result.certified)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.PIPELINE_FAULT
                and "DefensiveScopeCertifier" in v.message
                for v in result.violations
            )
        )

    def test_orchestrator_e2e_certified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-e2e-cert")
                env = orch.enforce({"run_input": {"seed": 42}}, job_id="e2e-certified")
        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        self.assertEqual(env.scope.scope, SCOPE_DEFENSIVE)
        self.assertEqual(len(env.prereg_hashes), 3)
        self.assertIsNotNone(env.certified_at)


class TestSkeletonStageInvariant(unittest.TestCase):
    """Pipeline must never fail-open — certification faults block."""

    def test_certifier_pipeline_fault_blocks(self) -> None:
        orch = EthicalBoundaryOrchestrator(user_id="test-fail-closed")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                with mock.patch.object(
                    orch.scope_certifier,
                    "certify",
                    side_effect=RuntimeError("unexpected"),
                ):
                    env = orch.enforce({"run_input": {"seed": 1}}, job_id="fault")
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)


class TestSkeletonFailClosed(unittest.TestCase):
    """Fail-closed invariants after full pipeline implementation."""

    def setUp(self) -> None:
        self.orch = EthicalBoundaryOrchestrator(user_id="test-skeleton")

    def test_clean_payload_certified_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-skeleton")
                env = orch.enforce({"run_input": {"seed": 1}}, job_id="clean")
        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        self.assertEqual(len(env.prereg_hashes), 3)

    def test_offensive_marker_blocked_at_agent1(self) -> None:
        env = self.orch.enforce(
            {"purposes": ["MEV_EXTRACTION"]},
            job_id="offensive-prereg",
        )
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)
        self.assertTrue(
            any(v.violation_type == ViolationType.PREREG_NEGATION for v in env.violations)
        )


class TestAuditTrailAgent(unittest.TestCase):
    def test_gobd_hash_chain_and_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                agent = AuditTrailAgent(user_id="test-audit")
                result = agent.begin_audit(
                    {"run_input": {"seed": 1}},
                    job_id="audit-chain",
                    completed_stages=(
                        "PreRegFirewallAgent",
                        "ScopeEnforcerAgent",
                        "EthicalAssertionAgent",
                    ),
                )
                self.assertFalse(result.violations)
                assert result.writer is not None
                self.assertGreaterEqual(result.entries_written, 4)
                ok, err = result.writer.verify_chain()
                self.assertTrue(ok, err)
                lines = result.writer.audit_path.read_text(encoding="utf-8").strip().splitlines()
                first = json.loads(lines[0])
                self.assertEqual(first["prev_hash"], AUDIT_GENESIS_HASH)
                self.assertEqual(first["purpose"], AUDIT_PURPOSE_OBSERVATION_AND_DEFENSE)
                self.assertIn("entry_hash", first)

    def test_audit_write_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_dir = Path(tmp) / "test-audit-fail" / "ethical_boundary" / "audit"
            audit_dir.mkdir(parents=True)
            audit_file = audit_dir / "blocked-job.jsonl"
            audit_file.write_text("{not-json", encoding="utf-8")
            with mock.patch.object(
                AuditTrailWriterFactory,
                "open",
                side_effect=lambda job_id: AuditTrailWriter(
                    job_id=job_id,
                    user_id="test-audit-fail",
                    audit_path=audit_file,
                ),
            ):
                with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                    agent = AuditTrailAgent(user_id="test-audit-fail")
                    result = agent.begin_audit(
                        {},
                        job_id="blocked-job",
                        completed_stages=("PreRegFirewallAgent",),
                    )
        self.assertTrue(result.violations)
        self.assertIsNone(result.writer)
        self.assertTrue(
            any(v.violation_type == ViolationType.PIPELINE_FAULT for v in result.violations)
        )

    def test_orchestrator_writes_audit_for_downstream_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-audit-orch")
                env = orch.enforce({"run_input": {"seed": 1}}, job_id="audit-orch")
                audit_path = (
                    Path(tmp)
                    / "test-audit-orch"
                    / "ethical_boundary"
                    / "audit"
                    / "audit-orch.jsonl"
                )
                self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
                self.assertTrue(audit_path.is_file())
                events = [json.loads(line)["event"] for line in audit_path.read_text().splitlines()]
                self.assertIn("pipeline_audit_start", events)
                self.assertIn("integrity_detection_pass", events)
                self.assertIn("violation_report_complete", events)
                self.assertIn("certification_pass", events)


class TestPreRegFirewallAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = PreRegFirewallAgent(user_id="test-prereg")

    def test_valid_prereg_passes_subagents(self) -> None:
        result = self.agent.enforce({"run_input": {"seed": 1}}, job_id="prereg-ok")
        self.assertFalse(result.violations)
        self.assertEqual(len(result.validated_hashes), 3)

    def test_hash_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_registry = Path(tmp) / "bad_hashes.json"
            bad_registry.write_text(
                json.dumps(
                    {
                        "version": "1.0",
                        "hashes": {
                            "bridge_stufe_a_v3": {
                                "path": "docs/BRIDGE_STUFE_A_V3_PREREG.md",
                                "sha256": "0" * 64,
                            },
                            "bridge_diagnostic": {
                                "path": "docs/BRIDGE_DIAGNOSTIC_PREREG.md",
                                "sha256": "0" * 64,
                            },
                            "wave38_live": {
                                "path": "docs/WAVE38_LIVE_PREREG.md",
                                "sha256": "0" * 64,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"ETHICAL_PREREG_HASH_REGISTRY": str(bad_registry)},
            ):
                agent = PreRegFirewallAgent(user_id="test-prereg-bad-hash")
                result = agent.enforce({}, job_id="hash-fail")
        self.assertTrue(result.violations)
        self.assertTrue(
            any(v.violation_type == ViolationType.CONFIG_INTEGRITY for v in result.violations)
        )

    def test_exclusion_enforcer_blocks_marker(self) -> None:
        result = self.agent.enforce(
            {"execution_calls": [{"purpose": "SANDWICH_ATTACK"}]},
            job_id="exclusion",
        )
        self.assertTrue(result.violations)
        self.assertTrue(
            any(v.violation_type == ViolationType.PREREG_NEGATION for v in result.violations)
        )

    def test_negation_bypass_flag_blocks(self) -> None:
        result = self.agent.enforce(
            {"negation_clause_bypass": True},
            job_id="bypass",
        )
        self.assertTrue(result.violations)
        self.assertTrue(
            any("bypass" in v.message.lower() for v in result.violations)
        )


class TestE2EPipeline(unittest.TestCase):
    """Wave 39 formal E2E — Happy-Path, Fail-closed (8 agents), GoBD-Konsistenz."""

    CLEAN_PAYLOAD: dict[str, Any] = {"run_input": {"seed": 1}}

    # Stage labels expected in a clean CERTIFIED audit trail (Agents 4–8 write events).
    REQUIRED_AUDIT_STAGES: frozenset[str] = frozenset(
        {
            "AuditTrailAgent",
            "CharterEnforcerAgent",
            "IntegrityViolationDetector",
            "BoundaryViolationReporter",
            "DefensiveScopeCertifier",
        }
    )

    REQUIRED_AUDIT_EVENTS: frozenset[str] = frozenset(
        {
            "pipeline_audit_start",
            "charter_enforcement_pass",
            "integrity_detection_pass",
            "violation_report_complete",
            "certification_pass",
        }
    )

    def test_clean_payload_certified_full_pipeline(self) -> None:
        """Happy-Path: all eight agents green → CERTIFIED + certificate_id."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-e2e")
                env = orch.enforce(self.CLEAN_PAYLOAD, job_id="clean")
                audit_path = (
                    Path(tmp)
                    / "test-e2e"
                    / "ethical_boundary"
                    / "audit"
                    / "clean.jsonl"
                )
                entries = [
                    json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()
                ]
        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        self.assertEqual(env.scope.scope, SCOPE_DEFENSIVE)
        self.assertIsNotNone(env.certified_at)
        self.assertEqual(len(env.prereg_hashes), 3)
        self.assertEqual(env.block_cause, None)
        self.assertFalse(env.violations)
        self.assertEqual(validate_ethical_envelope(env), [])

        cert_events = [e for e in entries if e.get("event") == "certification_pass"]
        self.assertEqual(len(cert_events), 1, entries)
        certificate_id = cert_events[0]["details"]["certificate_id"]
        self.assertEqual(len(certificate_id), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in certificate_id))
        expected_id = DefensiveScopeCertifier._certificate_id("clean", env.scope)
        self.assertEqual(certificate_id, expected_id)
        # Envelope is self-contained — same id as GoBD audit trail
        self.assertEqual(env.certificate_id, certificate_id)
        self.assertEqual(env.to_dict()["certificate_id"], certificate_id)

    def test_mock_violation_full_pipeline_blocked(self) -> None:
        orch = EthicalBoundaryOrchestrator(user_id="test-e2e")
        env = orch.enforce(
            {"purposes": ["MEV_EXTRACTION"]},
            job_id="mock-violation",
        )
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)
        self.assertEqual(env.block_cause, BlockCause.ETHICAL_BOUNDARY)
        self.assertTrue(
            any(v.violation_type == ViolationType.PREREG_NEGATION for v in env.violations)
        )

    def test_fail_closed_each_agent_blocks_on_internal_fault(self) -> None:
        """Each of the eight agents: internal exception → BLOCKED + PIPELINE_FAULT."""
        fault_targets: tuple[tuple[str, str], ...] = (
            ("prereg_firewall", "enforce"),
            ("scope_enforcer", "enforce"),
            ("ethical_assertion", "assert_non_extraction"),
            ("audit_trail", "begin_audit"),
            ("charter_enforcer", "enforce"),
            ("integrity_detector", "enforce"),
            ("violation_reporter", "enforce"),
            ("scope_certifier", "certify"),
        )
        for attr, method in fault_targets:
            with self.subTest(agent=attr, method=method):
                with tempfile.TemporaryDirectory() as tmp:
                    with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                        orch = EthicalBoundaryOrchestrator(user_id=f"e2e-fault-{attr}")
                        with mock.patch.object(
                            getattr(orch, attr),
                            method,
                            side_effect=RuntimeError(f"{attr} internal fault"),
                        ):
                            env = orch.enforce(
                                self.CLEAN_PAYLOAD,
                                job_id=f"fault-{attr}",
                            )
                self.assertEqual(env.status, EthicalVerdict.BLOCKED, (attr, env.violations))
                self.assertEqual(env.block_cause, BlockCause.ETHICAL_BOUNDARY)
                self.assertTrue(
                    any(
                        v.violation_type == ViolationType.PIPELINE_FAULT for v in env.violations
                    ),
                    (attr, env.violations),
                )

    def test_gobd_audit_trail_hash_chain_complete(self) -> None:
        """GoBD: append-only hash chain from GENESIS through certification."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-e2e-gobd")
                env = orch.enforce(self.CLEAN_PAYLOAD, job_id="gobd-chain")
                audit_path = (
                    Path(tmp)
                    / "test-e2e-gobd"
                    / "ethical_boundary"
                    / "audit"
                    / "gobd-chain.jsonl"
                )
                writer = AuditTrailWriter(
                    job_id="gobd-chain",
                    user_id="test-e2e-gobd",
                    audit_path=audit_path,
                )
                ok, err = writer.verify_chain()
                lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
                entries = [json.loads(line) for line in lines]

        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        self.assertTrue(ok, err)
        self.assertGreaterEqual(len(entries), 8)
        self.assertEqual(entries[0]["prev_hash"], AUDIT_GENESIS_HASH)
        for index, entry in enumerate(entries):
            self.assertIn("entry_hash", entry)
            self.assertIn("prev_hash", entry)
            if index == 0:
                continue
            self.assertEqual(entry["prev_hash"], entries[index - 1]["entry_hash"])

    def test_gobd_audit_all_stages_and_purpose_tags(self) -> None:
        """GoBD: all post-audit stages logged; purpose OBSERVATION_AND_DEFENSE everywhere."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-e2e-gobd-stages")
                env = orch.enforce(self.CLEAN_PAYLOAD, job_id="gobd-stages")
                audit_path = (
                    Path(tmp)
                    / "test-e2e-gobd-stages"
                    / "ethical_boundary"
                    / "audit"
                    / "gobd-stages.jsonl"
                )
                entries = [
                    json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()
                ]

        self.assertEqual(env.status, EthicalVerdict.CERTIFIED)
        stages = {e["stage"] for e in entries}
        events = {e["event"] for e in entries}
        self.assertTrue(
            self.REQUIRED_AUDIT_STAGES.issubset(stages),
            f"missing stages: {self.REQUIRED_AUDIT_STAGES - stages}",
        )
        self.assertTrue(
            self.REQUIRED_AUDIT_EVENTS.issubset(events),
            f"missing events: {self.REQUIRED_AUDIT_EVENTS - events}",
        )
        for entry in entries:
            self.assertEqual(
                entry.get("purpose"),
                AUDIT_PURPOSE_OBSERVATION_AND_DEFENSE,
                entry,
            )

    def test_wave28_observations_descriptive_only_on_block(self) -> None:
        """Blocked E2E path: Wave-28 observations carry no action fields."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ETHICAL_BOUNDARY_DATA_ROOT": tmp}):
                orch = EthicalBoundaryOrchestrator(user_id="test-e2e-w28")
                env = orch.enforce(
                    {"uses_causal_signal_for_profit": True},
                    job_id="e2e-integrity-block",
                )
        self.assertEqual(env.status, EthicalVerdict.BLOCKED)
        self.assertTrue(env.wave28_observations)
        forbidden = {"execute", "respond", "countermeasure", "action", "route"}
        for obs in env.wave28_observations:
            keys = set(obs.to_dict().keys())
            self.assertFalse(forbidden & keys)
            self.assertEqual(
                keys, {"signature", "severity", "timestamp_utc", "source_agent"}
            )


class TestWave38Hook(unittest.TestCase):
    """Gatekeeper × Wave 39 — additive hook with byte-identical compliance regression."""

    RUN_INPUT = {"user_id": "test-hook", "options": {"seed": 42, "prereg_version": "hook-test"}}

    def _meta(self, agent: GatekeeperDispatcherAgent, job_id: str, **kwargs: Any) -> dict[str, Any]:
        result = agent.run(self.RUN_INPUT, job_id, **kwargs)
        self.assertEqual(result["status"], "completed", result.get("error"))
        return result["artifacts"][0]["metadata"]

    def test_regression_byte_identical_released_without_hook(self) -> None:
        """Methodical RELEASED path: compare via regression normalizer only (§5.4)."""
        baseline = GatekeeperDispatcherAgent(user_id="test-hook")
        with_hook = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="certified"),
        )
        for job_id in ("reg-rel-1", "reg-rel-2"):
            m0 = self._meta(baseline, job_id)
            m1 = self._meta(with_hook, job_id)
            # Production path with hook MUST retain ethical_boundary (not stripped)
            self.assertIn("ethical_boundary", m1)
            self.assertEqual(m1["ethical_boundary"]["status"], "CERTIFIED")
            # Regression compare strips additive markers — methodical identity only
            self.assertEqual(
                normalize_envelope_metadata_for_regression(m0),
                normalize_envelope_metadata_for_regression(m1),
            )

    def test_regression_byte_identical_blocked_without_hook(self) -> None:
        """Methodical BLOCKED path: normalize for regression; keep markers in artifact."""
        baseline = GatekeeperDispatcherAgent(user_id="test-hook")
        with_hook = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="certified"),
        )
        kwargs = {
            "verdict": DiagnosticVerdict.DIAG_FILTER_ARTIFACT,
            "cause": BlockCause.FILTER_ARTIFACT,
        }
        m0 = self._meta(baseline, "reg-blk", **kwargs)
        m1 = self._meta(with_hook, "reg-blk", **kwargs)
        self.assertIn("ethical_boundary", m1)
        self.assertEqual(m1["ethical_boundary"]["status"], "CERTIFIED")
        self.assertEqual(
            normalize_envelope_metadata_for_regression(m0),
            normalize_envelope_metadata_for_regression(m1),
        )

    def test_production_certified_retains_markers_normalize_is_regression_only(
        self,
    ) -> None:
        """Production metadata keeps ethical_boundary; normalizer must not mutate it."""
        agent = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="certified"),
        )
        meta = self._meta(
            agent,
            "prod-certified-markers",
            verdict=DiagnosticVerdict.DIAG_INCONCLUSIVE,
            cause=BlockCause.INCONCLUSIVE,
        )
        self.assertIn("ethical_boundary", meta)
        self.assertEqual(meta["ethical_boundary"]["status"], "CERTIFIED")
        self.assertEqual(
            meta["ethical_boundary"]["scope"]["scope"],
            "DEFENSIVE_CAUSAL_GROUNDING",
        )
        self.assertTrue(meta["ethical_boundary"].get("certificate_id"))
        self.assertEqual(len(meta["ethical_boundary"]["certificate_id"]), 64)
        before = json.dumps(meta, sort_keys=True)
        _ = normalize_envelope_metadata_for_regression(meta)
        after = json.dumps(meta, sort_keys=True)
        self.assertEqual(before, after, "normalizer must not mutate production dict")
        self.assertIn("ethical_boundary", meta)
        normalized = json.loads(normalize_envelope_metadata_for_regression(meta))
        self.assertNotIn("ethical_boundary", normalized)

    def test_violation_ethical_beats_signal_valid(self) -> None:
        agent = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="blocked"),
        )
        meta = self._meta(
            agent,
            "viol-signal-valid",
            verdict=DiagnosticVerdict.DIAG_SIGNAL_VALID,
        )
        self.assertEqual(meta["gate_action"], "BLOCKED")
        self.assertEqual(meta["cause"], "ETHICAL_BOUNDARY")
        self.assertEqual(meta["verdict"], "DIAG_INCONCLUSIVE")

    def test_violation_ethical_beats_perm_and_kfold(self) -> None:
        agent = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="blocked"),
        )
        meta = self._meta(
            agent,
            "viol-perm-kfold",
            verdict=DiagnosticVerdict.DIAG_FILTER_ARTIFACT,
            cause=BlockCause.FILTER_ARTIFACT,
        )
        self.assertEqual(meta["cause"], "ETHICAL_BOUNDARY")

    def test_priority_order_ethical_first(self) -> None:
        self.assertLess(
            gate_cause_priority(BlockCause.ETHICAL_BOUNDARY),
            gate_cause_priority(BlockCause.INCONCLUSIVE),
        )
        self.assertLess(
            gate_cause_priority(BlockCause.ETHICAL_BOUNDARY),
            gate_cause_priority(BlockCause.FILTER_ARTIFACT),
        )
        self.assertTrue(ethical_beats_methodical(BlockCause.FILTER_ARTIFACT))
        self.assertTrue(ethical_beats_methodical(None))

    def test_resolve_final_gate_unchanged_on_compliance(self) -> None:
        from agents_b2g.diagnostic.ethical_boundary_hook import EthicalPreflightResult

        v, c, g = resolve_final_gate(
            methodical_verdict=DiagnosticVerdict.DIAG_SIGNAL_VALID,
            methodical_cause=None,
            ethical=EthicalPreflightResult(passed=True),
        )
        self.assertEqual(v, DiagnosticVerdict.DIAG_SIGNAL_VALID)
        self.assertIsNone(c)
        self.assertEqual(g.value, "RELEASED")

    def test_hook_fail_closed_on_orchestrator_exception(self) -> None:
        agent = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="fault"),
        )
        meta = self._meta(
            agent,
            "fail-closed-hook",
            verdict=DiagnosticVerdict.DIAG_SIGNAL_VALID,
        )
        self.assertEqual(meta["gate_action"], "BLOCKED")
        self.assertEqual(meta["cause"], "ETHICAL_BOUNDARY")
        self.assertIn("ethical_boundary", meta)
        self.assertEqual(meta["ethical_boundary"]["status"], "BLOCKED")

    def test_certified_ethical_boundary_serialized_on_methodical_block(self) -> None:
        """CERTIFIED Wave 39 must appear in metadata even when Wave 38 stays BLOCKED."""
        agent = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=_MockEthicalOrchestrator(mode="certified"),
        )
        meta = self._meta(
            agent,
            "certified-on-inconclusive",
            verdict=DiagnosticVerdict.DIAG_INCONCLUSIVE,
            cause=BlockCause.INCONCLUSIVE,
        )
        self.assertEqual(meta["gate_action"], "BLOCKED")
        self.assertEqual(meta["cause"], "INCONCLUSIVE")
        self.assertIn("ethical_boundary", meta)
        self.assertEqual(meta["ethical_boundary"]["status"], "CERTIFIED")
        self.assertEqual(
            meta["ethical_boundary"]["scope"]["scope"],
            "DEFENSIVE_CAUSAL_GROUNDING",
        )

    def test_real_orchestrator_violation_blocks_gatekeeper(self) -> None:
        agent = GatekeeperDispatcherAgent(
            user_id="test-hook",
            ethical_orchestrator=EthicalBoundaryOrchestrator(user_id="test-hook"),
        )
        run_input = {
            **self.RUN_INPUT,
            "receiver_metadata": {
                "receiver_id": "bad",
                "allowed_purposes": ["RISK_MANAGEMENT"],
                "purposes": ["MEV_EXTRACTION"],
            },
        }
        result = agent.run(
            run_input,
            "real-violation",
            verdict=DiagnosticVerdict.DIAG_SIGNAL_VALID,
        )
        self.assertEqual(result["status"], "completed")
        meta = result["artifacts"][0]["metadata"]
        self.assertEqual(meta["cause"], "ETHICAL_BOUNDARY")
        self.assertIn("ethical_boundary", meta)


class TestPipelineEthicalWiring(unittest.TestCase):
    """Analysis/Live pipeline injects EthicalBoundaryOrchestrator into Gatekeeper."""

    def test_analysis_pipeline_injects_orchestrator(self) -> None:
        from agents_b2g.diagnostic.wave38_analysis_pipeline import Wave38AnalysisPipeline

        pipe = Wave38AnalysisPipeline(user_id="test-wiring")
        self.assertIsNotNone(pipe.gatekeeper._ethical_orchestrator)
        self.assertIs(pipe.gatekeeper._ethical_orchestrator, pipe.ethical_orchestrator)

    def test_live_pipeline_shares_orchestrator(self) -> None:
        from agents_b2g.diagnostic.wave38_live_pipeline import Wave38LivePipeline

        pipe = Wave38LivePipeline(user_id="test-wiring")
        self.assertIs(pipe.analysis.ethical_orchestrator, pipe.ethical_orchestrator)
        self.assertIs(pipe.gatekeeper._ethical_orchestrator, pipe.ethical_orchestrator)

    def test_analysis_accepts_injected_mock(self) -> None:
        from agents_b2g.diagnostic.wave38_analysis_pipeline import Wave38AnalysisPipeline

        mock = _MockEthicalOrchestrator(mode="certified")
        pipe = Wave38AnalysisPipeline(user_id="test-wiring", ethical_orchestrator=mock)
        self.assertIs(pipe.gatekeeper._ethical_orchestrator, mock)


class _MockEthicalOrchestrator:
    """Injectable mock — Gatekeeper must not construct EthicalBoundaryOrchestrator itself."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def enforce(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str,
        wave38_gate_context: Mapping[str, Any] | None = None,
    ) -> EthicalBoundaryEnvelope:
        _ = payload, wave38_gate_context
        if self.mode == "fault":
            raise RuntimeError("charter unavailable")
        scope = attach_scope_flag({}, attached_by="MockEthicalOrchestrator")
        if self.mode == "blocked":
            return blocked_envelope(
                job_id=job_id,
                scope=scope,
                violations=(
                    ViolationRecord(
                        violation_type=ViolationType.PROFIT_EXTRACTION,
                        severity=ViolationSeverity.critical(),
                        source_agent="MockEthicalOrchestrator",
                        message="mock ethical violation",
                    ),
                ),
            )
        return certified_envelope(
            job_id=job_id,
            scope=scope,
            certificate_id=DefensiveScopeCertifier._certificate_id(job_id, scope),
        )


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestTypesAndEnvelope,
        TestFailClosed,
        TestNonExtractionAssertion,
        TestScopeTampering,
        TestScopeEnforcerAgent,
        TestEthicalAssertionAgent,
        TestWave28Descriptive,
        TestCharterAirGapRegression,
        TestCharterEnforcerAgent,
        TestCharterAirGap,
        TestIntegrityViolationDetector,
        TestBoundaryViolationReporter,
        TestDefensiveScopeCertifier,
        TestPreRegFirewallAgent,
        TestAuditTrailAgent,
        TestSkeletonStageInvariant,
        TestSkeletonFailClosed,
        TestE2EPipeline,
        TestWave38Hook,
        TestPipelineEthicalWiring,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    print(f"\n{'=' * 60}")
    print(f"Wave 39 Ethical Boundary: {passed}/{total} passed")
    print(f"{'=' * 60}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
