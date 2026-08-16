#!/usr/bin/env python3
"""Selbsttest der Emergenz-Messung an synthetischen Faellen mit bekannter
Grundwahrheit. Findet das Werkzeug hier nicht das Richtige, ist jede
Messung am echten Schwarm wertlos.

  Fall 1  identische Agenten            -> TRIVIAL_SYNC
  Fall 2  unabhaengige Oszillatoren     -> NO_COUPLING
  Fall 3  Kuramoto-gekoppelt (K > Kc)   -> COUPLED
  Fall 4  Sterntopologie                -> hub_dominated = True
  Fall 5  Zufallstopologie              -> hub_dominated = False
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from measure import SwarmTrace, assess, graph_structure, summary_line

N, T, DT = 9, 512, 0.05
SEED = 7


def _kuramoto_states(K: float, seed: int = SEED) -> np.ndarray:
    """Simuliert N Kuramoto-Oszillatoren, Zustand = [sin(theta), Arbeit].

    Die zweite Dimension (agentenspezifische Arbeitsrate) sorgt dafuer, dass
    Agenten auch bei perfektem Phasengleichlauf unterscheidbar bleiben — so
    wie in einem echten Schwarm Gas, Reputation oder Queue-Laenge divergieren.
    """
    rng = np.random.default_rng(seed)
    omega = rng.normal(2.0, 0.35, N)
    theta = rng.uniform(0, 2 * np.pi, N)
    work_rate = rng.uniform(0.5, 1.5, N)
    out = np.zeros((T, N, 2))
    work = np.zeros(N)
    for t in range(T):
        diff = theta[None, :] - theta[:, None]
        theta = theta + DT * (omega + (K / N) * np.sin(diff).sum(axis=1))
        work += work_rate * DT
        out[t, :, 0] = np.sin(theta)
        out[t, :, 1] = work
    return out


def case_identical() -> SwarmTrace:
    one = _kuramoto_states(0.0)[:, :1, :]              # ein Agent
    states = np.repeat(one, N, axis=1)                 # N-mal derselbe
    return SwarmTrace([f"A{i}" for i in range(N)], states, _star_messages())


def case_independent() -> SwarmTrace:
    return SwarmTrace([f"A{i}" for i in range(N)], _kuramoto_states(0.0),
                      _random_messages())


def case_coupled() -> SwarmTrace:
    return SwarmTrace([f"A{i}" for i in range(N)], _kuramoto_states(6.0),
                      _random_messages())


def _star_messages(seed: int = SEED):
    rng = np.random.default_rng(seed)
    msgs = []
    for t in range(200):
        a = f"A{rng.integers(1, N)}"
        msgs.append((t, a, "A0"))
        msgs.append((t, "A0", a))
    return msgs


def _random_messages(seed: int = SEED):
    rng = np.random.default_rng(seed)
    msgs = []
    for t in range(400):
        a, b = rng.choice(N, 2, replace=False)
        msgs.append((t, f"A{a}", f"A{b}"))
    return msgs


def main() -> int:
    failures = []

    print("=" * 74)
    print("SELBSTTEST — Emergenz-Messung gegen bekannte Grundwahrheit")
    print("=" * 74)

    checks = [
        ("identische Agenten",       case_identical(),    "TRIVIAL_SYNC"),
        ("unabhaengige Oszillatoren", case_independent(), "NO_COUPLING"),
        ("Kuramoto-gekoppelt K=6",   case_coupled(),      "COUPLED"),
    ]
    for label, trace, expected in checks:
        res = assess(trace, n_surrogates=200, seed=SEED)
        ok = res["verdict"] == expected
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label:<28} {summary_line(res)}")
        if not ok:
            failures.append(f"{label}: erwartet {expected}, bekam {res['verdict']}")

    # Topologie
    print()
    st = SwarmTrace([f"A{i}" for i in range(N)], _kuramoto_states(0.0), _star_messages())
    rd = SwarmTrace([f"A{i}" for i in range(N)], _kuramoto_states(0.0), _random_messages())
    gs = graph_structure(st, 200, SEED)
    gr = graph_structure(rd, 200, SEED)
    for label, g, expect_hub in [("Sterntopologie", gs, True), ("Zufallstopologie", gr, False)]:
        ok = g["hub_dominated"] == expect_hub
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label:<28} hub={g['hub_node']} share={g['hub_share']} "
              f"dominated={g['hub_dominated']} centralization={g['observed']['centralization']}")
        if not ok:
            failures.append(f"{label}: hub_dominated={g['hub_dominated']}, erwartet {expect_hub}")

    print()
    print("=" * 74)
    if failures:
        print(f"❌ SELBSTTEST FEHLGESCHLAGEN — {len(failures)} Abweichungen:")
        for f in failures:
            print(f"   • {f}")
        return 1
    print("✅ SELBSTTEST BESTANDEN — 5/5 Faelle korrekt klassifiziert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
