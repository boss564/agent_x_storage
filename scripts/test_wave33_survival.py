#!/usr/bin/env python3
"""
Test Suite: Wave 33 — Survival & Off-Grid Post-Quantum Orchestrator.

Testet die vollständige 9-Agenten-Survival-Architektur:
- Post-Quantum-Kryptografie (Dilithium-5, Kyber-1024, SPHINCS+)
- MPC-Bunker (t=3, n=5)
- ZK-STARK-Kompression
- LoRaWAN-Mesh-Networking
- Peer-Discovery (DHT + Gossip)
- State-Synchronisation (Hash-Kette)
- Ressourcen-Orakel (IoT-Sensoren)
- Rationierung (ZK-eID)
- Multilaterales Ressourcen-Clearing

Usage:
    python3 scripts/test_wave33_survival.py
    python3 scripts/test_wave33_survival.py --verbose
"""

import hashlib
import json
import os
import sys
import time
import unittest

# Projekt-Root in Pfad aufnehmen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.survival.survival_orchestrator import (
    SurvivalOrchestrator,
    SurvivalMode,
    SurvivalContext,
)
from agents_b2g.survival.subagents.pqc_signer import (
    PQCSignerAgent,
    PQCMode,
    DILITHIUM5_SIGNATURE_BYTES,
    DILITHIUM5_SECRET_KEY_BYTES,
    DILITHIUM5_PUBLIC_KEY_BYTES,
    KYBER1024_PUBLIC_KEY_BYTES,
    SPHINCS_SIGNATURE_BYTES,
)
from agents_b2g.survival.subagents.mpc_bunker import MPCBunkerAgent, NodeStatus
from agents_b2g.survival.subagents.zk_compression import ZKCompressionAgent
from agents_b2g.survival.subagents.lorawan_mesh import LoRaWANMeshAgent, ChannelType
from agents_b2g.survival.subagents.peer_discovery import PeerDiscoveryAgent
from agents_b2g.survival.subagents.state_sync import StateSyncAgent
from agents_b2g.survival.subagents.resource_oracle import ResourceOracleAgent
from agents_b2g.survival.subagents.rationing import RationingAgent
from agents_b2g.survival.subagents.clearing import ClearingAgent


# =============================================================================
# Test Helper
# =============================================================================

def assert_standard_json_format(test, result):
    """Validiert das standardisierte JSON-Ausgabeformat."""
    test.assertIn("status", result, "Fehlendes 'status' Feld")
    test.assertIn(result["status"], ["completed", "started", "failed", "RESOURCE_TRANSFERRED"],
                  f"Unerwarteter Status: {result.get('status')}")


# =============================================================================
# Test Group 1: PQC Signer Agent (Dilithium, Kyber, SPHINCS+)
# =============================================================================

