#!/usr/bin/env python3
"""
Mock Handyman — Simuliert das Handy des Handwerkers auf der Baustelle.

Erstellt CBOR-komprimierte Pakete und sendet sie via Mock-LoRa (UDP).
Simuliert den gesamten Workflow: NFC-Tap → CBOR-Encode → LoRa-TX.

Payload-Struktur (identisch mit ESP32 cbor_payload.h):
    {
        1: "meier-bau.firma.b2g",     // Device-ID / Absender
        2: "MILESTONE",                // Nachrichten-Typ
        3: 4500000,                    // Betrag in Cent (45.000,00 €)
        4: 1723152000,                  // Unix-Timestamp
        5: 42,                         // Nonce
    }

Usage:
    from tests.mock_handyman import MockHandyman

    handyman = MockHandyman(contractor="meier-bau.firma.b2g")
    packet = handyman.create_milestone_packet(amount=45000.0)
    handyman.send_milestone(target_port=8888)
"""

import hashlib
import json
import struct
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from tests.mock_lorawan import MockLoRaTransceiver


# =============================================================================
# Minimal-CBOR-Encoder (kein externes cbor2 nötig)
# =============================================================================

class MiniCBOREncoder:
    """
    Minimaler CBOR-Encoder — identisch mit cbor_payload.h Logik.

    Komprimiert auf ~50-70 Bytes für LoRa-Übertragung.
    Kein externes cbor2-Paket nötig.
    """

    @staticmethod
    def _encode_uint(value: int) -> bytes:
        """CBOR Major Type 0 (Unsigned Integer)."""
        if value <= 23:
            return bytes([value])
        elif value <= 0xFF:
            return bytes([0x18, value])
        elif value <= 0xFFFF:
            return bytes([0x19, (value >> 8) & 0xFF, value & 0xFF])
        else:
            return bytes([0x1A,
                         (value >> 24) & 0xFF,
                         (value >> 16) & 0xFF,
                         (value >> 8) & 0xFF,
                         value & 0xFF])

    @staticmethod
    def _encode_string(s: str) -> bytes:
        """CBOR Major Type 3 (Text String)."""
        data = s.encode('utf-8')
        length = len(data)
        if length <= 23:
            return bytes([0x60 | length]) + data
        elif length <= 0xFF:
            return bytes([0x78, length]) + data
        else:
            return bytes([0x79, (length >> 8) & 0xFF, length & 0xFF]) + data

    @staticmethod
    def _encode_float32(value: float) -> bytes:
        """CBOR Major Type 7, IEEE 754 float32 (Big-Endian)."""
        packed = struct.pack('>f', value)
        return bytes([0xFA]) + packed

    @staticmethod
    def encode_milestone_packet(
        contractor: str,
        inspector: str,
        amount_eur: float,
        milestone: str,
        nonce: int = 0,
    ) -> bytes:
        """
        Encodiert einen Meilenstein als CBOR-Paket.

        Format (CBOR Map mit 5 Keys):
            Key 1 (uint): Absender (string)
            Key 2 (uint): Nachrichten-Typ = "MILESTONE"
            Key 3 (uint): Betrag in EUR (float32)
            Key 4 (uint): Unix-Timestamp (uint32)
            Key 5 (uint): Nonce (uint32)
        """
        result = bytearray()

        # CBOR Map Header (5 Paare)
        result.append(0xA5)

        # Key 1: Sender
        result.extend(MiniCBOREncoder._encode_uint(1))
        result.extend(MiniCBOREncoder._encode_string(contractor))

        # Key 2: Type
        result.extend(MiniCBOREncoder._encode_uint(2))
        result.extend(MiniCBOREncoder._encode_string("MILESTONE"))

        # Key 3: Amount (EUR als Float32)
        result.extend(MiniCBOREncoder._encode_uint(3))
        result.extend(MiniCBOREncoder._encode_float32(amount_eur))

        # Key 4: Timestamp
        result.extend(MiniCBOREncoder._encode_uint(4))
        result.extend(MiniCBOREncoder._encode_uint(int(time.time())))

        # Key 5: Nonce
        result.extend(MiniCBOREncoder._encode_uint(5))
        result.extend(MiniCBOREncoder._encode_uint(nonce))

        return bytes(result)


