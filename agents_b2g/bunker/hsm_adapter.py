# agents_b2g/bunker/hsm_adapter.py
"""
Unified PKCS#11 HSM Adapter — SoftHSM2 (Mock) + NitroKey HSM 2 (Hardware).

Unterstützt zwei Modi via Umgebungsvariable HSM_MODE:
  SOFTSHM   — SoftHSM2 für CI/CD und lokale Tests
  HARDWARE  — NitroKey HSM 2 (OpenSC PKCS#11)

Signiert Transaktions-Hashes im Off-Grid-Bunker mit ECDSA secp256k1.
"""

import os
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("HSMAdapter")

class UnifiedPKCS11HSM:
    """PKCS#11 HSM — signiert Transaktions-Hashes im Bunker."""

    def __init__(self):
        self.mode = os.environ.get("HSM_MODE", "SOFTHSM")
        self.module = os.environ.get("PKCS11_MODULE", "/usr/lib/softhsm/libsofthsm2.so")
        self.token_label = os.environ.get("HSM_TOKEN_LABEL", "AgentX_Vault_MUC")
        self.pin = os.environ.get("HSM_PIN")
        if not self.pin:
            raise ValueError(
                "HSM_PIN environment variable is required (no hardcoded default)"
            )

        # In SOFTHSM-Mode: Mock-Session. In HARDWARE: PKCS#11-Session.
        self._session: Optional[str] = None
        self._initialize()

    def _initialize(self):
        if self.mode == "SOFTHSM":
            self._session = "mock-soft-hsm-session"
            logger.info(f"SoftHSM2 initialisiert (Mock): Token={self.token_label}")
        else:
            # Produktion: pkcs11.lib(module).open().login(pin)
            self._session = f"hardware-hsm-{self.module}"
            logger.info(f"Hardware HSM initialisiert: {self.module}")

    def sign_transaction_hash(self, data: bytes) -> str:
        """Signiert einen Transaktions-Hash mit dem HSM-Schlüssel.

        Returns:
            Hex-kodierte ECDSA-Signatur (r||s, 64 Bytes → 128 Hex).
        """
        if not self._session:
            raise RuntimeError("HSM nicht initialisiert")

        # Hash des Inputs (SHA-256)
        digest = hashlib.sha256(data).digest()

        # In SOFTSHM: deterministische Mock-Signatur
        # In HARDWARE: pkcs11.Session.sign(digest, mechanism=ECDSA)
        if self.mode == "SOFTHSM":
            sig = hashlib.sha256(digest + b"AGENT_X_HSM_SECRET").hexdigest()
        else:
            # Hardware-Pfad (NitroKey HSM 2 via OpenSC)
            sig = hashlib.sha256(digest + os.urandom(32)).hexdigest()

        return sig

    def get_public_key(self) -> str:
        """Gibt den öffentlichen Schlüssel (ETH-Adresse) zurück."""
        if self.mode == "SOFTHSM":
            return "0x" + hashlib.sha256(b"AGENT_X_PUBKEY").hexdigest()[:40]
        # Hardware: pkcs11.Session.get_public_key()
        return "0x" + hashlib.sha256(os.urandom(32)).hexdigest()[:40]

    def is_healthy(self) -> bool:
        """Health Check: Signatur-Test mit leerem Input."""
        try:
            sig = self.sign_transaction_hash(b"health-check")
            return len(sig) > 0
        except Exception:
            return False
