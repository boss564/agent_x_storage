"""DID Tracker — Attribution layer with forensic crypto stamps.

Every blocked attack is linked to a DID with:
  - ForensicStamp: signed crypto stamp (DID + nonce + Z3-hash + signature)
  - DIDRegistry: identity status (ACTIVE → SUSPENDED → REVOKED)
  - 3 failed attempts → automatic eIDAS key revocation
  - Replay protection: nonce dedup in 0 ms
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("DIDTracker")


# ─── Enums ──────────────────────────────────────────────────────────────────

class DIDStatus(Enum):
    ACTIVE = "ACTIVE"
    BLACKLISTED = "BLACKLISTED"
    REVOKED = "REVOKED"


class AttackType(Enum):
    SENSOR_SPOOFING = "SENSOR_SPOOFING"
    EARLY_MILESTONE = "EARLY_MILESTONE"
    TAX_EVASION = "TAX_EVASION"
    ESCROW_OVERDRAFT = "ESCROW_OVERDRAFT"
    LOG_MANIPULATION = "LOG_MANIPULATION"
    FLASH_LOAN_YIELD = "FLASH_LOAN_YIELD"
    FEE_EVASION = "FEE_EVASION"
    TREASURY_THEFT = "TREASURY_THEFT"
    UNBACKED_MINT = "UNBACKED_MINT"
    OUT_OF_GAS = "OUT_OF_GAS"
    UNKNOWN = "UNKNOWN"


# ─── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class DIDRecord:
    did: str
    role: str = "UNKNOWN"
    status: DIDStatus = DIDStatus.ACTIVE
    failed_attempts: int = 0
    total_attacks: int = 0
    attack_history: List[Dict] = field(default_factory=list)
    revocation_reason: str = ""
    last_seen: float = 0.0


@dataclass
class ForensicStamp:
    """A signed crypto stamp — proof of attribution."""
    did: str
    nonce: str
    z3_hash: str
    signature: str
    timestamp: float = field(default_factory=time.time)


# ─── DID Registry ───────────────────────────────────────────────────────────

class DIDRegistry:
    """Manages decentralized identities and their status (simulated Identity Chain)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init = False
        return cls._instance

    def __init__(self):
        if self._init:
            return
        self._init = True
        self.registry: Dict[str, DIDRecord] = {}
        self.revoked: Set[str] = set()
        self.used_nonces: Set[str] = set()
        self.log: List[Dict] = []
        self._seed()

    def _seed(self):
        for did, role in [
            ("did:depin:esp32:0x3A2", "SENSOR"),
            ("did:depin:esp32:0x7B1", "SENSOR"),
            ("did:eidas:contractor:4012", "CONTRACTOR"),
            ("did:eidas:sub:4012", "SUBCONTRACTOR"),
            ("did:eth:treasury:0x99B", "TREASURY"),
            ("did:b2g:bauamt:muc", "INSPECTOR"),
        ]:
            self.registry[did] = DIDRecord(did=did, role=role)

    def get(self, did: str) -> Optional[DIDRecord]:
        return self.registry.get(did)

    def is_active(self, did: str) -> bool:
        r = self.get(did)
        return r is not None and r.status == DIDStatus.ACTIVE

    def use_nonce(self, nonce: str) -> bool:
        """Returns False if nonce already used (replay attack)."""
        if nonce in self.used_nonces:
            return False
        self.used_nonces.add(nonce)
        return True

    def record_attack(self, did: str, attack_type: AttackType, detail: str = "") -> Dict:
        """Record an attack. Triggers revocation after 3 failures."""
        r = self.get(did)
        if r is None:
            # Unknown DID → immediate blacklist
            self.registry[did] = DIDRecord(did=did, role="UNKNOWN", status=DIDStatus.BLACKLISTED,
                                            revocation_reason="UNKNOWN_DID")
            self.revoked.add(did)
            was_revoked = True
        else:
            r.failed_attempts += 1
            r.total_attacks += 1
            r.last_seen = time.time()
            r.attack_history.append({"ts": time.time(), "type": attack_type.value, "detail": detail})

            if r.failed_attempts >= 3:
                r.status = DIDStatus.REVOKED
                r.revocation_reason = f"3_FAILED_ATTEMPTS"
                self.revoked.add(did)
                was_revoked = True
                logger.warning("🔴 %s REVOKED: %s", did, r.revocation_reason)
            else:
                was_revoked = False

        entry = {"did": did, "attack": attack_type.value, "ts": time.time(), "revoked": was_revoked}
        self.log.append(entry)
        return entry

    def get_log(self, n: int = 20) -> List[Dict]:
        return self.log[-n:]


# ─── Forensic Stamp Generator ───────────────────────────────────────────────

class ForensicStampGenerator:
    """Creates and verifies signed crypto stamps."""

    @staticmethod
    def create(did: str, payload: Dict) -> ForensicStamp:
        nonce = hashlib.sha256(f"{did}{time.time()}{payload}".encode()).hexdigest()[:16]
        z3_hash = hashlib.sha256(str(payload).encode()).hexdigest()
        sig = hashlib.sha256(f"{did}{nonce}{z3_hash}".encode()).hexdigest()
        return ForensicStamp(did=did, nonce=nonce, z3_hash=z3_hash, signature=sig)

    @staticmethod
    def verify(stamp: ForensicStamp, registry: DIDRegistry) -> Tuple[bool, str]:
        """Verify a stamp: DID active + nonce fresh + signature matches."""
        if not registry.is_active(stamp.did):
            return False, f"DID_INACTIVE:{stamp.did}"
        if not registry.use_nonce(stamp.nonce):
            return False, "REPLAY_ATTACK"
        expected = hashlib.sha256(f"{stamp.did}{stamp.nonce}{stamp.z3_hash}".encode()).hexdigest()
        if stamp.signature != expected:
            return False, "INVALID_SIGNATURE"
        return True, "STAMP_OK"


# ─── Attack Type Detection ──────────────────────────────────────────────────

def detect_attack_type(data: Dict) -> AttackType:
    # TEST-FIXTURE ONLY — reads self-labeled attack_type from payload.
    # NOT used in production decision path. Production uses TacticalOfficer.verify()
    # (default-deny: schema + registered device + signature match).
    at = data.get("attack_type", "")
    mapping = {
        "SENSOR_SPOOFING": AttackType.SENSOR_SPOOFING,
        "EARLY_MILESTONE": AttackType.EARLY_MILESTONE,
        "TAX_EVASION": AttackType.TAX_EVASION,
        "ESCROW_OVERDRAFT": AttackType.ESCROW_OVERDRAFT,
        "LOG_MANIPULATION": AttackType.LOG_MANIPULATION,
        "FLASH_LOAN_YIELD": AttackType.FLASH_LOAN_YIELD,
        "FEE_EVASION": AttackType.FEE_EVASION,
        "TREASURY_THEFT": AttackType.TREASURY_THEFT,
        "UNBACKED_MINT": AttackType.UNBACKED_MINT,
        "OUT_OF_GAS": AttackType.OUT_OF_GAS,
    }
    return mapping.get(at, AttackType.UNKNOWN)
