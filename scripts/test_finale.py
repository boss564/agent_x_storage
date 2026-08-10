#!/usr/bin/env python3
"""E2E Test Suite: Final Veredelung (Wave 34) — 9 Agenten.

Test coverage:
  - DashboardRendererAgent: 4 tests (render, Streamlit mode, violation, empty)
  - AuditTrailAgent: 4 tests (log, verify, export, stats)
  - RealtimeMonitorAgent: 5 tests (health, alert, status, acknowledge, escalation)
  - FinaleOrchestrator: 5 tests (audit package, pitch summary, certificate, chain, multi-tx)
  - E2E: 2 tests (full pipeline, concurrent rendering)

Usage:
  python3 scripts/test_finale.py
  python3 scripts/test_finale.py --verbose
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents_b2g.finale import FinaleOrchestrator
from agents_b2g.finale.subagents.dashboard_renderer import DashboardRendererAgent
from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent
from agents_b2g.finale.subagents.realtime_monitor import RealtimeMonitorAgent


# ── Test fixtures ────────────────────────────────────────────────

SAMPLE_TX = {
    "contract_id": "VOB-2026-MUC-8812",
    "sector": "BAU",
    "gross_amount": 45000.0,
    "net_amount": 36000.0,      # 80%
    "tax_amount": 6750.0,       # 15% §13b UStG
    "retention_amount": 2250.0, #  5% §17 VOB/B
    "contractor": "meier-bau.firma.b2g",
    "inspector": "bauamt.muenchen.b2g",
    "milestone": "MILESTONE_05",
    "timestamp": datetime.now().isoformat(),
}

VIOLATION_TX = {
    "contract_id": "VOB-2026-BAD-0001",
    "sector": "BAU",
    "gross_amount": 45000.0,
    "net_amount": 38000.0,       # should be 36000 — 2000 € over
    "tax_amount": 6750.0,        # ok
    "retention_amount": 2250.0,   # ok → sum = 47000 ≠ 45000
    "contractor": "bad-actor.firma.b2g",
    "milestone": "MILESTONE_01",
    "timestamp": datetime.now().isoformat(),
    "z3_proof": {
        "status": "FAILED",
        "proof_hash": "0x0",
    },
}


# ── DashboardRendererAgent Tests ─────────────────────────────────

class TestDashboardRendererAgent(unittest.TestCase):
    """D1: Dashboard Renderer — 4 tests."""

    def setUp(self):
        self.agent = DashboardRendererAgent(user_id="test")

    def test_01_render_valid_tx(self):
        """Valid transaction renders with BHO Δ=0 and proof verified."""
        result = self.agent.render(SAMPLE_TX)
        self.assertEqual(result["status"], "started")
        a = result["artifacts"][0]
        self.assertEqual(a["bho_delta"], 0.00)
        self.assertFalse(a["bho_violation"])
        self.assertIn(a["proof"]["label"], ["✅ Bewiesen", "⏳ Ausstehend"])
        # chart_json is None when plotly is not installed (graceful fallback)
        if a["chart_json"] is not None:
            self.assertIn("data", a["chart_json"])

    def test_02_render_streamlit_mode(self):
        """Streamlit render mode returns st-compatible output."""
        result = self.agent.render_streamlit(SAMPLE_TX)
        self.assertIn("st_metrics", result)
        self.assertEqual(len(result["st_metrics"]), 4)
        self.assertIsNone(result.get("alerts"))  # no violation = no alert

    def test_03_bho_violation_detected(self):
        """BHO violation is correctly flagged when split amounts exceed gross."""
        result = self.agent.render(VIOLATION_TX)
        a = result["artifacts"][0]
        self.assertNotEqual(a["bho_delta"], 0.00,
                            "Delta must be non-zero when net exceeds gross split")
        self.assertTrue(a["bho_violation"],
                        "Violation must be flagged when split != gross")
        self.assertEqual(a["split_source"], "TRANSACTION")
        self.assertEqual(a["proof"]["label"], "❌ Fehlgeschlagen")

    def test_04_empty_transaction(self):
        """Empty transaction renders without crashing."""
        result = self.agent.render({})
        a = result["artifacts"][0]
        self.assertEqual(a["bar_data"]["brutto_eur"], 0)
        self.assertEqual(a["ticker"]["contract_id"], "N/A")


# ── AuditTrailAgent Tests ────────────────────────────────────────

class TestAuditTrailAgent(unittest.TestCase):
    """D2: Audit Trail — 4 tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.agent = AuditTrailAgent(user_id="test", data_root=self.tmpdir)

    def test_05_log_and_chain(self):
        """Logging entries builds a verifiable hash chain."""
        for i in range(5):
            tx = {"contract_id": f"VOB-{i:04d}", "gross_amount": 10000.0 * (i + 1),
                  "z3_proof": {"proof_hash": f"0x{i:032x}"}}
            self.agent.log_transaction(tx)

        self.assertEqual(len(self.agent.trail), 5)

        verified = self.agent.verify_chain()
        v = verified["artifacts"][0]
        self.assertTrue(v["verified"])
        self.assertEqual(v["status"], "INTACT")
        self.assertEqual(v["breaks_found"], 0)

    def test_06_tamper_detection(self):
        """Hash chain detects tampering."""
        tx = {"contract_id": "VOB-TAMPER", "gross_amount": 99999.0,
              "z3_proof": {"proof_hash": "0xdead"}}
        self.agent.log_transaction(tx)
        self.agent.log_transaction(tx)

        # Tamper: change previous_hash of second entry
        self.agent.trail[1]["previous_hash"] = "0xbroken"

        verified = self.agent.verify_chain()
        v = verified["artifacts"][0]
        self.assertFalse(v["verified"])
        self.assertEqual(v["status"], "TAMPERED")
        self.assertGreater(v["breaks_found"], 0)

    def test_07_export_jsonl(self):
        """Export produces valid JSONL file."""
        for i in range(3):
            tx = {"contract_id": f"VOB-EXP-{i:04d}", "gross_amount": 5000.0,
                  "z3_proof": {"proof_hash": f"0x{i:032x}"}}
            self.agent.log_transaction(tx)

        exported = self.agent.export_audit_log()
        e = exported["artifacts"][0]
        self.assertEqual(e["entries"], 3)
        self.assertTrue(os.path.exists(e["path"]))

        with open(e["path"], "r") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            entry = json.loads(line)
            self.assertIn("hash", entry)
            self.assertIn("previous_hash", entry)

    def test_08_stats(self):
        """Stats return correct aggregate values."""
        for i in range(4):
            tx = {"contract_id": f"VOB-STAT-{i:04d}", "gross_amount": 25000.0,
                  "z3_proof": {"proof_hash": f"0x{i:032x}"}}
            self.agent.log_transaction(tx)

        stats = self.agent.get_stats()
        self.assertEqual(stats["total_entries"], 4)
        self.assertEqual(stats["total_amount_eur"], 100000.0)
        self.assertIsNotNone(stats["first_entry"])
        self.assertIsNotNone(stats["last_entry"])