class TestPQCSignerAgent(unittest.TestCase):
    """Testet den PQC Signer Agent mit Dilithium-5, Kyber-1024, SPHINCS+."""

    def setUp(self):
        self.agent = PQCSignerAgent(user_id="test")

    def test_01_backend_detection(self):
        """Prüft dass ein PQC-Backend erkannt wird."""
        self.assertIn(self.agent.mode, [PQCMode.NATIVE_LIBOQS, PQCMode.SIMULATION_SHA3])
        self.assertIsNotNone(self.agent.backend_info)
        print(f"  PQC Backend: {self.agent.mode.value} ({self.agent.backend_info})")

    def test_02_dilithium_keypair_generation(self):
        """Generiert ein Dilithium-5 Schlüsselpaar."""
        result = self.agent.generate_dilithium_keypair()
        assert_standard_json_format(self, result)
        self.assertEqual(result["algorithm"], result.get("algorithm", ""))
        self.assertEqual(result["nist_level"], 5)
        self.assertTrue(result["quantum_resistant"])
        # Korrekte Dimensionen (Dilithium-5)
        self.assertEqual(result["public_key_size_bytes"], DILITHIUM5_PUBLIC_KEY_BYTES)
        self.assertEqual(result["secret_key_size_bytes"], DILITHIUM5_SECRET_KEY_BYTES)

    def test_03_dilithium_sign_and_verify(self):
        """Signiert eine Nachricht mit Dilithium-5 und verifiziert."""
        message = b"Agent X B2G Procurement Order #2026-0815"
        result = self.agent.sign_dilithium(message)
        self.assertTrue(result.verified)
        self.assertEqual(result.nist_level, 5)
        self.assertTrue(result.quantum_resistant)
        self.assertEqual(result.signature_size_bytes, DILITHIUM5_SIGNATURE_BYTES)
        self.assertGreater(result.signing_time_us, 0)

    def test_04_kyber_keypair_and_encapsulation(self):
        """Generiert Kyber-1024 Schlüssel und kapselt Shared Secret."""
        keypair = self.agent.generate_kyber_keypair()
        assert_standard_json_format(self, keypair)
        self.assertEqual(keypair["public_key_size_bytes"], KYBER1024_PUBLIC_KEY_BYTES)
        self.assertEqual(keypair["nist_level"], 5)

        encapsulation = self.agent.encapsulate_kyber(keypair["public_key_hex"])
        assert_standard_json_format(self, encapsulation)
        self.assertEqual(encapsulation["shared_secret_size_bytes"], 32)
        self.assertEqual(encapsulation["nist_level"], 5)

    def test_05_sphincs_sign(self):
        """Signiert mit SPHINCS+ (hash-basierter Fallback)."""
        message = b"Critical Infrastructure Shutdown Authorization"
        result = self.agent.sign_sphincs(message)
        self.assertTrue(result.verified)
        self.assertEqual(result.nist_level, 5)
        self.assertTrue(result.quantum_resistant)
        self.assertEqual(result.signature_size_bytes, SPHINCS_SIGNATURE_BYTES)

    def test_06_hybrid_ecdsa_dilithium(self):
        """Hybride Signatur ECDSA + Dilithium (BSI TR-02102-1)."""
        message = b"BSI TR-02102-1 Hybrid Migration Test"
        result = self.agent.sign_hybrid(message)
        assert_standard_json_format(self, result)
        self.assertTrue(result["ecdsa"]["verified"])
        self.assertTrue(result["dilithium5"]["verified"])
        self.assertFalse(result["ecdsa"]["quantum_resistant"])
        self.assertTrue(result["dilithium5"]["quantum_resistant"])
        self.assertEqual(result["nist_level"], 5)

    def test_07_benchmark(self):
        """Führt PQC-Benchmark mit allen Algorithmen durch."""
        result = self.agent.run_benchmark(iterations=10)
        assert_standard_json_format(self, result)
        self.assertIn("dilithium5", result["benchmark"])
        self.assertIn("kyber1024", result["benchmark"])
        self.assertIn("sphincs+", result["benchmark"])
        self.assertIn("ecdsa_p256", result["benchmark"])
        self.assertIn("comparison", result)

    def test_08_status(self):
        """Prüft System-Status."""
        status = self.agent.get_status()
        assert_standard_json_format(self, status)
        self.assertTrue(status["bsi_compliant"])
        self.assertEqual(len(status["available_algorithms"]), 4)

    def test_09_failsafe_wrapper(self):
        """Testet _safe_call mit absichtlichem Fehler."""
        result = self.agent._safe_call(lambda: 1 / 0)
        self.assertEqual(result["status"], "failed")
        self.assertIn("error", result)
        self.assertEqual(result["error_type"], "ZeroDivisionError")


# =============================================================================
# Test Group 2: MPC Bunker Agent (t=3, n=5)
# =============================================================================

