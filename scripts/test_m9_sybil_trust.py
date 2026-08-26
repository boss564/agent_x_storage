#!/usr/bin/env python3
"""M9 Sybil smoke: Trust α/β only moves on BHO Δ≠0.

Not a Pre-Reg. Engineering gate for Sybil-Schutz.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents_b2g.emergence.kanten_ledger import LedgerBook  # noqa: E402


def main() -> int:
    book = LedgerBook(trust_settlement_only=True, latency_mode="ewma")
    assert book.trust_settlement_only is True

    # Spam: many successes without settlement — trust must stay prior (α=β=1 → 0.5)
    for t in range(50):
        book.update("S", "T", t, success=True, signed_net=0.0, latency=1.0)
    e = book.get("S", "T")
    assert e is not None
    assert e.interaction_count > 0.0  # ops counter still moves (may decay)
    assert abs(e.alpha - 1.0) < 1e-9 and abs(e.beta - 1.0) < 1e-9
    assert abs(e.trust_score() - 0.5) < 1e-9, f"trust leaked: {e.trust_score()}"
    assert book.trust_spam_suppressed == 50

    # Settlement touch: trust moves
    book.update("S", "T", 50, success=True, signed_net=100.0, latency=1.0)
    e = book.get("S", "T")
    assert e is not None
    assert e.alpha == 2.0  # prior 1 + one settlement success
    assert e.trust_score() > 0.5

    # Vorher-Zustand: trust on every interaction
    legacy = LedgerBook(trust_settlement_only=False, latency_mode="ewma")
    for t in range(10):
        legacy.update("A", "B", t, success=True, signed_net=0.0, latency=1.0)
    el = legacy.get("A", "B")
    assert el is not None and el.alpha == 11.0  # 1 prior + 10
    assert legacy.trust_spam_suppressed == 0

    print("M9_SYBIL_SMOKE: PASS")
    print(f"  spam_suppressed={book.trust_spam_suppressed}")
    print(f"  trust_after_settlement={e.trust_score():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