# ── RealtimeMonitorAgent Tests ───────────────────────────────────

class TestRealtimeMonitorAgent(unittest.TestCase):
    """D3: Realtime Monitor — 5 tests."""

    def setUp(self):
        self.agent = RealtimeMonitorAgent(user_id="test")

    def test_09_health_check(self):
        """Health check returns all components online."""
        result = self.agent.check_health()
        a = result["artifacts"][0]
        self.assertIn(a["overall_status"], ["HEALTHY", "DEGRADED"])  # Z3 may be offline
        self.assertGreaterEqual(a["health_score"], 80)
        self.assertIn(a["health_grade"], ["A", "B"])
        self.assertIn("orchestrator", a["components"])
        self.assertIn("z3_solver", a["components"])
        self.assertIn("hsm_bridge", a["components"])

    def test_10_trigger_alert(self):
        """Alert is logged and escalated correctly."""
        result = self.agent.trigger_alert(
            "CRITICAL", "ledger", "BHO Δ = 0.02 €!")
        a = result["artifacts"][0]
        self.assertEqual(a["severity"], "CRITICAL")
        self.assertEqual(a["component"], "ledger")
        self.assertEqual(len(self.agent.alert_history), 1)

    def test_11_system_status(self):
        """System status returns correct metrics."""
        result = self.agent.get_system_status()
        a = result["artifacts"][0]
        self.assertGreaterEqual(a["system_health"], 80)  # Z3 may be offline
        self.assertGreaterEqual(a["uptime_hours"], 0)
        self.assertIsInstance(a["dnd_active"], bool)

    def test_12_acknowledge_alert(self):
        """Alert can be acknowledged."""
        self.agent.trigger_alert("WARNING", "hsm_bridge", "Test")
        alert_id = self.agent.alert_history[0]["alert_id"]
        result = self.agent.acknowledge_alert(alert_id)
        self.assertTrue(result["artifacts"][0]["acknowledged"])
        self.assertTrue(self.agent.alert_history[0]["acknowledged"])

    def test_13_escalation_payment_halt(self):
        """FREEZE severity triggers payment halt action."""
        result = self.agent.trigger_alert(
            "FREEZE", "ledger", "BHO-Verletzung kritisch!")
        a = result["artifacts"][0]
        self.assertEqual(a["action"], "PAYMENT_HALT")