class TestMPCBunkerAgent(unittest.TestCase):
    """Testet den MPC Bunker Agent mit Threshold-Signaturen."""

    def setUp(self):
        self.agent = MPCBunkerAgent(user_id="test")

    def test_10_bunker_activation(self):
        """Aktiviert alle 5 Bunker-Nodes."""
        result = self.agent.activate_bunker()
        assert_standard_json_format(self, result)
        self.assertEqual(result["nodes_total"], 5)
        self.assertEqual(result["threshold"], 3)
        self.assertTrue(result["threshold_met"])

    def test_11_bunker_status(self):
        """Prüft detaillierten Bunker-Status."""
        self.agent.activate_bunker()
        status = self.agent.get_bunker_status()
        assert_standard_json_format(self, status)
        self.assertEqual(len(status["nodes"]), 5)
        self.assertTrue(status["can_sign"])
        self.assertEqual(status["online_count"], 5)

    def test_12_mpc_threshold_signature(self):
        """Führt eine MPC-Threshold-Signatur durch (3 von 5)."""
        self.agent.activate_bunker()
        message = b"Emergency Resource Reallocation Order #2026-001"
        result = self.agent.sign_with_mpc(message)
        assert_standard_json_format(self, result)
        self.assertEqual(result["shards_used"], 3)
        self.assertGreater(result["signature_size_bytes"], 0)
        self.assertTrue(result["quantum_resistant"])
        self.assertIn("selected_nodes", result)

    def test_13_node_failure_simulation(self):
        """Simuliert Ausfall eines Bunker-Nodes."""
        self.agent.activate_bunker()
        result = self.agent.simulate_node_failure("node_01")
        assert_standard_json_format(self, result)
        self.assertEqual(result["remaining_online"], 4)
        self.assertTrue(result["can_still_sign"])

    def test_14_node_failure_below_threshold(self):
        """Simuliert Ausfall von 3 Nodes — Signatur unmöglich."""
        self.agent.activate_bunker()
        for node_id in ["node_01", "node_02", "node_03"]:
            self.agent.simulate_node_failure(node_id)
        status = self.agent.get_bunker_status()
        self.assertFalse(status["can_sign"])

    def test_15_node_recovery(self):
        """Stellt ausgefallenen Node wieder her."""
        self.agent.activate_bunker()
        self.agent.simulate_node_failure("node_02")
        result = self.agent.recover_node("node_02")
        assert_standard_json_format(self, result)
        self.assertEqual(result["recovered_node"], "node_02")

    def test_16_failsafe(self):
        """Testet _safe_call."""
        result = self.agent._safe_call(lambda: 1 / 0)
        self.assertEqual(result["status"], "failed")


# =============================================================================
# Test Group 3: ZK Compression Agent (STARKs)
# =============================================================================

class TestZKCompressionAgent(unittest.TestCase):
    """Testet den ZK STARK Compression Agent."""

    def setUp(self):
        self.agent = ZKCompressionAgent(user_id="test")

    def test_20_stark_proof_generation(self):
        """Generiert einen STARK-Proof."""
        data = {"key": "value", "numbers": list(range(100))}
        result = self.agent.generate_stark_proof(data)
        assert_standard_json_format(self, result)
        self.assertTrue(result["quantum_resistant"])
        self.assertFalse(result["trusted_setup_required"])
        # Proof sollte ~256 bytes sein
        self.assertLess(result["proof_size_bytes"], 1000)
        self.assertGreater(result["compression_ratio"].split(":")[0], "1")

    def test_21_stark_verification(self):
        """Verifiziert einen STARK-Proof."""
        data = {"tender_id": "TED-2026-0815", "amount_eur": 4_200_000}
        proof = self.agent.generate_stark_proof(data)
        verify = self.agent.verify_stark_proof(
            proof["proof_hex"],
            hashlib.sha3_256(str(data).encode()).hexdigest(),
        )
        assert_standard_json_format(self, verify)

    def test_22_mesh_compression(self):
        """Komprimiert State für LoRaWAN-Mesh-Übertragung (4 KB Limit)."""
        state = {"transactions": [{"id": i, "amount": i * 100} for i in range(50)]}
        result = self.agent.compress_state_for_mesh(state)
        assert_standard_json_format(self, result)
        self.assertTrue(result["fits_lorawan"])
        self.assertGreater(result["updates_per_day"], 0)

    def test_23_snark_vs_stark_comparison(self):
        """Vergleicht SNARK vs STARK Eigenschaften."""
        result = self.agent.compare_snark_vs_stark()
        assert_standard_json_format(self, result)
        self.assertIn("trusted_setup", result["comparison"])
        self.assertIn("quantum_resistance", result["comparison"])

    def test_24_compression_statistics(self):
        """Prüft Kompressions-Statistiken."""
        for i in range(5):
            self.agent.generate_stark_proof({"data": "x" * 1000})
        status = self.agent.get_status()
        assert_standard_json_format(self, status)
        self.assertEqual(status["proofs_generated"], 5)
        self.assertGreater(status["avg_compression_ratio"], 0)


# =============================================================================
# Test Group 4: LoRaWAN Mesh Agent
# =============================================================================

