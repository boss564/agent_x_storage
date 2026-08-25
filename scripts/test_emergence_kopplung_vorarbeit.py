#!/usr/bin/env python3
"""Vorarbeiten zur Emergenz-Kopplungs-Pre-Reg (ohne κ > 0).

docs/EMERGENZ_KOPPLUNG_PREREG.md §7:
  1. StickySelector.freeze() unit-tested
  2. Shuffle degree-preserving + role-segment-internal
  3. Determinismus κ = 0 (zwei Läufe byte-identisch)

Usage:
    python3 scripts/test_emergence_kopplung_vorarbeit.py
"""
from __future__ import annotations

import hashlib
import os
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "agents_b2g" / "emergence"))

from partner_select import (  # noqa: E402
    StickySelector,
    assert_degree_preserving,
    permute_sticky_map,
)

PASS, FAIL = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


class _Cand:
    def __init__(self, id_: str, load: int = 0):
        self.id = id_
        self.load = load


def test_freeze() -> None:
    print("\n=== V1 StickySelector.freeze() ===")
    sticky = StickySelector(threshold=8)
    cands = [_Cand("p0", 0), _Cand("p1", 0), _Cand("p2", 100)]
    loads = {c.id: c.load for c in cands}

    def load_of(c: _Cand) -> int:
        return loads[c.id]

    # Warm-up: establish sticky partner under equal load
    p = sticky.select("s0", "evaluator", cands, load_of)
    check("V1.1 partner established before freeze", p.id in {"p0", "p1", "p2"})
    established = p.id

    snap = sticky.freeze()
    check("V1.2 freeze() returns map copy", ( "s0", "evaluator") in snap and sticky.frozen)
    check("V1.3 snapshot matches", sticky.snapshot()[("s0", "evaluator")] == established)

    # After freeze: even extreme load must not switch
    loads[established] = 10_000
    for c in cands:
        if c.id != established:
            loads[c.id] = 0
    p2 = sticky.select("s0", "evaluator", cands, load_of)
    check("V1.4 frozen ignores load divergence", p2.id == established)

    # Mutating returned freeze copy must not alter internal map
    snap[("s0", "evaluator")] = "TAMPER"
    check(
        "V1.5 freeze() return is a copy",
        sticky.last_partner_id("s0", "evaluator") == established,
    )

    # Missing key while frozen → pins on first sight (no switch later)
    sticky2 = StickySelector()
    sticky2.select("s0", "evaluator", cands, load_of)
    sticky2.freeze()
    loads["p0"] = loads["p1"] = loads["p2"] = 0
    p_new = sticky2.select("s_new", "evaluator", cands, load_of)
    p_new2 = sticky2.select("s_new", "evaluator", cands, load_of)
    check("V1.6 frozen novel key pins once", p_new.id == p_new2.id)

    sticky.unfreeze()
    loads[established] = 10_000
    p3 = sticky.select("s0", "evaluator", cands, load_of)
    check("V1.7 unfreeze allows switch", p3.id != established)


def test_shuffle() -> None:
    print("\n=== V2 degree-preserving role-segment shuffle ===")
    frozen = {
        ("s0", "evaluator"): "e0",
        ("s1", "evaluator"): "e1",
        ("s2", "evaluator"): "e0",
        ("s3", "economic"): "x0",
        ("s4", "economic"): "x1",
        ("s5", "economic"): "x1",
    }
    shuffled = permute_sticky_map(frozen, seed=7)
    try:
        assert_degree_preserving(frozen, shuffled)
        ok = True
        detail = ""
    except AssertionError as exc:
        ok = False
        detail = str(exc)
    check("V2.1 assert_degree_preserving passes", ok, detail)

    # Same keys
    check("V2.2 same edge keys", set(frozen) == set(shuffled))

    # Per-role partner multiset
    for role in ("evaluator", "economic"):
        o = sorted(p for (s, r), p in frozen.items() if r == role)
        s = sorted(p for (s, r), p in shuffled.items() if r == role)
        check(f"V2.3 multiset preserved ({role})", o == s)

    # Cross-role: shuffled evaluator partners ⊆ original evaluator partner set
    # (already covered by multiset); explicit: no economic id in evaluator slots
    econ_ids = {p for (s, r), p in frozen.items() if r == "economic"}
    eval_shuffled = {p for (s, r), p in shuffled.items() if r == "evaluator"}
    check(
        "V2.4 role-segment internal (no cross-role partners)",
        eval_shuffled.isdisjoint(econ_ids),
    )
    leaked = any(
        shuffled[(s, r)] not in {p for (ss, rr), p in frozen.items() if rr == r}
        for (s, r) in frozen
    )
    check("V2.5 every target in original role partner set", not leaked)

    # Non-identity when diversity exists
    check(
        "V2.6 not fixed-point (when diversity allows)",
        shuffled != frozen,
        detail=str(shuffled),
    )

    # Deterministic in seed
    a = permute_sticky_map(frozen, seed=7)
    b = permute_sticky_map(frozen, seed=7)
    c = permute_sticky_map(frozen, seed=8)
    check("V2.7 shuffle deterministic in seed", a == b and a != c)

    # load_map + freeze for Arm C wiring
    sticky = StickySelector()
    sticky.load_map(shuffled, freeze=True)
    check(
        "V2.8 load_map freezes shuffled map",
        sticky.frozen and sticky.snapshot() == shuffled,
    )