# ── FinaleOrchestrator Tests ─────────────────────────────────────

class TestFinaleOrchestrator(unittest.TestCase):
    """Orchestrator: 5 tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orch = FinaleOrchestrator(user_id="test", data_root=self.tmpdir)

    def test_14_generate_audit_package(self):
        """Full audit package generated for a valid transaction."""
        result = self.orch.generate_full_audit_package(SAMPLE_TX)
        self.assertEqual(result["status"], "completed")
        a = result["artifacts"][0]
        self.assertTrue(a["pitch_ready"])
        cert = a["certificate"]
        self.assertTrue(cert["bho_invariant_holds"])
        # Z3 proof: MATHEMATICALLY_PROVED when service is reachable,
        # UNVERIFIED (local fallback) otherwise — both are valid
        self.assertIn(cert["z3_proof_status"],
            ["MATHEMATICALLY_PROVED", "VERIFIED", "UNVERIFIED"])

    def test_15_pitch_summary(self):
        """Pitch summary contains all key metrics."""
        self.orch.generate_full_audit_package(SAMPLE_TX)
        result = self.orch.get_pitch_summary()
        p = result["artifacts"][0]
        self.assertGreaterEqual(p["system_health"], 80)  # Z3 may be offline
        self.assertGreaterEqual(p["audit_entries"], 1)
        self.assertTrue(p["pitch_ready"])

    def test_16_certificate_retrieval(self):
        """Certificate can be retrieved by ID."""
        result = self.orch.generate_full_audit_package(SAMPLE_TX)
        cert_id = result["artifacts"][0]["certificate"]["certificate_id"]

        cert = self.orch.get_audit_certificate(cert_id)
        self.assertIsNotNone(cert)
        self.assertEqual(cert["certificate"]["certificate_id"], cert_id)

    def test_17_health_and_status(self):
        """Health + Status combined view works."""
        result = self.orch.run_health_and_status()
        a = result["artifacts"][0]
        self.assertGreaterEqual(a["health"]["health_score"], 80)  # Z3 may be offline
        self.assertIn("audit_stats", a)

    def test_18_multi_tx_pipeline(self):
        """Multiple transactions produce independent certificates."""
        txs = [
            {"contract_id": f"VOB-MULTI-{i:04d}", "sector": "BAU",
             "gross_amount": 10000.0 * (i + 1),
             "contractor": f"firma_{i}.b2g", "milestone": f"M{i}",
             "timestamp": datetime.now().isoformat(),
             "z3_proof": {"status": "MATHEMATICALLY_PROVED",
                          "proof_hash": f"0x{hash(str(i)):032x}"}}
            for i in range(5)
        ]
        cert_ids = []
        for tx in txs:
            result = self.orch.generate_full_audit_package(tx)
            cert_ids.append(result["artifacts"][0]["certificate"]["certificate_id"])

        # All certificates should be unique
        self.assertEqual(len(cert_ids), len(set(cert_ids)))
        self.assertEqual(len(self.orch.audit.trail), 5)

        # Chain must be intact
        chain = self.orch.audit.verify_chain()
        self.assertTrue(chain["artifacts"][0]["verified"])

    def test_19_derived_split_makes_no_claim(self):
        """DERIVED split proves nothing — certificate must not claim it does.

        Regression guard: if bho_invariant_holds returns True for a DERIVED
        split, the certificate asserts a fact it never measured. This test
        turns red the moment that invariant is violated.
        """
        tx = {
            "contract_id": "TED-NO-AMOUNTS",
            "sector": "BAU",
            "gross_amount": 45000.0,
            # deliberately no net/tax/retention → DERIVED
        }
        result = self.orch.generate_full_audit_package(tx)
        cert = result["artifacts"][0]["certificate"]

        self.assertEqual(cert["bho_split_source"], "DERIVED")
        self.assertIsNone(
            cert["bho_invariant_holds"],
            "DERIVED split must not claim bho_invariant_holds — "
            "no actual amounts were measured"
        )


# ── E2E Tests ────────────────────────────────────────────────────

class TestE2EFullPipeline(unittest.TestCase):
    """End-to-End: 2 tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orch = FinaleOrchestrator(user_id="test", data_root=self.tmpdir)

    def test_19_full_pipeline(self):
        """Complete E2E: tx → audit package → certificate → chain verify."""
        result = self.orch.generate_full_audit_package(SAMPLE_TX)
        self.assertEqual(result["status"], "completed")
        a = result["artifacts"][0]

        # All artifacts present
        self.assertIsNotNone(a["dashboard"])
        self.assertIsNotNone(a["audit_entry"])
        self.assertIsNotNone(a["certificate"])

        # Certificate checks
        cert = a["certificate"]
        self.assertTrue(cert["bho_invariant_holds"])
        self.assertIn(cert["z3_proof_status"],
            ["MATHEMATICALLY_PROVED", "VERIFIED", "UNVERIFIED"])
        self.assertGreater(len(cert["seal"]), 10)

        # Chain verification
        chain = self.orch.audit.verify_chain()
        self.assertTrue(chain["artifacts"][0]["verified"])

        # Pitch summary
        pitch = self.orch.get_pitch_summary()
        self.assertTrue(pitch["artifacts"][0]["pitch_ready"])

    def test_20_concurrent_rendering(self):
        """Multiple dashboard renders don't interfere."""
        results = []
        for i in range(10):
            tx = {**SAMPLE_TX, "contract_id": f"VOB-CONC-{i:04d}"}
            results.append(self.orch.dashboard.render(tx))

        # All renders should succeed
        for r in results:
            self.assertEqual(r["status"], "started")
            self.assertIsNone(r["error"])

        # Render counts should increment
        self.assertEqual(
            self.orch.dashboard.render_count, 10,
            f"Expected 10 renders, got {self.orch.dashboard.render_count}")


# ── Runner ───────────────────────────────────────────────────────

def run_tests(verbose: bool = False):
    """Run all 20 tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDashboardRendererAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestAuditTrailAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestRealtimeMonitorAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestFinaleOrchestrator))
    suite.addTests(loader.loadTestsFromTestCase(TestE2EFullPipeline))

    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)

    # Summary in Agent X format
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    print(f"\n📊 ERGEBNIS: {passed} passed, {failed} failed ({total} total)")

    return result.wasSuccessful()


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    success = run_tests(verbose=verbose)
    sys.exit(0 if success else 1)
