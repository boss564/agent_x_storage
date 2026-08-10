#!/usr/bin/env python3
"""DIDRegistry — Dynamic device identity registry with demo and production modes.

Replaces the hardcoded VALID_SIGNATURES dict with a registry that can be
backed by an Identity Chain API, an HSM adapter, or a local demo dataset.

Default-deny: a device is only trusted if it is registered AND its signature
matches the stored public key.

Demo mode: 9 pre-loaded DIDs (identical to the former VALID_SIGNATURES).
Production mode: sync from Identity Chain REST API or HSM PKCS#11 adapter.

Usage:
  from agents_b2g.crew.did_registry import get_registry, DIDRegistry
  reg = get_registry()                           # demo mode (default)
  reg = get_registry(demo_mode=False)            # production mode
  result = reg.verify("MEIER_BAU_GMBH", "0xVALID_SIG_3", payload)
  if not result.valid:
      raise PermissionError(result.reason)
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("DIDRegistry")


# ─── Data Classes ───────────────────────────────────────────────────────────

class DIDStatus(Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"


@dataclass
class DIDRecord:
    did: str
    public_key: str
    status: DIDStatus = DIDStatus.ACTIVE
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    last_seen: float = 0.0
    failed_attempts: int = 0


@dataclass
class VerificationResult:
    valid: bool
    reason: str = ""
    did_status: Optional[DIDStatus] = None
    public_key: Optional[str] = None


# ─── Demo DIDs ──────────────────────────────────────────────────────────────

DEMO_DIDS: Dict[str, Tuple[str, Dict]] = {
    "MEIER_BAU_GMBH":     ("0xVALID_SIG_3",     {"role": "CONTRACTOR", "sector": "BAU"}),
    "ESP32_DEMO_01":      ("0xVALID_SIG_1",     {"role": "SENSOR",    "type": "DHT22"}),
    "ESP32_SOLAR_MUC":    ("0xSOLAR_SIG_2",     {"role": "SENSOR",    "type": "SOLAR"}),
    "CONTRACTOR_4012":    ("0xCONTRACTOR_SIG",  {"role": "CONTRACTOR", "sector": "ALL"}),
    "INSPECTOR_MUC":      ("0xINSPECTOR_SIG",   {"role": "INSPECTOR",  "sector": "BAU"}),
    "TANKER_ALPHA":       ("0xTANKER_A_SIG",    {"role": "TREASURY"}),
    "KLINIKBAU_AG":       ("0xKLINIK_SIG",      {"role": "CONTRACTOR", "sector": "KLINIK"}),
    "TREASURY_MAIN":      ("0xTREASURY_SIG",    {"role": "TREASURY"}),
    "GOVERNANCE_COUNCIL": ("0xGOV_SIG",         {"role": "GOVERNANCE"}),
    "STAKING_POOL":       ("0xSTAKING_SIG",     {"role": "STAKING"}),
}


# ─── Registry ───────────────────────────────────────────────────────────────

class DIDRegistry:
    """Dynamic device identity registry.

    Demo mode (default): pre-loaded DIDs with string-comparison verification.
    Production mode: sync from Identity Chain or HSM; crypto verification.
    """

    def __init__(self, demo_mode: bool = True, verifier: Any = None):
        self.records: Dict[str, DIDRecord] = {}
        self.demo_mode = demo_mode
        self._identity_chain_url: Optional[str] = None
        self._hsm: Any = None
        self._verifier: Any = verifier  # Injected Ed25519/ECDSA verifier

        if demo_mode:
            self._load_demo_dids()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def _load_demo_dids(self):
        for did, (pubkey, meta) in DEMO_DIDS.items():
            self.records[did] = DIDRecord(
                did=did, public_key=pubkey, status=DIDStatus.ACTIVE,
                metadata=meta, created_at=time.time(),
            )
        logger.info("DIDRegistry: %d demo DIDs loaded", len(self.records))

    # ── CRUD ────────────────────────────────────────────────────────────

    def register(self, did: str, public_key: str, metadata: Dict = None) -> bool:
        if did in self.records and self.records[did].status == DIDStatus.ACTIVE:
            logger.debug("DID %s already registered", did)
            return False
        self.records[did] = DIDRecord(
            did=did, public_key=public_key, status=DIDStatus.ACTIVE,
            metadata=metadata or {}, created_at=time.time(),
        )
        logger.info("DID %s registered", did)
        return True

    def revoke(self, did: str, reason: str = "") -> bool:
        r = self.records.get(did)
        if not r:
            return False
        r.status = DIDStatus.REVOKED
        r.metadata["revocation_reason"] = reason
        logger.warning("DID %s REVOKED: %s", did, reason)
        return True

    def suspend(self, did: str, reason: str = "") -> bool:
        r = self.records.get(did)
        if not r:
            return False
        r.status = DIDStatus.SUSPENDED
        r.metadata["suspension_reason"] = reason
        logger.warning("DID %s SUSPENDED: %s", did, reason)
        return True

    def reinstate(self, did: str, approver_a: str, approver_b: str,
                  reason: str = "") -> bool:
        """Restore a revoked/suspended DID with dual approval (Vier-Augen-Prinzip).

        Requires two distinct approver identifiers. Both must be non-empty and
        different from each other. This prevents a single compromised admin
        account from reinstating a blocked attacker.

        Returns True if the DID was successfully reinstated.
        """
        r = self.records.get(did)
        if not r:
            logger.warning("Reinstate failed: DID %s not found", did)
            return False
        if r.status not in (DIDStatus.REVOKED, DIDStatus.SUSPENDED):
            logger.info("DID %s is already %s, no reinstatement needed", did, r.status.value)
            return True
        if not approver_a or not approver_b or approver_a == approver_b:
            logger.error(
                "Reinstate denied: dual approval required (got a=%s, b=%s)",
                approver_a[:8] if approver_a else "empty",
                approver_b[:8] if approver_b else "empty",
            )
            return False

        r.status = DIDStatus.ACTIVE
        r.failed_attempts = 0
        r.metadata["reinstated_by"] = [approver_a, approver_b]
        r.metadata["reinstated_reason"] = reason
        r.metadata["reinstated_at"] = time.time()
        logger.info(
            "DID %s REINSTATED by %s + %s: %s",
            did, approver_a[:12], approver_b[:12], reason,
        )
        return True

    def get(self, did: str) -> Optional[DIDRecord]:
        return self.records.get(did)

    def is_active(self, did: str) -> bool:
        r = self.records.get(did)
        return r is not None and r.status == DIDStatus.ACTIVE

    # ── Verification ────────────────────────────────────────────────────

    def verify(self, device_id: str, signature: str,
               payload: Dict = None) -> VerificationResult:
        """Verify a device ID + signature against the registry.

        Returns VerificationResult with .valid and .reason.
        Default-deny: unknown devices and mismatched signatures are rejected.
        """
        # 1. Device must be registered
        record = self.records.get(device_id)
        if record is None:
            return VerificationResult(False, f"UNKNOWN_DEVICE:{device_id}")

        # 2. Device must be active
        if record.status != DIDStatus.ACTIVE:
            return VerificationResult(
                False, f"DID_{record.status.value}:{device_id}",
                did_status=record.status,
            )

        # 3. Signature must match
        if self.demo_mode:
            # String comparison (demo)
            if signature != record.public_key:
                record.failed_attempts += 1
                record.last_seen = time.time()
                # 3 failures → auto-revoke
                if record.failed_attempts >= 3:
                    self.revoke(device_id, "3_FAILED_ATTEMPTS")
                    return VerificationResult(
                        False, f"DID_REVOKED:{device_id}",
                        did_status=DIDStatus.REVOKED,
                    )
                return VerificationResult(
                    False, f"SIG_MISMATCH:{signature[:16] if signature else 'MISSING'}",
                    did_status=record.status, public_key=record.public_key,
                )
        else:
            # Cryptographic verification (production)
            if not self._verify_crypto(record.public_key, signature, payload or {}):
                record.failed_attempts += 1
                record.last_seen = time.time()
                return VerificationResult(
                    False, "CRYPTO_VERIFY_FAILED",
                    did_status=record.status, public_key=record.public_key,
                )

        # Success
        record.last_seen = time.time()
        record.failed_attempts = 0
        return VerificationResult(True, "SIG_OK", record.status, record.public_key)

    def _verify_crypto(self, pubkey: str, signature: str, payload: Dict) -> bool:
        """Fail-closed: rejects unless a real Ed25519/ECDSA verifier is injected.

        In demo_mode this method is never called (string comparison is used instead).
        In production mode, callers MUST inject a verifier via __init__(verifier=...)
        or via inject_verifier(). Without one, all verifications are rejected.
        """
        # No verifier injected → reject (fail-closed, not fail-open)
        if self._verifier is None:
            logger.error(
                "_verify_crypto called without injected verifier — "
                "rejecting. Inject via registry.inject_verifier(adapter) "
                "or DIDRegistry(verifier=hsm_adapter)."
            )
            return False

        if not signature or not pubkey:
            return False

        try:
            # Delegate to injected verifier (e.g. HSM adapter with ECDSA/Ed25519)
            return self._verifier.verify(pubkey, signature, payload)
        except Exception as e:
            logger.error("Crypto verification failed: %s", e)
            return False

    def inject_verifier(self, verifier: Any) -> None:
        """Inject an Ed25519/ECDSA verifier for production use.

        The verifier must expose:
            verifier.verify(pubkey: str, signature: str, payload: dict) -> bool

        Example:
            from agents_b2g.bunker.hsm_adapter import UnifiedPKCS11HSM
            registry.inject_verifier(UnifiedPKCS11HSM())
        """
        self._verifier = verifier
        self.demo_mode = False
        logger.info("Crypto verifier injected — production mode active")

    # ── Sync ────────────────────────────────────────────────────────────

    def sync_from_chain(self, url: str) -> int:
        """Sync DIDs from an Identity Chain REST API. Returns count of new DIDs."""
        self._identity_chain_url = url
        try:
            import urllib.request
            with urllib.request.urlopen(f"{url}/dids/active", timeout=5) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            logger.error("Identity Chain sync failed: %s", e)
            return 0

        count = 0
        for entry in data.get("dids", []):
            if self.register(entry["did"], entry["public_key"], entry.get("metadata")):
                count += 1
        logger.info("Synced %d DIDs from Identity Chain", count)
        return count

    def sync_from_hsm(self, hsm: Any) -> int:
        """Sync DIDs from an HSM adapter (NitroKey/YubiKey via PKCS#11)."""
        self._hsm = hsm
        count = 0
        try:
            keys = hsm.list_keys() if hasattr(hsm, "list_keys") else []
        except Exception as e:
            logger.error("HSM sync failed: %s", e)
            return 0

        for did, pubkey in keys:
            if self.register(did, pubkey, {"source": "HSM"}):
                count += 1
        logger.info("Synced %d DIDs from HSM", count)
        return count

    # ── Status ──────────────────────────────────────────────────────────

    def summary(self) -> Dict:
        active = sum(1 for r in self.records.values() if r.status == DIDStatus.ACTIVE)
        revoked = sum(1 for r in self.records.values() if r.status == DIDStatus.REVOKED)
        return {
            "total": len(self.records), "active": active, "revoked": revoked,
            "suspended": sum(1 for r in self.records.values() if r.status == DIDStatus.SUSPENDED),
            "demo_mode": self.demo_mode,
            "identity_chain": self._identity_chain_url,
            "hsm_connected": self._hsm is not None,
            "public_keys": {did: r.public_key for did, r in self.records.items() if r.status == DIDStatus.ACTIVE},
        }

    def to_valid_signatures_dict(self) -> Dict[str, str]:
        """Export as a dict compatible with the old VALID_SIGNATURES format."""
        return {did: r.public_key for did, r in self.records.items()
                if r.status == DIDStatus.ACTIVE}


# ─── Singleton ──────────────────────────────────────────────────────────────

_registry: Optional[DIDRegistry] = None


def get_registry(demo_mode: bool = True) -> DIDRegistry:
    """Get or create the global DIDRegistry singleton."""
    global _registry
    if _registry is None or _registry.demo_mode != demo_mode:
        _registry = DIDRegistry(demo_mode=demo_mode)
    return _registry