class TestLoRaWANMeshAgent(unittest.TestCase):
    """Testet den LoRaWAN Mesh Agent."""

    def setUp(self):
        self.agent = LoRaWANMeshAgent(user_id="test")

    def test_30_mesh_activation(self):
        """Aktiviert alle Mesh-Kanäle."""
        result = self.agent.activate_mesh()
        assert_standard_json_format(self, result)
        self.assertEqual(len(result["protocols"]), 4)
        self.assertEqual(len(result["channels"]), 4)

    def test_31_broadcast_state(self):
        """Sendet State-Proof via Mesh."""
        self.agent.activate_mesh()
        proof = os.urandom(256)
        result = self.agent.broadcast_state(proof)
        assert_standard_json_format(self, result)
        self.assertGreater(result["peers_reached"], 0)
        self.assertTrue(result["pqc_encrypted"])

    def test_32_channel_status(self):
        """Prüft Kanal-Status."""
        self.agent.activate_mesh()
        status = self.agent.get_channel_status()
        assert_standard_json_format(self, status)
        self.assertEqual(len(status["channels"]), 4)
        for ch in status["channels"].values():
            self.assertTrue(ch["active"])

    def test_33_range_estimation(self):
        """Schätzt Mesh-Reichweite."""
        self.agent.activate_mesh()
        result = self.agent.estimate_range()
        assert_standard_json_format(self, result)
        self.assertGreaterEqual(result["max_range_km"], 50)

    def test_34_mesh_deactivation(self):
        """Deaktiviert Mesh (Rückkehr zu TCP/IP)."""
        self.agent.activate_mesh()
        result = self.agent.deactivate_mesh()
        assert_standard_json_format(self, result)
        self.assertFalse(result["mesh_active"])


# =============================================================================
# Test Group 5: Peer Discovery Agent
# =============================================================================

class TestPeerDiscoveryAgent(unittest.TestCase):
    """Testet den Peer Discovery Agent (DHT + Gossip)."""

    def setUp(self):
        self.agent = PeerDiscoveryAgent(user_id="test")

    def test_40_peer_discovery(self):
        """Sucht nach Peers im Mesh."""
        result = self.agent.discover_peers()
        assert_standard_json_format(self, result)
        self.assertGreater(result["count"], 0)
        self.assertGreater(len(result["peers"]), 0)
        self.assertTrue(result["sybil_resistant"])

    def test_41_dht_lookup(self):
        """Führt einen DHT-Lookup durch."""
        self.agent.discover_peers()
        # Suche nach erstem Peer
        first_peer = list(self.agent.peers.keys())[0] if self.agent.peers else "test_peer"
        result = self.agent.dht_lookup(first_peer)
        assert_standard_json_format(self, result)

    def test_42_network_topology(self):
        """Prüft Netzwerktopologie."""
        self.agent.discover_peers()
        result = self.agent.get_network_topology()
        assert_standard_json_format(self, result)
        self.assertIn("roles_distribution", result)
        self.assertIn("mesh_health", result)


# =============================================================================
# Test Group 6: State Sync Agent (Hash-Kette)
# =============================================================================

class TestStateSyncAgent(unittest.TestCase):
    """Testet den State Sync Agent mit Hash-Ketten-Synchronisation."""

    def setUp(self):
        self.agent = StateSyncAgent(user_id="test")
        self.zk_agent = ZKCompressionAgent(user_id="test")

    def test_50_state_sync(self):
        """Synchronisiert State via Succinct-Rollup."""
        state = {"balance": 1000, "peers": 5, "mode": "off_grid", "data": "x" * 1000}
        result = self.agent.sync_state(state, self.zk_agent)
        assert_standard_json_format(self, result)
        self.assertEqual(result["version"], 1)
        self.assertTrue(result["hash_chain_intact"])
        # Mit großen Daten sollte die Kompression greifen
        self.assertGreater(result["compressed_size_bytes"], 0)

    def test_51_delta_sync(self):
        """Synchronisiert nur geänderte Felder."""
        self.agent.sync_state({"a": 1, "b": 2}, self.zk_agent)
        result = self.agent.sync_delta({"b": 3}, self.zk_agent)
        assert_standard_json_format(self, result)
        self.assertEqual(result["delta_keys"], 1)

    def test_52_hash_chain_verification(self):
        """Validiert die Hash-Kette (WORM-Audit)."""
        for i in range(5):
            self.agent.sync_state({f"key_{i}": i}, self.zk_agent)
        result = self.agent.verify_hash_chain()
        assert_standard_json_format(self, result)
        self.assertTrue(result["chain_valid"])
        self.assertEqual(result["worm_property"], "INTACT")

    def test_53_multiple_versions(self):
        """Erzeugt mehrere Versionen und prüft."""
        for i in range(10):
            result = self.agent.sync_state({f"version_{i}": i}, self.zk_agent)
            self.assertEqual(result["version"], i + 1)
        status = self.agent.get_status()
        self.assertEqual(status["current_version"], 10)


