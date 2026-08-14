"""Shared finality types for the air interceptor layer.

Defines the three-tier finality ladder (L0/L1/L2), the attestation envelope,
and the finality state machine. Consumed by A02 (fast-path), A03
(soft-finality), and later Schwarm 2 (CAS).

Code comments in English per project convention.
"""

from __future__ import annotations

import enum
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Optional


class FinalityTier(enum.IntEnum):
    """Three-tier finality ladder."""

    SPECULATIVE = 0   # in flight, freely revocable
    SOFT_FINAL = 1    # A03-attested, reversible only via compensation
    HARD_FINAL = 2    # anchored on L1, irreversible


class FinalityState(enum.Enum):
    """Finality state machine states."""

    RECEIVED = "received"
    VERIFIED = "verified"
    SOFT_FINAL = "soft_final"
    ANCHORED = "anchored"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


# Terminal states: every SOFT_FINAL must end ANCHORED or ROLLED_BACK.
TERMINAL_STATES = frozenset({
    FinalityState.ANCHORED,
    FinalityState.ROLLED_BACK,
    FinalityState.REJECTED,
})


# Legal transitions — core invariant: SOFT_FINAL → {ANCHORED, ROLLED_BACK}.
FINALITY_TRANSITIONS = {
    FinalityState.RECEIVED: {FinalityState.VERIFIED, FinalityState.REJECTED},
    FinalityState.VERIFIED: {FinalityState.SOFT_FINAL, FinalityState.ROLLED_BACK},
    FinalityState.SOFT_FINAL: {FinalityState.ANCHORED, FinalityState.ROLLED_BACK},
    FinalityState.ANCHORED: set(),
    FinalityState.ROLLED_BACK: set(),
    FinalityState.REJECTED: set(),
}


@dataclass(frozen=True)
class DedupKey:
    """Replay-protection key: (sender, nonce, intent_hash).

    Uses intent_hash rather than tx_hash so NATS redeliveries of the
    same logical payment dedup correctly.
    """

    sender: str
    nonce: int
    intent_hash: str

    def render(self) -> str:
        return f"{self.sender}:{self.nonce}:{self.intent_hash}"


def build_dedup_key(sender: str, nonce: int, intent_hash: str) -> DedupKey:
    return DedupKey(sender=sender, nonce=nonce, intent_hash=intent_hash)


@dataclass(frozen=True)
class AttestationEnvelope:
    """Signed attestation binding a TX to a state root at a tier.

    The envelope is the unit of the soft-finality promise. Idempotent:
    resubmitting the same dedup_key yields the identical envelope.
    """

    tx_hash: str
    state_root: str
    tier: int
    signer: str
    ts: float
    expiry: float
    epoch: int
    seq: int
    dedup_key: str
    signature: Optional[str] = None

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        return now > self.expiry

    def digest(self) -> str:
        """Stable content hash for signature + GoBD audit chaining."""
        payload = (
            f"{self.tx_hash}|{self.state_root}|{self.tier}|{self.signer}|"
            f"{self.ts:.6f}|{self.expiry:.6f}|{self.epoch}|{self.seq}|"
            f"{self.dedup_key}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_audit_dict(self) -> dict:
        d = asdict(self)
        d["digest"] = self.digest()
        return d
