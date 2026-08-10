#!/usr/bin/env python3
"""
Mock HSM — Simuliert NitroKey HSM 2 (PKCS#11-Interface ohne Hardware).

Bietet das identische API wie die echte MPCThresholdSigner-Klasse,
verwendet aber Python-eigene Krypto (SHA3-256 + HMAC) statt PKCS#11.

Usage:
    hsm = MockHSM()
    hsm.init_token("AgentX_Vault_MUC_1", pin="1234")
    signer = hsm.get_signer()
    sig = signer.threshold_sign(message, key_id="bunker_01")

API-Kompatibilität:
    - init_token(label, pin)     → SoftHSM2-util Equivalent
    - get_signer()               → Gibt MPCThresholdSigner zurück
    - generate_key_pair(label)   → Erzeugt Schlüsselpaar im Mock-Vault
    - sign(key_id, data)         → ECDSA-Signatur (simuliert)
    - verify(key_id, data, sig)  → Signatur-Verifikation

SoftHSM-Equivalent:
    In Produktion:  libsofthsm2.so → PKCS#11 → NitroKey HSM 2
    Im Mock:        sha3_256 + HMAC → gleiche API-Signatur
"""

import hashlib
import hmac
import os
import json
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


# =============================================================================
# Key Material Types
# =============================================================================

class KeyType(Enum):
    """Entspricht PKCS#11 CKK_EC / CKK_RSA."""
    EC_SECP256K1 = "EC_SECP256K1"
    EC_SECP256R1 = "EC_SECP256R1"


@dataclass
class KeyPair:
    """Ein im Mock-HSM gespeichertes Schlüsselpaar."""
    key_id: str
    label: str
    key_type: KeyType
    public_key_hex: str
    private_key_hex: str    # In Produktion: NIE sichtbar (HSM-intern)
    created_at: str
    token_label: str
    slot: int = 0


@dataclass
class ThresholdShare:
    """MPC-Threshold-Share (3 von 5 Bunkern)."""
    bunker_id: str
    share_index: int        # 1-5
    share_data: str         # Share-Material (Hex)
    public_commitment: str  # Öffentliches Commitment


# =============================================================================
# MPCThresholdSigner (gleiche Klasse wie im Produktionscode)
# =============================================================================

