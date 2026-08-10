#!/usr/bin/env python3
"""
Mock LoRaWAN Transceiver — UDP-basierte Simulation des SX1276/SX1262.

Simuliert den LoRa-Transceiver via UDP-Sockets statt SPI.
Gleiche API wie die echte LoRaWANTransceiverAgent-Klasse.

API-Kompatibilität:
    - receive(timeout)     → Empfängt Paket (entspricht rfm9x.receive())
    - send(data, port)     → Sendet Paket (entspricht LoRa-TX)
    - close()              → Schließt Transceiver (entspricht rfm9x.sleep())

LoRa-Parameter (simuliert):
    - Frequenz:    868.1 MHz (simuliert, keine echte HF)
    - Bandbreite:  125 kHz (Time-on-Air simuliert)
    - SF:          10 (Spreading Factor)
    - Reichweite:  ~15 km (simuliert, keine echte Ausbreitung)

Usage:
    from tests.mock_lorawan import MockLoRaTransceiver

    lora = MockLoRaTransceiver(udp_port=8888)
    packet = lora.receive(timeout=5.0)
    if packet:
        process_packet(packet)
    lora.close()
"""

import socket
import threading
import time
import hashlib
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class LoRaPacket:
    """Ein empfangenes LoRa-Paket mit Metadaten."""
    data: bytes
    source_addr: Tuple[str, int]
    rssi: float          # Signalstärke in dBm (simuliert)
    snr: float           # Signal-Rausch-Verhältnis in dB (simuliert)
    frequency_mhz: float
    spreading_factor: int
    timestamp: str
    packet_id: str


class MockLoRaTransceiver:
    """
    Simuliert einen SX1262/SX1276 LoRa-Transceiver via UDP.

    Statt SPI-Register-Zugriff wird UDP verwendet.
    Ideal für Container-Tests ohne echte HF-Hardware.
    """

    def __init__(self, udp_port: int = 8888):
        self.udp_port = udp_port
        self.frequency_mhz = 868.1
        self.spreading_factor = 10
        self.bandwidth_khz = 125

        # UDP-Socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("0.0.0.0", udp_port))
        self.socket.settimeout(0.5)

        # Empfangs-Thread
        self.running = True
        self._packet_queue: List[LoRaPacket] = []
        self._rx_count = 0
        self._tx_count = 0
        self._lock = threading.Lock()

        self._thread = threading.Thread(target=self._receive_loop, daemon=True, name="MockLoRa-RX")
        self._thread.start()

    # =========================================================================
    # Receive
    # =========================================================================

    def _receive_loop(self):
        """Hintergrund-Thread: Empfängt UDP-Pakete und stellt sie als LoRa-Pakete dar."""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                continue

            # Simuliere LoRa-Metadaten
            with self._lock:
                packet = LoRaPacket(
                    data=data,
                    source_addr=addr,
                    rssi=-75.0 + (hash(data) % 40 - 20),  # -55 bis -95 dBm
                    snr=8.0 + (hash(data[:8]) % 10 - 5),    # 3-13 dB
                    frequency_mhz=self.frequency_mhz,
                    spreading_factor=self.spreading_factor,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    packet_id=hashlib.sha3_256(data + str(time.time()).encode()).hexdigest()[:16],
                )
                self._packet_queue.append(packet)
                self._rx_count += 1

    def receive(self, timeout: float = 5.0) -> Optional[bytes]:
        """
        Wartet auf ein eingehendes LoRa-Paket.

        Entspricht rfm9x.receive() auf ESP32.
        Blockiert bis timeout oder Paket empfangen.
        """
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if self._packet_queue:
                    packet = self._packet_queue.pop(0)
                    return packet.data
            time.sleep(0.05)
        return None

    def receive_with_metadata(self, timeout: float = 5.0) -> Optional[LoRaPacket]:
        """
        Wartet auf ein Paket und gibt vollständige Metadaten zurück.

        Entspricht rfm9x.receive() mit RSSI/SNR-Auslese.
        """
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if self._packet_queue:
                    return self._packet_queue.pop(0)
            time.sleep(0.05)
        return None

    # =========================================================================
    # Send
    # =========================================================================

    def send(self, data: bytes, target_host: str = "localhost", target_port: int = 8889) -> bool:
        """
        Sendet ein LoRa-Paket via UDP.

        Entspricht rfm9x.send() auf ESP32.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, (target_host, target_port))
            sock.close()
            self._tx_count += 1
            return True
        except Exception:
            return False

    # =========================================================================
    # Statistics & Control
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Empfangs-/Sende-Statistiken zurück."""
        with self._lock:
            queue_len = len(self._packet_queue)
        return {
            "rx_count": self._rx_count,
            "tx_count": self._tx_count,
            "queue_len": queue_len,
            "frequency_mhz": self.frequency_mhz,
            "spreading_factor": self.spreading_factor,
            "bandwidth_khz": self.bandwidth_khz,
            "udp_port": self.udp_port,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def set_frequency(self, freq_mhz: float):
        """Setzt die simulierte LoRa-Frequenz."""
        self.frequency_mhz = freq_mhz

    def set_spreading_factor(self, sf: int):
        """Setzt den simulierten Spreading Factor (7-12)."""
        if 7 <= sf <= 12:
            self.spreading_factor = sf

    def close(self):
        """Schließt den Transceiver und räumt auf."""
        self.running = False
        try:
            self.socket.close()
        except Exception:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
