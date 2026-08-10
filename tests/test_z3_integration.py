#!/usr/bin/env python3
"""
Integrationstest: Z3-Theorem-Prover + Bunker-Orchestrator.

Testet die vollständige Pipeline:
  1. Z3-Service-Healthcheck (Z3-Kernel antwortet)
  2. BHO-Invariant-Beweis (UNSAT → Invariante hält)
  3. BHO-Verletzungserkennung (SAT → Gegenbeispiel)
  4. Orchestrator → Z3-HTTP-Call (vollständiger Flow)
  5. Float-Präzisions-Härtung (0.1 + 0.2 ≠ 0.3 in IEEE-754, aber Z3 korrigiert)

Usage:
  pytest tests/test_z3_integration.py -v
  python3 tests/test_z3_integration.py
"""

import hashlib
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.z3_solver.main import (
    app,
    prove_bho_invariant_z3,
    BHOCheckRequest,
    BHOProofResponse,
)
from fastapi.testclient import TestClient


class TestZ3Kernel(unittest.TestCase):
    """Validiert den Z3-Kernel direkt (ohne HTTP)."""

    def test_01_z3_import_and_version(self):
        """Z3-Solver ist importierbar und hat eine Versionsnummer."""
        import z3
        version = z3.get_version_string()
        self.assertIsInstance(version, str)
        self.assertGreater(len(version), 3)
        print(f"  Z3 Version: {version}")

    def test_02_bho_invariant_holds(self):
        """BHO-Invariante hält bei korrekter Aufteilung."""
        holds, delta, proof_us = prove_bho_invariant_z3(
            gross=45000.00, net=36000.00, tax=6750.00, retention=2250.00
        )
        self.assertTrue(holds, f"BHO must hold, got delta={delta}")
        self.assertEqual(delta, 0.0)
        self.assertLess(proof_us, 10000, f"Z3 proof too slow: {proof_us:.0f} µs")
        print(f"  Z3 proof: {proof_us:.1f} µs (UNSAT = invariant holds)")

    def test_03_bho_invariant_violated(self):
        """BHO-Verletzung wird erkannt (1 Cent Differenz)."""
        holds, delta, proof_us = prove_bho_invariant_z3(
            gross=45000.00, net=36000.00, tax=6750.00, retention=2249.99
        )
        self.assertFalse(holds, "BHO violation must be detected")
        self.assertNotEqual(delta, 0.0)
        print(f"  Z3 detected violation: Δ = {delta:.4f} (SAT)")

    def test_04_float_precision_hardening(self):
        """
        IEEE-754-Falle: 0.1 + 0.2 ≠ 0.3 in Float-Arithmetik.
        Z3 RealVal via String-Konversion muss dies korrigieren.
        """
        # In Python-Float: 0.1 + 0.2 = 0.30000000000000004
        # Z3 muss dies als 3/10 erkennen → Δ = 0
        holds, delta, proof_us = prove_bho_invariant_z3(
            gross=0.3, net=0.1, tax=0.1, retention=0.1
        )
        self.assertTrue(holds, f"Z3 must handle 0.1+0.1+0.1==0.3, got delta={delta}")
        print(f"  IEEE-754 Härtung: 0.1+0.1+0.1 vs 0.3 → Δ = {delta} (Z3 korrigiert)")

    def test_05_various_amounts(self):
        """Verschiedene Beträge — alle korrekten Splits müssen halten."""
        test_cases = [
            (1000.00, 800.00, 150.00, 50.00),
            (12345.67, 9876.54, 1851.85, 617.28),
            (99999.99, 79999.99, 15000.00, 5000.00),
            (1.00, 0.80, 0.15, 0.05),
            (1000000.00, 800000.00, 150000.00, 50000.00),
        ]
        for gross, net, tax, ret in test_cases:
            holds, delta, _ = prove_bho_invariant_z3(gross, net, tax, ret)
            self.assertTrue(holds,
                f"BHO must hold for {gross} = {net} + {tax} + {ret}, got Δ={delta}")
        print(f"  {len(test_cases)} korrekte Splits → alle halten ✅")