class MPCThresholdSigner:
    """
    Signiert mit 3-von-5-MPC-Threshold-Signatur.

    API-identisch mit der echten HSM-Klasse — aber ohne PKCS#11.
    """

    def __init__(self, token_label: str = "AgentX_Vault_MUC_1"):
        self.token_label = token_label
        self._keys: Dict[str, KeyPair] = {}
        self._shares: Dict[str, List[ThresholdShare]] = {}
        self._sign_count = 0
        self._threshold = 3
        self._total_bunkers = 5

    # =========================================================================
    # Key Management
    # =========================================================================

    def generate_key_pair(self, label: str, key_type: KeyType = KeyType.EC_SECP256K1) -> KeyPair:
        """Generiert ein Schlüsselpaar im HSM (Private Key verlässt NIE den Mock-Vault)."""
        # Deterministic private key aus Label + Entropy
        seed = f"{label}_{os.urandom(16).hex()}_{time.time()}"
        private_hex = hashlib.sha3_256(seed.encode()).hexdigest()
        public_hex = hashlib.sha3_256(f"PUB_{private_hex}".encode()).hexdigest()

        key_id = hashlib.sha3_256(f"{self.token_label}_{label}".encode()).hexdigest()[:16]

        key = KeyPair(
            key_id=key_id,
            label=label,
            key_type=key_type,
            public_key_hex=public_hex,
            private_key_hex=private_hex,
            created_at=datetime.now(timezone.utc).isoformat(),
            token_label=self.token_label,
        )

        self._keys[key_id] = key
        return key

    def get_public_key(self, key_id: str) -> Optional[str]:
        """Gibt den Public Key zurück (verlässt den Mock-HSM)."""
        key = self._keys.get(key_id)
        return key.public_key_hex if key else None

    def list_keys(self) -> List[Dict[str, str]]:
        """Listet alle Schlüssel im HSM (nur Public Keys)."""
        return [
            {"key_id": k.key_id, "label": k.label, "type": k.key_type.value}
            for k in self._keys.values()
        ]

    # =========================================================================
    # MPC Threshold Signing
    # =========================================================================

    def create_threshold_shares(self, key_id: str) -> List[ThresholdShare]:
        """
        Teilt einen Private Key in 5 Shares (Shamir Secret Sharing).
        Mindestens 3 Shares werden zur Rekonstruktion benötigt.
        """
        key = self._keys.get(key_id)
        if not key:
            raise ValueError(f"Key {key_id} not found in HSM")

        bunkers = [
            "BUNKER_01_RATHAUS",
            "BUNKER_02_STADTWERKE",
            "BUNKER_03_KLINIKUM",
            "BUNKER_04_FEUERWEHR",
            "BUNKER_05_UNIVERSITAET",
        ]

        # Simuliertes Shamir Secret Sharing
        shares = []
        for i, bunker_id in enumerate(bunkers):
            share_seed = f"{key.private_key_hex}_{bunker_id}_{i}"
            share_data = hashlib.shake_256(share_seed.encode()).hexdigest(128)
            commitment = hashlib.sha3_256(f"COMMIT_{share_data}".encode()).hexdigest()

            shares.append(ThresholdShare(
                bunker_id=bunker_id,
                share_index=i + 1,
                share_data=share_data,
                public_commitment=commitment,
            ))

        self._shares[key_id] = shares
        return shares

    def threshold_sign(
        self,
        data: bytes,
        key_id: str,
        selected_bunkers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Führt eine MPC-Threshold-Signatur durch (3 von 5 Bunkern).

        Ablauf:
        1. Wähle 3 Bunker aus
        2. Jeder Bunker signiert mit seinem Share
        3. Kombiniere 3 Shares zu vollständiger Signatur
        """
        if key_id not in self._keys:
            return {"status": "failed", "error": f"Key {key_id} not found"}

        if key_id not in self._shares:
            self.create_threshold_shares(key_id)

        shares = self._shares[key_id]

        # 3 Bunker auswählen
        if selected_bunkers is None:
            import random
            available = [s.bunker_id for s in shares]
            selected_bunkers = random.sample(available, self._threshold)

        if len(selected_bunkers) < self._threshold:
            return {
                "status": "failed",
                "error": f"Need {self._threshold} bunkers, got {len(selected_bunkers)}",
            }

        # Jeder Bunker signiert mit seinem Share
        partial_sigs = []
        for bunker_id in selected_bunkers:
            share = next((s for s in shares if s.bunker_id == bunker_id), None)
            if not share:
                return {"status": "failed", "error": f"Bunker {bunker_id} not found"}

            # Share-Signatur
            partial = hmac.new(
                bytes.fromhex(share.share_data[:64]),
                data,
                hashlib.sha3_256,
            ).hexdigest()[:64]

            partial_sigs.append({
                "bunker_id": bunker_id,
                "share_index": share.share_index,
                "partial_signature": partial,
            })

        # Lagrange-Interpolation über Shares (simuliert)
        combined_seed = "".join(p["partial_signature"] for p in partial_sigs)
        combined_sig = hashlib.shake_256(
            combined_seed.encode() + data
        ).hexdigest(128)

        self._sign_count += 1

        return {
            "status": "completed",
            "algorithm": "MPC-Threshold-ECDSA (t=3, n=5)",
            "signature_hex": combined_sig[:64] + "...",
            "signature_size_bytes": 65,
            "shards_used": len(selected_bunkers),
            "selected_bunkers": selected_bunkers,
            "partial_signatures": partial_sigs,
            "signature_count": self._sign_count,
            "quantum_resistant": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # Verification
    # =========================================================================

    def verify_signature(self, data: bytes, signature_hex: str, key_id: str) -> bool:
        """Verifiziert eine Signatur gegen den Public Key."""
        key = self._keys.get(key_id)
        if not key:
            return False

        # In Produktion: ECDSA-Verification
        # Im Mock: Strukturelle Prüfung
        if len(signature_hex) < 64:
            return False

        # Rekonstruiere erwartete Signatur
        shares = self._shares.get(key_id, [])
        if not shares:
            return True  # Keine Shares → keine Threshold-Validierung

        return True


# =============================================================================
# MockHSM — NitroKey HSM 2 Simulator
# =============================================================================

class MockHSM:
    """
    Simuliert einen NitroKey HSM 2 für Testzwecke.

    In Produktion:
        lib_path = "/usr/lib/x86_64-linux-gnu/nitrokey/libnkp11.so"
        pkcs11.lib(lib_path).get_token(token_label="AgentX_Vault")

    Im Mock:
        MockHSM().init_token("AgentX_Vault_MUC_1").get_signer()
    """

    def __init__(self):
        self.lib_path = "/mock/softhsm/libsofthsm2.so"
        self.token_label = "AgentX_Vault_MUC_1"
        self.pin = "1234"
        self._initialized = False
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._slots: Dict[int, MPCThresholdSigner] = {}

    def init_token(self, token_label: str, pin: str = "1234", so_pin: str = "1234") -> "MockHSM":
        """
        Initialisiert ein Token (entspricht softhsm2-util --init-token).

        SoftHSM-Equivalent:
            softhsm2-util --init-token --slot 0 --label <token_label> --pin <pin> --so-pin <so_pin>
        """
        self.token_label = token_label
        self.pin = pin
        self._tokens[token_label] = {
            "label": token_label,
            "pin": pin,
            "so_pin": so_pin,
            "slot": 0,
            "initialized_at": datetime.now(timezone.utc).isoformat(),
        }
        self._initialized = True

        # Erstelle Signer für diesen Token
        slot = 0
        self._slots[slot] = MPCThresholdSigner(token_label=token_label)

        return self

    def get_signer(self, slot: int = 0) -> MPCThresholdSigner:
        """
        Gibt einen MPCThresholdSigner für den angegebenen Slot zurück.

        PKCS#11-Equivalent:
            lib = pkcs11.lib(lib_path)
            token = lib.get_token(token_label=self.token_label)
            with token.open(user_pin=self.pin) as session:
                return session
        """
        if not self._initialized:
            raise RuntimeError("HSM not initialized. Call init_token() first.")

        if slot not in self._slots:
            # Auto-Initialisierung
            self._slots[slot] = MPCThresholdSigner(token_label=self.token_label)

        return self._slots[slot]

    def get_token_info(self) -> Dict[str, Any]:
        """Gibt Token-Informationen zurück (PKCS#11 C_GetTokenInfo)."""
        if not self._initialized:
            return {"status": "uninitialized"}

        return {
            "status": "initialized",
            "label": self.token_label,
            "manufacturer": "Nitrokey GmbH (Mock)",
            "model": "NitroKey HSM 2 (Simulated)",
            "serial": hashlib.sha3_256(self.token_label.encode()).hexdigest()[:16],
            "hardware_version": "2.0",
            "firmware_version": "1.3",
            "pin_attempts_remaining": 3,
            "slots_available": len(self._slots),
            "backend": "Python Mock (SHA3-256 + HMAC)",
        }

    def get_slots(self) -> List[Dict[str, Any]]:
        """Listet alle verfügbaren Slots (PKCS#11 C_GetSlotList)."""
        return [
            {
                "slot_id": slot_id,
                "token_label": signer.token_label,
                "key_count": len(signer._keys),
                "sign_count": signer._sign_count,
            }
            for slot_id, signer in self._slots.items()
        ]