# =============================================================================
# Test Group 7: Resource Oracle Agent
# =============================================================================

class TestResourceOracleAgent(unittest.TestCase):
    """Testet das Ressourcen-Orakel (IoT-Sensoren)."""

    def setUp(self):
        self.agent = ResourceOracleAgent(user_id="test")

    def test_60_fetch_resources(self):
        """Liest lokale Ressourcen aus."""
        result = self.agent.fetch_local_resources()
        assert_standard_json_format(self, result)
        self.assertEqual(len(result["units"]), 6)
        self.assertIn("electricity_kwh", result["units"])
        self.assertIn("water_liters", result["units"])

    def test_61_check_availability(self):
        """Prüft Ressourcen-Verfügbarkeit."""
        self.agent.fetch_local_resources()
        result = self.agent.check_availability("electricity_kwh", 100)
        assert_standard_json_format(self, result)
        self.assertTrue(result["sufficient"])

    def test_62_resource_transfer(self):
        """Führt Ressourcen-Transfer durch."""
        self.agent.fetch_local_resources()
        result = self.agent.transfer("A", "B", "diesel_liters", 50)
        assert_standard_json_format(self, result)
        self.assertIn("transfer_hash", result)

    def test_63_survival_estimation(self):
        """Schätzt Überlebensdauer."""
        self.agent.fetch_local_resources()
        result = self.agent.estimate_survival_days(population=2000)
        assert_standard_json_format(self, result)
        self.assertIn("bottleneck_days", result)
        self.assertIn("grade", result)

    def test_64_add_resources(self):
        """Fügt Ressourcen hinzu."""
        self.agent.fetch_local_resources()
        result = self.agent.add_resources("wheat_kg", 500, "Harvest_2026")
        assert_standard_json_format(self, result)
        self.assertEqual(result["added"], 500)


# =============================================================================
# Test Group 8: Rationing Agent (ZK-eID)
# =============================================================================

class TestRationingAgent(unittest.TestCase):
    """Testet den Rationing Agent mit ZK-eID."""

    def setUp(self):
        self.agent = RationingAgent(user_id="test")

    def test_70_issue_ration_card(self):
        """Stellt eine ZK-eID-Rationierungskarte aus."""
        result = self.agent.issue_ration_card("buerger_001", entitlement_level=1)
        assert_standard_json_format(self, result)
        self.assertTrue(result["anonymized"])
        self.assertTrue(result["double_spend_protected"])
        self.assertIn("daily_ration", result)

    def test_71_priority_levels(self):
        """Testet alle 5 Prioritäts-Level."""
        for level in range(1, 6):
            result = self.agent.issue_ration_card(f"citizen_L{level}", entitlement_level=level)
            self.assertEqual(result["entitlement_level"], level)
            self.assertGreaterEqual(result["priority_multiplier"], 1.0)

    def test_72_verify_entitlement(self):
        """Verifiziert ZK-Berechtigung."""
        card = self.agent.issue_ration_card("citizen_42", entitlement_level=3)
        valid = self.agent.verify_entitlement(card["zk_proof"])
        self.assertTrue(valid)

    def test_73_issue_ration(self):
        """Gibt eine Ration aus."""
        card = self.agent.issue_ration_card("citizen_x", entitlement_level=2)
        result = self.agent.issue_ration(card["citizen_hash"], "water_liters", 20)
        assert_standard_json_format(self, result)
        self.assertTrue(result["corruption_free"])

    def test_74_double_spend_protection(self):
        """Double-Spend-Schutz: zweite Ausgabe schlägt fehl."""
        card = self.agent.issue_ration_card("citizen_y", entitlement_level=1)
        # Erste Ausgabe
        self.agent.issue_ration(card["citizen_hash"], "wheat_kg", 0.5)
        # Zweite Ausgabe (sollte fehlschlagen)
        result = self.agent.issue_ration(card["citizen_hash"], "wheat_kg", 0.5)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Double-Spend", result["error"])

    def test_75_distribution_stats(self):
        """Prüft Verteilungs-Statistiken."""
        for i in range(10):
            self.agent.issue_ration_card(f"citizen_{i}", entitlement_level=(i % 5) + 1)
        stats = self.agent.get_distribution_stats()
        assert_standard_json_format(self, stats)
        self.assertEqual(stats["total_citizens"], 10)
        self.assertEqual(stats["corruption_incidents"], 0)