def test_determinism_kappa0() -> None:
    print("\n=== V3 Determinismus κ = 0 (§5.2 D1/D2) ===")
    import numpy as np
    from agents_b2g.emergence.adapter_agentx import capture
    from agents_b2g.emergence.coupling import init_timing, oscillator_from_gas

    class _Gas:
        fee_per_action = 0.8

    class _Agent:
        def __init__(self, id_: str):
            self.id = id_

    c0 = oscillator_from_gas(_Gas(), agent_id="agent-a", run_seed=0).charge
    c1 = oscillator_from_gas(_Gas(), agent_id="agent-a", run_seed=1).charge
    c0b = oscillator_from_gas(_Gas(), agent_id="agent-a", run_seed=0).charge
    check("V3.0a oscillator_from_gas run_seed changes charge", c0 != c1)
    check("V3.0b oscillator_from_gas same run_seed stable", c0 == c0b)

    a0, a1 = _Agent("agent-a"), _Agent("agent-a")
    init_timing(a0, base_interval=1.0, run_seed=0)
    init_timing(a1, base_interval=1.0, run_seed=1)
    check("V3.0c init_timing run_seed changes phase", a0.phase != a1.phase)
    a0b = _Agent("agent-a")
    init_timing(a0b, base_interval=1.0, run_seed=0)
    check("V3.0d init_timing same run_seed stable", a0.phase == a0b.phase)
    # Phase must not be derived from fee/base_interval as hash input
    a_fee = _Agent("agent-a")
    init_timing(a_fee, base_interval=2.0, run_seed=0)
    # Same agent_id|seed → same fractional hash; scaled by base_interval
    check(
        "V3.0e phase scales with base_interval only as multiplier",
        abs(a_fee.phase - 2.0 * a0.phase) < 1e-12,
    )

    # D1/D2 on interval path (default): run_seed → init_timing phase (§5.1).
    t1 = capture(cycles=64, full=True, kappa=0.0, epsilon=0.0, run_seed=1)
    t2 = capture(cycles=64, full=True, kappa=0.0, epsilon=0.0, run_seed=1)

    h1 = hashlib.sha256(np.ascontiguousarray(t1.states).tobytes()).hexdigest()
    h2 = hashlib.sha256(np.ascontiguousarray(t2.states).tobytes()).hexdigest()
    check(
        "V3.1 D1 same run_seed → byte-identical states (interval)",
        h1 == h2,
        detail=f"{h1[:12]} vs {h2[:12]}",
    )
    check(
        "V3.2 D1 same run_seed → identical message logs",
        list(t1.messages) == list(t2.messages),
    )

    t3 = capture(cycles=64, full=True, kappa=0.0, epsilon=0.0, run_seed=2)
    h3 = hashlib.sha256(np.ascontiguousarray(t3.states).tobytes()).hexdigest()
    check(
        "V3.3 D2 different run_seed → different states (interval)",
        h3 != h1,
        detail=f"seed1={h1[:12]} seed2={h3[:12]}",
    )
    check(
        "V3.4 phase exposed in state matrix",
        "phase" in getattr(t1, "state_keys", []),
    )

    # Oscillator path still D1/D2 (both hooks live)
    r1 = capture(cycles=32, full=True, kappa=0.0, run_seed=1, relax=True)
    r2 = capture(cycles=32, full=True, kappa=0.0, run_seed=2, relax=True)
    hr1 = hashlib.sha256(np.ascontiguousarray(r1.states).tobytes()).hexdigest()
    hr2 = hashlib.sha256(np.ascontiguousarray(r2.states).tobytes()).hexdigest()
    check("V3.5 D2 also on relax path", hr1 != hr2)


def main() -> int:
    print("Emergenz-Kopplung Vorarbeiten (κ>0 verboten)")
    test_freeze()
    test_shuffle()
    test_determinism_kappa0()
    print(f"\n{'=' * 60}")
    print(f"Vorarbeit: {PASS}/{PASS + FAIL} passed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