# =============================================================================
# MockHandyman
# =============================================================================

class MockHandyman:
    """
    Simuliert das Handy des Handwerkers auf der Baustelle.

    Workflow:
    1. NFC-Tap an Bautafel → liest Projekt-ID
    2. Eingabe des Meilensteins
    3. CBOR-Komprimierung (<150 Bytes)
    4. Senden via LoRa (UDP im Mock)
    """

    def __init__(
        self,
        contractor: str = "meier-bau.firma.b2g",
        inspector: str = "bauamt.muenchen.b2g",
        lora_port: int = 8889,
        use_lora: bool = True,
    ):
        self.contractor = contractor
        self.inspector = inspector
        self.nonce = 0

        # Eigener LoRa-Transceiver (nur wenn benötigt)
        self.lora = MockLoRaTransceiver(udp_port=lora_port) if use_lora else None

    # =========================================================================
    # Packet Creation
    # =========================================================================

    def create_milestone_packet(
        self,
        amount_eur: float = 45000.0,
        milestone: str = "MILESTONE_05",
    ) -> bytes:
        """
        Erstellt ein CBOR-komprimiertes Meilenstein-Paket.

        Größe: ~50-70 Bytes (weit unter 150-Byte-LoRa-Limit).
        """
        self.nonce += 1

        packet = MiniCBOREncoder.encode_milestone_packet(
            contractor=self.contractor,
            inspector=self.inspector,
            amount_eur=amount_eur,
            milestone=milestone,
            nonce=self.nonce,
        )

        return packet

    def create_resource_packet(
        self,
        resource_type: str = "ENERGY_KWH",
        amount: float = 15.4,
    ) -> bytes:
        """
        Erstellt ein Ressourcen-Messungs-Paket (ESP32-Simulation).

        Identisch zum Format des echten ESP32.
        """
        self.nonce += 1

        result = bytearray()
        result.append(0xA5)  # CBOR Map (5)

        # Key 1: Device-ID
        result.extend(MiniCBOREncoder._encode_uint(1))
        result.extend(MiniCBOREncoder._encode_string(f"HDY_{self.contractor}"))

        # Key 2: Resource-Type
        result.extend(MiniCBOREncoder._encode_uint(2))
        result.extend(MiniCBOREncoder._encode_string(resource_type))

        # Key 3: Amount
        result.extend(MiniCBOREncoder._encode_uint(3))
        result.extend(MiniCBOREncoder._encode_float32(amount))

        # Key 4: Timestamp
        result.extend(MiniCBOREncoder._encode_uint(4))
        result.extend(MiniCBOREncoder._encode_uint(int(time.time())))

        # Key 5: Nonce
        result.extend(MiniCBOREncoder._encode_uint(5))
        result.extend(MiniCBOREncoder._encode_uint(self.nonce))

        return bytes(result)

    # =========================================================================
    # Send
    # =========================================================================

    def send_milestone(
        self,
        amount_eur: float = 45000.0,
        milestone: str = "MILESTONE_05",
        target_port: int = 8888,
    ) -> bytes:
        """
        Sendet einen Meilenstein via Mock-LoRa (UDP).
        """
        packet = self.create_milestone_packet(amount_eur, milestone)
        if self.lora:
            success = self.lora.send(packet, target_port=target_port)
        else:
            success = False

        if success:
            print(f"📱 Handwerker: Meilenstein {milestone} gesendet ({len(packet)} bytes, {amount_eur:,.2f} €)")

        return packet

    def send_resource_measurement(
        self,
        resource_type: str = "ENERGY_KWH",
        amount: float = 15.4,
        target_port: int = 8888,
    ) -> bytes:
        """
        Sendet eine Ressourcen-Messung via Mock-LoRa.
        """
        packet = self.create_resource_packet(resource_type, amount)
        if self.lora:
            success = self.lora.send(packet, target_port=target_port)
        else:
            success = False

        if success:
            print(f"📱 Handwerker: {amount} {resource_type} gesendet ({len(packet)} bytes)")

        return packet

    # =========================================================================
    # Cleanup
    # =========================================================================

    def close(self):
        """Schließt den LoRa-Transceiver."""
        if self.lora:
            self.lora.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
