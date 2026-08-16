"""AirBHO ledger adapter — double-entry, Decimal, zero-sum.

Air-layer binding of the BHO zero-sum law (Key B2G Decision): every
neutralization/compensation pair keeps the books balanced. |delta| >
0.01 EUR trips the halt flag, mirroring the ground-side payment-stop
rule. Production binding writes through to golden_books/ (5 books +
journal); this adapter keeps the in-process journal so Schwarm 2/3 can
verify balance without I/O.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import List


@dataclass(frozen=True)
class JournalEntry:
    entry_id: int
    ts: float
    account: str
    dedup_key: str
    amount: Decimal
    reason: str


class AirBHOLedger:
    """Implements the A06 LedgerHook + A07 compensation booking."""

    HALT_THRESHOLD = Decimal("0.01")   # BHO: |Δ| > 0.01€ halts payments

    def __init__(self):
        self._entries: List[JournalEntry] = []
        self._ids = itertools.count(1)
        self._lock = threading.RLock()
        self.halted = False

    # -- booking ----------------------------------------------------------

    def book_neutralization(self, dedup_key: str, state_root: str,
                            reason: str) -> None:
        """Destruction pair (A06 debit leg): promise destroyed, liability
        parked until compensation."""
        self._book("air:neutralizations", dedup_key, Decimal("1.00"), reason)
        self._book("air:quarantine_liability", dedup_key, Decimal("-1.00"), reason)

    def book_compensation(self, dedup_key: str, compensation_id: str,
                          reason: str) -> None:
        """Compensation pair (A07 credit leg): liability released against
        the compensation expense account."""
        ref = f"comp:{compensation_id}"
        self._book("air:quarantine_liability", dedup_key, Decimal("1.00"), ref)
        self._book("air:compensation_expense", dedup_key, Decimal("-1.00"), ref)

    def _book(self, account: str, dedup_key: str, amount: Decimal,
              reason: str) -> None:
        with self._lock:
            self._entries.append(JournalEntry(
                entry_id=next(self._ids), ts=time.time(), account=account,
                dedup_key=dedup_key, amount=amount, reason=reason,
            ))
            if abs(self.delta()) > self.HALT_THRESHOLD:
                self.halted = True

    # -- queries ---------------------------------------------------------

    def delta(self) -> Decimal:
        with self._lock:
            return sum((e.amount for e in self._entries), Decimal("0"))

    def is_balanced(self) -> bool:
        return abs(self.delta()) <= self.HALT_THRESHOLD

    def account_balance(self, account: str) -> Decimal:
        with self._lock:
            return sum((e.amount for e in self._entries
                        if e.account == account), Decimal("0"))

    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)