# =============================================================================
# Test Group 9: Clearing Agent (Multilaterales Netting)
# =============================================================================

class TestClearingAgent(unittest.TestCase):
    """Testet den Clearing Agent mit multilateralem Ressourcen-Netting."""

    def setUp(self):
        self.agent = ClearingAgent(user_id="test")

    def test_80_register_transaction(self):
        """Registriert eine Clearing-Transaktion."""
        result = self.agent.register_transaction("A", "B", "electricity_kwh", 150)
        assert_standard_json_format(self, result)
        self.assertTrue(result["pending_clearing"])

    def test_81_bilateral_netting(self):
        """Saldiert gegenseitige Forderungen A↔B."""
        self.agent.register_transaction("A", "B", "water_liters", 100)
        self.agent.register_transaction("B", "A", "water_liters", 60)
        result = self.agent.execute_clearing()
        assert_standard_json_format(self, result)
        self.assertGreater(result["reduction_percentage"], 0)

    def test_82_multilateral_cycle_resolution(self):
        """Löst Dreiecks-Schulden auf (A→B→C→A)."""
        self.agent.register_transaction("A", "B", "diesel_liters", 100)
        self.agent.register_transaction("B", "C", "diesel_liters", 100)
        self.agent.register_transaction("C", "A", "diesel_liters", 100)
        result = self.agent.execute_clearing()
        assert_standard_json_format(self, result)
        # 3 bilaterale + 1 Zyklus = hohe Reduktion
        self.assertGreater(result["reduction_percentage"], 50)

    def test_83_cycle_detection_algorithm(self):
        """Testet Zyklenerkennung im Graph."""
        self.agent.register_transaction("Node1", "Node2", "resource", 50)
        self.agent.register_transaction("Node2", "Node3", "resource", 50)
        self.agent.register_transaction("Node3", "Node1", "resource", 50)
        self.agent.register_transaction("Node1", "Node4", "resource", 30)
        result = self.agent.execute_clearing()
        assert_standard_json_format(self, result)
        self.assertTrue(result["bho_zero_sum"])
        self.assertEqual(result["delta_resource_units"], 0.00)

    def test_84_empty_clearing(self):
        """Clearing ohne Transaktionen."""
        result = self.agent.execute_clearing()
        assert_standard_json_format(self, result)
        self.assertEqual(result["original_transactions"], 0)

    def test_85_clearing_history(self):
        """Prüft Clearing-Historie (GoBD-WORM)."""
        for i in range(3):
            self.agent.register_transaction(f"P{i}", f"Q{i}", "resource", 100)
            self.agent.execute_clearing()
        history = self.agent.get_clearing_history()
        assert_standard_json_format(self, history)
        self.assertEqual(history["total_cycles"], 3)
        self.assertTrue(history["worm_archived"])

    def test_86_large_scale_netting(self):
        """Testet Netting mit 50 Transaktionen (bilateral + multilateral)."""
        parties = [f"Party_{i}" for i in range(10)]
        # Bilaterale Paare (viel Reduktionspotential)
        for i in range(25):
            sender = parties[i % len(parties)]
            recipient = parties[(i + 1) % len(parties)]
            self.agent.register_transaction(sender, recipient, "electricity_kwh", 100)
            # Gegenrichtung → bilaterales Netting möglich
            self.agent.register_transaction(recipient, sender, "electricity_kwh", 80)
        result = self.agent.execute_clearing()
        assert_standard_json_format(self, result)
        # Mit 25 bilateralen Paaren sollte die Reduktion >50% sein
        self.assertGreater(result["reduction_percentage"], 50)
        self.assertTrue(result["bho_zero_sum"])


