#!/usr/bin/env python3
"""M7 production smoke: MAD reject + poison log + trimmed_m7 default.

Not a Pre-Reg. Engineering gate for Latenz-Poisoning-Schutz.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents_b2g.emergence.kanten_ledger import (  # noqa: E402
    LATENCY_MODE_EWMA,
    LATENCY_MODE_M7_TRIM,
    LATENCY_N_MIN,
    LedgerBook,
)


def main() -> int:
    poison_cb: list = []
    book = LedgerBook(
        latency_mode=LATENCY_MODE_M7_TRIM,
        on_latency_poison=poison_cb.append,
    )
    assert book.latency_mode == LATENCY_MODE_M7_TRIM

    # Fill window with stable latencies (settlement touches)
    for t in range(LATENCY_N_MIN):
        book.update("A", "B", t, success=True, signed_net=1.0, latency=1.0)

    e = book.get("A", "B")
    assert e is not None and e.latency_evaluable
    baseline = e.avg_latency
    n_before = len(e.latency_samples)

    # Extreme delay spike — must be rejected (not appended)
    book.update("A", "B", LATENCY_N_MIN, success=True, signed_net=1.0, latency=1e6)
    e = book.get("A", "B")
    assert e is not None
    assert len(e.latency_samples) == n_before, "spike must not enter window"
    assert abs(e.avg_latency - baseline) < 0.5, "ℓ must stay near baseline"
    assert len(book.latency_poison_events) >= 1
    assert len(poison_cb) >= 1
    assert poison_cb[-1]["reason"] == "mad_gate_reject"

    # Thin window: no MAD reject (§3.5.2)
    thin = LedgerBook(latency_mode=LATENCY_MODE_M7_TRIM)
    for t in range(5):
        thin.update("X", "Y", t, success=True, signed_net=1.0, latency=1.0)
    thin.update("X", "Y", 5, success=True, signed_net=1.0, latency=1e6)
    et = thin.get("X", "Y")
    assert et is not None
    assert len(et.latency_samples) == 6, "thin window accepts samples"
    assert len(thin.latency_poison_events) == 0

    # Vorher-Zustand override still available
    legacy = LedgerBook(latency_mode=LATENCY_MODE_EWMA)
    assert legacy.latency_mode == LATENCY_MODE_EWMA

    print("M7_POISON_SMOKE: PASS")
    print(f"  default_mode={LedgerBook().latency_mode}")
    print(f"  poison_events={len(book.latency_poison_events)}")
    print(f"  baseline_ell={baseline:.4f} after_spike={e.avg_latency:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
