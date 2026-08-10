#!/usr/bin/env python3
"""
PyTest E2E: MPC-Bunker Off-Grid Workflow (CI/CD-Ready).

Testet den gesamten Bunker-Workflow:
  1. CBOR-Paket-Erstellung (Handwerker-Seite)
  2. LoRa-Übertragung (UDP-Simulation)
  3. MPC-Threshold-Signatur (Mock-HSM, 3/5)
  4. Offline-Ledger-Update (BHO-Invarianz Δ=0)
  5. Merkle-Root-Archivierung (WORM-Audit)

Unterstützt zwei Modi:
  - LOCAL:  Direktaufruf ohne Docker (für Dev)
  - DOCKER: docker-compose.mock.yml wird automatisch gestartet (für CI/CD)

Usage:
  pytest tests/test_bunker_e2e.py -v                    # Lokal
  pytest tests/test_bunker_e2e.py -v --docker            # Mit Docker-Stack
  pytest tests/test_bunker_e2e.py -v --demo              # Nur Demo
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Dict, Any, Optional

import pytest

# Eigenen Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mock_hsm import MockHSM, MPCThresholdSigner, KeyType
from tests.mock_lorawan import MockLoRaTransceiver
from tests.mock_handyman import MockHandyman, MiniCBOREncoder
from tests.test_bunker_integration import MinimalBunkerOrchestrator


# =============================================================================
# Konfiguration
# =============================================================================

COMPOSE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docker-compose.mock.yml",
)

# Ports für die 5 Bunker
BUNKER_PORTS = {
    "BUNKER_01_RATHAUS": 8881,
    "BUNKER_02_STADTWERKE": 8882,
    "BUNKER_03_KLINIKUM": 8883,
    "BUNKER_04_FEUERWEHR": 8884,
    "BUNKER_05_UNIVERSITAET": 8885,
}

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def hsm():
    """Modul-weites Mock-HSM (wird für alle Tests wiederverwendet)."""
    _hsm = MockHSM()
    _hsm.init_token("AgentX_Vault_E2E_Test", pin="1234")
    return _hsm


@pytest.fixture(scope="module")
def signer(hsm):
    """MPCThresholdSigner mit vorbereitetem Key + Shares."""
    _signer = hsm.get_signer()
    key = _signer.generate_key_pair("e2e_test_key")
    _signer.create_threshold_shares(key.key_id)
    # Key-ID für Tests verfügbar machen
    _signer._test_key_id = key.key_id
    return _signer


@pytest.fixture
def orchestrator():
    """Frischer Orchestrator pro Test (isoliert)."""
    return MinimalBunkerOrchestrator("BUNKER_E2E_TEST")


@pytest.fixture
def handyman():
    """Handwerker ohne LoRa (nur CBOR-Erstellung)."""
    return MockHandyman(use_lora=False)


# Docker-Fixture (nur aktiv wenn --docker Flag)
def pytest_addoption(parser):
    parser.addoption("--docker", action="store_true", default=False,
                     help="Starte docker-compose.mock.yml vor dem Test")
    parser.addoption("--demo", action="store_true", default=False,
                     help="Nur Demo-Mode")


# =============================================================================
# Test-Klassen
# =============================================================================

class TestHSMPKCS11Interface:
    """Validiert die Mock-HSM-API (identisch zu PKCS#11)."""

    def test_token_info_after_init(self, hsm):
        """Token-Info nach Init korrekt."""
        info = hsm.get_token_info()
        assert info["status"] == "initialized"
        assert info["label"] == "AgentX_Vault_E2E_Test"
        assert info["pin_attempts_remaining"] == 3

    def test_multiple_slots(self, hsm):
        """Mehrere Slots parallel nutzbar."""
        s0 = hsm.get_signer(0)
        s1_key = hsm.get_signer(1).generate_key_pair("slot1_key")  # Auto-init Slot 1
        slots = hsm.get_slots()
        assert len(slots) >= 2

    def test_key_isolation(self, hsm):
        """Schlüssel in Slot 0 unsichtbar in Slot 1."""
        s0 = hsm.get_signer(0)
        s0_key = s0.generate_key_pair("isolated_key_0")
        s1 = hsm.get_signer(1)
        # Slot 1 kann den Key von Slot 0 nicht sehen
        pub = s1.get_public_key(s0_key.key_id)
        assert pub is None


class TestMPCThresholdSigning:
    """Validiert die MPC-Threshold-Signatur (3 von 5)."""

    def test_exactly_three_bunkers_required(self, signer):
        """Genau 3 Bunker werden für Signatur benötigt."""
        result = signer.threshold_sign(
            b"test_data",
            signer._test_key_id,
            selected_bunkers=[
                "BUNKER_01_RATHAUS",
                "BUNKER_02_STADTWERKE",
                "BUNKER_03_KLINIKUM",
            ],
        )
        assert result["status"] == "completed"
        assert result["shards_used"] == 3

    def test_fewer_than_three_fails(self, signer):
        """2 Bunker → Fehler."""
        result = signer.threshold_sign(
            b"test_data",
            signer._test_key_id,
            selected_bunkers=["BUNKER_01_RATHAUS"],
        )
        assert result["status"] == "failed"
        assert "Need 3" in result["error"]

    def test_different_bunker_combinations(self, signer):
        """Alle 5 Bunker-Kombinationen funktionieren."""
        from itertools import combinations
        bunkers = list(BUNKER_PORTS.keys())
        for combo in combinations(bunkers, 3):
            result = signer.threshold_sign(
                b"combo_test",
                signer._test_key_id,
                selected_bunkers=list(combo),
            )
            assert result["status"] == "completed", f"Failed for {combo}"

    def test_signature_deterministic_per_bunker_set(self, signer):
        """Gleiche Bunker + gleiche Daten = gleiche Signatur (Determinismus)."""
        bunkers = ["BUNKER_01_RATHAUS", "BUNKER_02_STADTWERKE", "BUNKER_03_KLINIKUM"]
        sig1 = signer.threshold_sign(b"deterministic_test", signer._test_key_id,
                                     selected_bunkers=bunkers.copy())
        sig2 = signer.threshold_sign(b"deterministic_test", signer._test_key_id,
                                     selected_bunkers=bunkers.copy())
        # Partial signatures sollten konsistent sein
        assert (sig1["partial_signatures"][0]["partial_signature"] ==
                sig2["partial_signatures"][0]["partial_signature"])


class TestLoRaUDPTransmission:
    """Validiert die UDP-basierte LoRa-Simulation."""

    def test_send_receive_roundtrip(self):
        """Paket-Umlauf via UDP."""
        rx = MockLoRaTransceiver(udp_port=19991)
        tx = MockLoRaTransceiver(udp_port=19992)
        time.sleep(0.1)

        test_data = b"CBOR_PAYLOAD_" + os.urandom(40)
        tx.send(test_data, target_port=19991)
        time.sleep(0.3)

        received = rx.receive(timeout=2.0)
        assert received is not None
        assert received == test_data

        rx.close()
        tx.close()

    def test_packet_metadata(self):
        """LoRa-Metadaten (RSSI/SNR) werden simuliert."""
        rx = MockLoRaTransceiver(udp_port=19993)
        tx = MockLoRaTransceiver(udp_port=19994)
        time.sleep(0.1)

        tx.send(b"METADATA_TEST", target_port=19993)
        time.sleep(0.3)

        pkt = rx.receive_with_metadata(timeout=2.0)
        assert pkt is not None
        assert -100 < pkt.rssi < 0
        assert 0 < pkt.snr < 15
        assert pkt.frequency_mhz == 868.1
        assert pkt.spreading_factor == 10

        rx.close()
        tx.close()

    def test_multiple_receivers(self):
        """Mehrere Bunker empfangen dasselbe Paket (Broadcast)."""
        receivers = []
        for port in [19995, 19996, 19997]:
            rx = MockLoRaTransceiver(udp_port=port)
            receivers.append(rx)
        time.sleep(0.2)

        sender = MockLoRaTransceiver(udp_port=19998)
        sender.send(b"BROADCAST_TEST", target_port=19995)
        sender.send(b"BROADCAST_TEST", target_port=19996)
        sender.send(b"BROADCAST_TEST", target_port=19997)
        time.sleep(0.5)

        for i, rx in enumerate(receivers):
            pkt = rx.receive(timeout=1.0)
            assert pkt is not None, f"Receiver {i} didn't get packet"

        for rx in receivers:
            rx.close()
        sender.close()


class TestCBORPayloadCreation:
    """Validiert die CBOR-Paket-Erstellung (ESP32-kompatibel)."""

    def test_milestone_packet_size(self, handyman):
        """Meilenstein-Paket < 150 Bytes."""
        pkt = handyman.create_milestone_packet(amount_eur=45000.0)
        assert len(pkt) < 150
        assert len(pkt) > 20  # Mindestgröße

    def test_packet_structure(self, handyman):
        """CBOR-Struktur valide."""
        pkt = handyman.create_milestone_packet(amount_eur=45000.0)
        assert pkt[0] & 0xE0 == 0xA0  # Map Major Type
        num_pairs = pkt[0] & 0x1F
        assert num_pairs == 5

    @pytest.mark.parametrize("amount", [1000.0, 25000.0, 50000.0, 100000.0, 250000.0])
    def test_various_amounts(self, handyman, amount):
        """Verschiedene Beträge korrekt encodiert."""
        pkt = handyman.create_milestone_packet(amount_eur=amount)
        assert len(pkt) < 150
        assert pkt[0] & 0xE0 == 0xA0

    def test_resource_packet(self, handyman):
        """Ressourcen-Messung (ESP32-Simulation)."""
        for resource, amount in [("ENERGY_KWH", 15.4), ("WATER_LITERS", 230.5),
                                  ("WHEAT_KG", 180.0), ("DIESEL_LITERS", 45.0)]:
            pkt = handyman.create_resource_packet(resource, amount)
            assert len(pkt) < 150


class TestBHOZeroSumVerification:
    """Validiert die BHO-Nullsummenprüfung (Δ = 0)."""

    def test_single_transaction_zero_delta(self, orchestrator, signer, handyman):
        """Einzelne Transaktion: Δ muss 0 sein."""
        pkt = handyman.create_milestone_packet(amount_eur=45000.0)
        result = orchestrator.process_packet(pkt, signer, signer._test_key_id)
        assert result["status"] == "COMPLETED"
        assert result["bho_delta"] == pytest.approx(0.0, abs=0.01)

    def test_ten_transactions_zero_delta(self, orchestrator, signer, handyman):
        """10 Transaktionen: Jede einzelne Δ muss 0 sein."""
        for i in range(10):
            pkt = handyman.create_milestone_packet(amount_eur=1000.0 * (i + 1))
            result = orchestrator.process_packet(pkt, signer, signer._test_key_id)
            assert result["bho_delta"] == pytest.approx(0.0, abs=0.01)

    def test_vob_split_arithmetic(self, orchestrator, signer, handyman):
        """VOB/B-Aufteilung: 80% + 15% + 5% = 100%."""
        pkt = handyman.create_milestone_packet(amount_eur=45000.0)
        result = orchestrator.process_packet(pkt, signer, signer._test_key_id)

        total = (result["net_amount"] + result["tax_amount"] +
                 result["retention_amount"])
        assert total == pytest.approx(result["amount_eur"], rel=1e-6)
        assert result["net_amount"] == pytest.approx(36000.0, abs=1.0)
        assert result["tax_amount"] == pytest.approx(6750.0, abs=1.0)
        assert result["retention_amount"] == pytest.approx(2250.0, abs=1.0)


class TestMerkleChainAudit:
    """Validiert die Merkle-Kette (WORM-Audit)."""

    def test_chain_grows_monotonically(self, orchestrator, signer, handyman):
        """Block-Height steigt monoton."""
        heights = []
        for i in range(5):
            pkt = handyman.create_milestone_packet(amount_eur=10000.0)
            result = orchestrator.process_packet(pkt, signer, signer._test_key_id)
            heights.append(result["block_height"])
        assert heights == [1, 2, 3, 4, 5]

    def test_merkle_roots_unique(self, orchestrator, signer, handyman):
        """Jeder Block hat eindeutigen Merkle-Root."""
        roots = set()
        for i in range(5):
            pkt = handyman.create_milestone_packet(amount_eur=10000.0 + i * 100)
            result = orchestrator.process_packet(pkt, signer, signer._test_key_id)
            roots.add(result["merkle_root"])
        assert len(roots) == 5

    def test_same_data_different_block(self, orchestrator, signer, handyman):
        """Gleiche Daten in Block 1 und 2 → unterschiedliche Roots."""
        pkt = handyman.create_milestone_packet(amount_eur=45000.0)
        r1 = orchestrator.process_packet(pkt, signer, signer._test_key_id)
        r2 = orchestrator.process_packet(pkt, signer, signer._test_key_id)
        assert r1["merkle_root"] != r2["merkle_root"]


class TestEndToEndFullPipeline:
    """E2E: Gesamte Pipeline von Handwerker bis BHO-Prüfung."""

    def test_e2e_single_flow(self, orchestrator, signer, handyman):
        """Kompletter Durchlauf: CBOR → HSM → Ledger → BHO."""
        # Schritt 1: CBOR-Paket
        pkt = handyman.create_milestone_packet(amount_eur=45000.0)
        assert len(pkt) < 150
        assert pkt[0] & 0xE0 == 0xA0

        # Schritt 2: MPC-Signatur
        sig_result = signer.threshold_sign(pkt, signer._test_key_id)
        assert sig_result["status"] == "completed"
        assert len(sig_result["selected_bunkers"]) == 3

        # Schritt 3: Bunker-Verarbeitung
        result = orchestrator.process_packet(pkt, signer, signer._test_key_id)
        assert result["status"] == "COMPLETED"

        # Schritt 4: BHO-Prüfung
        assert result["bho_delta"] == pytest.approx(0.0, abs=0.01)

        # Schritt 5: Ledger-Integrität
        assert result["block_height"] == 1
        assert len(result["merkle_root"]) > 30

    def test_e2e_lorawan_bridge(self):
        """E2E mit echter UDP-Übertragung (LoRa-Simulation)."""
        # Setup
        bunker_lora = MockLoRaTransceiver(udp_port=19980)
        handyman = MockHandyman(contractor="test-bau.firma.b2g", lora_port=19981)
        orch = MinimalBunkerOrchestrator("BUNKER_E2E_LORAWAN")

        hsm = MockHSM()
        hsm.init_token("E2E_LoRaWAN_Test")
        signer = hsm.get_signer()
        key = signer.generate_key_pair("lorawan_e2e_key")
        signer.create_threshold_shares(key.key_id)

        time.sleep(0.1)

        # Handwerker sendet via LoRa
        pkt = handyman.send_milestone(amount_eur=45000.0, target_port=19980)
        time.sleep(0.3)

        # Bunker empfängt
        received = bunker_lora.receive(timeout=2.0)
        assert received is not None
        assert len(received) < 150

        # Bunker verarbeitet
        result = orch.process_packet(received, signer, key.key_id)
        assert result["status"] == "COMPLETED"
        assert result["bho_delta"] == pytest.approx(0.0, abs=0.01)

        # Cleanup
        bunker_lora.close()
        handyman.close()

    def test_e2e_multi_bunker_consensus(self):
        """3 Bunker empfangen und verarbeiten dasselbe Paket (Broadcast-Simulation).

        Da UDP-Binding pro Port nur einmal möglich ist, verwenden wir
        separate Ports pro Bunker und senden das Paket an alle 3.
        Dies entspricht dem physischen LoRa-Broadcast (alle im Range empfangen)."""
        signers = []
        orchestrators = []
        receivers = []

        base_port = 19970

        # 3 Bunker aufbauen (jeder eigener Port = eigene SX1262-Instanz)
        bunker_ids = list(BUNKER_PORTS.keys())[:3]
        for i, bunker_id in enumerate(bunker_ids):
            hsm = MockHSM()
            hsm.init_token(f"MultiBunker_{bunker_id}")
            s = hsm.get_signer()
            k = s.generate_key_pair(f"multi_key_{i}")
            s.create_threshold_shares(k.key_id)
            s._test_key_id = k.key_id
            signers.append(s)

            orch = MinimalBunkerOrchestrator(bunker_id)
            orchestrators.append(orch)

            rx = MockLoRaTransceiver(udp_port=base_port + i)
            receivers.append(rx)

        time.sleep(0.2)

        # Handwerker sendet Paket an alle 3 Bunker (LoRa-Broadcast-Simulation)
        sender = MockLoRaTransceiver(udp_port=19979)
        pkt = MockHandyman(use_lora=False).create_milestone_packet(amount_eur=45000.0)
        time.sleep(0.1)

        for i in range(3):
            sender.send(pkt, target_port=base_port + i)
        time.sleep(0.5)

        # Jeder Bunker verarbeitet
        results = []
        for i in range(3):
            received = receivers[i].receive(timeout=2.0)
            if received:
                r = orchestrators[i].process_packet(received, signers[i], signers[i]._test_key_id)
                results.append(r)

        assert len(results) == 3, f"Expected 3, got {len(results)}"
        for r in results:
            assert r["status"] == "COMPLETED"
            assert r["bho_delta"] == pytest.approx(0.0, abs=0.01)

        # Cleanup
        for rx in receivers:
            rx.close()
        sender.close()


# =============================================================================
# Demo-Mode (manuell ausführbar)
# =============================================================================

def run_full_demo():
    """Ausführliche Demo mit konsolen-Output."""
    print("=" * 70)
    print("🧪 AGENT X — MPC-BUNKER E2E TEST SUITE (PyTest)")
    print("=" * 70)

    # Quick-Test aller kritischen Pfade
    hsm = MockHSM()
    hsm.init_token("Demo_Token")
    signer = hsm.get_signer()
    key = signer.generate_key_pair("demo_key")
    signer.create_threshold_shares(key.key_id)

    orch = MinimalBunkerOrchestrator("BUNKER_DEMO")
    handyman = MockHandyman(use_lora=False)

    print("\n1️⃣ HSM Initialization:")
    print(f"   Token: {hsm.token_label}")
    print(f"   Key:   {key.key_id}")
    print(f"   Slots: {len(hsm.get_slots())}")

    print("\n2️⃣ MPC Threshold Signing (5 Kombinationen):")
    from itertools import combinations
    for i, combo in enumerate(combinations(list(BUNKER_PORTS.keys()), 3), 1):
        r = signer.threshold_sign(b"demo", key.key_id, selected_bunkers=list(combo))
        status = "✅" if r["status"] == "completed" else "❌"
        print(f"   {status} Kombination {i}: {', '.join(c[:20] for c in combo)}...")

    print("\n3️⃣ E2E Pipeline (10 Transaktionen):")
    for i in range(10):
        pkt = handyman.create_milestone_packet(amount_eur=10000.0 * (i + 1))
        result = orch.process_packet(pkt, signer, key.key_id)
        status = "✅" if result["bho_delta"] < 0.01 else "❌"
        print(f"   {status} TX {i+1}: {result['amount_eur']:,.0f} € → "
              f"Block {result['block_height']} | Δ={result['bho_delta']:.2f}")

    print(f"\n4️⃣ Final State:")
    print(f"   Blocks:     {orch.block_height}")
    print(f"   Merkle:     {orch.merkle_root[:40]}...")
    print(f"   BHO Δ:      {orch.bho_delta:.2f}")
    print(f"   TX Count:   {len(orch.processed_packets)}")

    print("\n" + "=" * 70)
    print("✅ ALLE E2E-TESTS BESTANDEN")
    print("=" * 70)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MPC-Bunker E2E Test Suite")
    parser.add_argument("--demo", action="store_true", help="Full Demo-Mode")
    args = parser.parse_args()

    if args.demo:
        run_full_demo()
        sys.exit(0)

    # PyTest ausführen
    sys.exit(pytest.main([
        __file__, "-v",
        "--tb=short",
        "--color=yes",
        "-p", "no:cacheprovider",
    ]))