class TestZ3HTTPService(unittest.TestCase):
    """Validiert den Z3-HTTP-Endpoint via TestClient."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_10_health(self):
        """Healthcheck: Z3-Kernel antwortet."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["solver"], "Z3")
        self.assertIn("4.", data["version"])  # Z3 4.x
        print(f"  Health: {data['solver']} {data['version']} ✅")

    def test_11_valid_bho_200(self):
        """Korrekte BHO-Aufteilung → 200 MATHEMATICALLY_PROVED."""
        resp = self.client.post("/prove_bho_invariant", json={
            "sector": "BAU",
            "gross_amount": 45000.00,
            "net_amount": 36000.00,
            "tax_amount": 6750.00,
            "retention_amount": 2250.00,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "MATHEMATICALLY_PROVED")
        self.assertTrue(data["bho_invariant_valid"])
        self.assertEqual(data["bho_delta_eur"], 0.0)
        self.assertEqual(data["solver"], "Z3_Real_Arithmetic")
        self.assertGreater(data["proof_time_us"], 0)
        print(f"  {data['status']} in {data['proof_time_us']:.1f} µs")

    def test_12_invalid_bho_422(self):
        """BHO-Verletzung → 422 Unprocessable Entity."""
        resp = self.client.post("/prove_bho_invariant", json={
            "sector": "ENERGIE",
            "gross_amount": 45000.00,
            "net_amount": 36000.00,
            "tax_amount": 6750.00,
            "retention_amount": 2249.00,  # 1 EUR zu wenig
        })
        self.assertEqual(resp.status_code, 422)
        detail = resp.json()["detail"]
        self.assertIn("VERLETZT", detail)
        self.assertIn("ENERGIE", detail)
        print(f"  422: {detail[:80]}...")

    def test_13_multiple_sectors(self):
        """Verschiedene Sektoren — alle korrekt."""
        for sector in ["BAU", "ENERGIE", "WASSER", "BILDUNG"]:
            resp = self.client.post("/prove_bho_invariant", json={
                "sector": sector,
                "gross_amount": 100000.00,
                "net_amount": 80000.00,
                "tax_amount": 15000.00,
                "retention_amount": 5000.00,
            })
            self.assertEqual(resp.status_code, 200, f"Sector {sector} failed")
            self.assertTrue(resp.json()["bho_invariant_valid"])
        print(f"  4 Sektoren → alle BHO-konform ✅")

    def test_14_response_schema(self):
        """Response entspricht BHOProofResponse-Schema."""
        resp = self.client.post("/prove_bho_invariant", json={
            "sector": "TEST",
            "gross_amount": 100.00,
            "net_amount": 80.00,
            "tax_amount": 15.00,
            "retention_amount": 5.00,
        })
        data = resp.json()
        required_keys = {"status", "bho_invariant_valid", "bho_delta_eur", "solver", "proof_time_us", "sector", "message"}
        self.assertTrue(required_keys.issubset(set(data.keys())),
                       f"Missing keys: {required_keys - set(data.keys())}")
        print(f"  Response-Schema: {len(data)} keys ✅")


class TestOrchestratorZ3Integration(unittest.TestCase):
    """
    Simuliert die Orchestrator→Z3-Integration.
    Der echte Orchestrator würde httpx.AsyncClient verwenden.
    """

    def setUp(self):
        self.client = TestClient(app)
        # Simulierter Orchestrator-Kontext
        self.context = {
            "sector": "BAU",
            "contract_id": "TEST-2026-0815",
        }

    def _orchestrator_verify_bho(self, gross, net, tax, retention):
        """
        Simuliert B2GOrchestrator.verify_bho_invariant().
        In Produktion: httpx.AsyncClient().post()
        """
        resp = self.client.post("/prove_bho_invariant", json={
            "sector": self.context["sector"],
            "gross_amount": gross,
            "net_amount": net,
            "tax_amount": tax,
            "retention_amount": retention,
        })
        if resp.status_code == 200:
            data = resp.json()
            assert data["bho_invariant_valid"] is True
            return data["bho_delta_eur"]
        else:
            raise RuntimeError(f"Z3 proof failed: {resp.json()['detail']}")

    def test_20_orchestrator_flow_valid(self):
        """Orchestrator ruft Z3 auf → BHO hält → Settlement freigegeben."""
        delta = self._orchestrator_verify_bho(
            gross=45000.00, net=36000.00, tax=6750.00, retention=2250.00
        )
        self.assertEqual(delta, 0.0)
        print(f"  Orchestrator→Z3: BHO Δ = {delta:.2f} → Settlement approved")

    def test_21_orchestrator_flow_violation(self):
        """Orchestrator ruft Z3 auf → BHO verletzt → Settlement blockiert."""
        with self.assertRaises(RuntimeError) as ctx:
            self._orchestrator_verify_bho(
                gross=45000.00, net=36000.00, tax=6750.00, retention=2000.00
            )
        self.assertIn("Z3 proof failed", str(ctx.exception))
        self.assertIn("VERLETZT", str(ctx.exception))
        print(f"  Orchestrator→Z3: BHO violation → Z3 proof failed (expected)")

    def test_22_consecutive_transactions(self):
        """10 aufeinanderfolgende Transaktionen — alle müssen halten."""
        for i in range(10):
            amount = 1000.00 * (i + 1)
            net = amount * 0.80
            tax = amount * 0.15
            ret = amount * 0.05
            delta = self._orchestrator_verify_bho(amount, net, tax, ret)
            self.assertEqual(delta, 0.0)
        print(f"  10 consecutive TXs → all BHO Δ=0 ✅")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Z3 Integration Test Suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=" * 70)
    print("🧠 AGENT X — Z3 THEOREM PROVER INTEGRATION TEST")
    print("=" * 70)

    verbosity = 2 if args.verbose else 1

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for group in [TestZ3Kernel, TestZ3HTTPService, TestOrchestratorZ3Integration]:
        suite.addTests(loader.loadTestsFromTestCase(group))

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    failed = len(result.failures) + len(result.errors)
    print("\n" + "=" * 70)
    print(f"📊 ERGEBNIS: {passed} passed, {failed} failed ({result.testsRun} total)")
    print("=" * 70)

    sys.exit(0 if result.wasSuccessful() else 1)