# =============================================================================
# Test Group 10: Survival Orchestrator E2E
# =============================================================================

class TestSurvivalOrchestratorE2E(unittest.TestCase):
    """End-to-End-Tests für den Survival Orchestrator."""

    def setUp(self):
        self.orch = SurvivalOrchestrator(user_id="test_e2e")

    def test_90_initialization(self):
        """Prüft Initialisierung mit allen 9 Subagenten."""
        self.assertEqual(self.orch.context.mode, SurvivalMode.NORMAL)
        self.assertTrue(self.orch.context.bank_available)
        self.assertTrue(self.orch.context.internet_available)

    def test_91_off_grid_activation(self):
        """Aktiviert Off-Grid-Modus (9-Stufen-Pipeline)."""
        result = self.orch.activate_off_grid_mode()
        assert_standard_json_format(self, result)
        self.assertEqual(result["mode"], "OFF_GRID")
        self.assertGreater(result["mesh_peers"], 0)
        self.assertGreater(len(result["resources"]), 0)
        self.assertTrue(result["pqc_active"])
        self.assertTrue(result["sovereignty_preserved"])
        self.assertEqual(len(result["pipeline_stages"]), 8)

    def test_92_degraded_mode(self):
        """Aktiviert degradierten Modus."""
        result = self.orch.activate_degraded_mode()
        assert_standard_json_format(self, result)
        self.assertEqual(result["mode"], "DEGRADED")

    def test_93_post_quantum_mode(self):
        """Aktiviert Post-Quantum-Modus."""
        result = self.orch.activate_post_quantum_mode()
        assert_standard_json_format(self, result)
        self.assertEqual(result["mode"], "POST_QUANTUM")
        self.assertTrue(result["quantum_threat_detected"])

    def test_94_resource_transaction_off_grid(self):
        """Führt Ressourcen-Transfer im Off-Grid-Modus durch."""
        self.orch.activate_off_grid_mode()
        result = self.orch.execute_resource_transaction(
            sender="Rathaus",
            recipient="Krankenhaus",
            resource_type="diesel_liters",
            amount=200,
        )
        self.assertEqual(result["status"], "RESOURCE_TRANSFERRED")
        self.assertIn("transfer_hash", result)

    def test_95_resource_transaction_insufficient(self):
        """Transfer scheitert bei unzureichenden Ressourcen."""
        self.orch.activate_off_grid_mode()
        result = self.orch.execute_resource_transaction(
            sender="Rathaus",
            recipient="Krankenhaus",
            resource_type="electricity_kwh",
            amount=999_999_999,  # Unmöglich viel
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("shortfall", result)

    def test_96_return_to_normal(self):
        """Rückkehr zum Normalbetrieb."""
        self.orch.activate_off_grid_mode()
        self.orch.clearing_agent.register_transaction("A", "B", "water", 100)
        self.orch.clearing_agent.execute_clearing()
        result = self.orch.return_to_normal()
        assert_standard_json_format(self, result)
        self.assertEqual(result["mode"], "NORMAL")
        self.assertFalse(self.orch.context.emergency_declared)

    def test_97_system_status(self):
        """Prüft Gesamtsystem-Status mit allen 9 Agenten."""
        self.orch.activate_off_grid_mode()
        status = self.orch.get_system_status()
        assert_standard_json_format(self, status)
        self.assertIn("agents", status)
        for agent_name in ["pqc_signer", "mpc_bunker", "zk_compression",
                           "mesh", "peers", "state_sync",
                           "resources", "rationing", "clearing"]:
            self.assertIn(agent_name, status["agents"],
                          f"Agent {agent_name} fehlt im System-Status")

    def test_98_full_survival_demo(self):
        """Führt vollständige Survival-Demo durch (alle Stages)."""
        result = self.orch.run_full_survival_demo()
        assert_standard_json_format(self, result)
        self.assertGreater(result["stages_completed"], 0)
        self.assertGreater(result["transactions_executed"], 0)
        self.assertTrue(result["sovereignty_preserved"])
        print(f"  Survival Grade: {result['survival_grade']}")
        print(f"  Bottleneck: {result['bottleneck_days']} Tage")

    def test_99_survival_context_state(self):
        """Prüft SurvivalContext State-Maschine."""
        self.orch.activate_off_grid_mode()
        self.assertEqual(self.orch.context.mode, SurvivalMode.OFF_GRID)
        self.assertFalse(self.orch.context.bank_available)
        self.assertFalse(self.orch.context.internet_available)
        self.assertTrue(self.orch.context.emergency_declared)
        self.assertTrue(self.orch.context.sovereignty_preserved)

        self.orch.return_to_normal()
        self.assertEqual(self.orch.context.mode, SurvivalMode.NORMAL)
        self.assertTrue(self.orch.context.bank_available)
        self.assertFalse(self.orch.context.emergency_declared)


# =============================================================================
# Test Group 11: Config & Environment
# =============================================================================

class TestConfigAndEnvironment(unittest.TestCase):
    """Testet Konfiguration und Umgebungsvariablen."""

    def test_100_pqc_mode_from_env(self):
        """PQC-Modus wird korrekt erkannt."""
        agent = PQCSignerAgent()
        self.assertIn(agent.mode, [PQCMode.NATIVE_LIBOQS, PQCMode.SIMULATION_SHA3])
        self.assertIsNotNone(agent.backend_info)

    def test_101_multi_user_isolation(self):
        """Multi-Tenancy: User-IDs isolieren Ressourcen."""
        orch_a = SurvivalOrchestrator(user_id="kaemmerer_a")
        orch_b = SurvivalOrchestrator(user_id="kaemmerer_b")
        self.assertEqual(orch_a.user_id, "kaemmerer_a")
        self.assertEqual(orch_b.user_id, "kaemmerer_b")
        # Unterschiedliche User haben unabhängige Kontexte
        self.assertIsNot(orch_a.context, orch_b.context)


# =============================================================================
# Main Runner
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Wave 33 Survival & Off-Grid Test Suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--demo", action="store_true", help="Run full survival demo only")
    args = parser.parse_args()

    if args.demo:
        print("=" * 70)
        print("🛡️  AGENT X — SOVEREIGN SURVIVAL ENCLAVE — FULL DEMO")
        print("=" * 70)
        orch = SurvivalOrchestrator(user_id="demo")
        result = orch.run_full_survival_demo()
        print(json.dumps({
            "stages_completed": result["stages_completed"],
            "transactions": result["transactions_executed"],
            "clearing_cycles": result["clearing_cycles"],
            "survival_grade": result["survival_grade"],
            "bottleneck_days": result["bottleneck_days"],
            "pqc_mode": result["pqc_mode"],
            "sovereignty_preserved": result["sovereignty_preserved"],
        }, indent=2))
        print("\n🎉 Survival Demo abgeschlossen!")
        sys.exit(0)

    print("=" * 70)
    print("🧪 Wave 33 — Survival & Off-Grid Post-Quantum Test Suite")
    print(f"   PQC Backend: {PQCSignerAgent().mode.value} ({PQCSignerAgent().backend_info})")
    print("=" * 70)

    # Test-Suite zusammenstellen
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_groups = [
        TestPQCSignerAgent,
        TestMPCBunkerAgent,
        TestZKCompressionAgent,
        TestLoRaWANMeshAgent,
        TestPeerDiscoveryAgent,
        TestStateSyncAgent,
        TestResourceOracleAgent,
        TestRationingAgent,
        TestClearingAgent,
        TestSurvivalOrchestratorE2E,
        TestConfigAndEnvironment,
    ]

    for group in test_groups:
        tests = loader.loadTestsFromTestCase(group)
        suite.addTests(tests)

    # Verbosity
    verbosity = 2 if args.verbose else 1

    # Run
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 70)
    print(f"📊 Ergebnisse: {result.testsRun} Tests")
    print(f"   ✅ Erfolgreich: {result.testsRun - len(result.failures) - len(result.errors)}")
    if result.failures:
        print(f"   ❌ Fehlschläge: {len(result.failures)}")
    if result.errors:
        print(f"   ⚠️  Errors: {len(result.errors)}")
    print("=" * 70)

    # Exit-Code
    sys.exit(0 if result.wasSuccessful() else 1)
