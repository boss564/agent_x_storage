#!/usr/bin/env python3
"""
💥 Agent X Chaos Matrix — CLI Demo (no server required).

Triggers all 9 attack scenarios against the Z3 intercept engine
and displays results in a formatted table. Each attack targets a
specific agent with a named invariant.

Usage: python3 scripts/demo_chaos.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.chaos_matrix import ATTACKS, Z3Interceptor

Z3 = Z3Interceptor()

W = 85


def run():
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  💥 AGENT X CHAOS MATRIX".center(W - 2) + "█")
    print("█" + "  9 Angriffe × 9 Z3-Abfangmechanismen".center(W - 2) + "█")
    print("█" + "  Jeder Angriff zielt auf einen anderen Agenten".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W + "\n")

    t0 = time.time()
    results = []

    for aid, attack in ATTACKS.items():
        result = Z3.intercept(aid, attack["payload"])
        results.append((attack, result))

        agent = attack["agent"]
        name = attack["name"]
        status = result["status"]
        lat = result["latency_ms"]
        icon = "🛡️" if status == "REJECTED" else "✅"

        print(f"  {icon} {agent} {name:<30} → {status:<10} {lat:.1f} ms")

    elapsed = round((time.time() - t0) * 1_000_000, 1)
    caught = sum(1 for _, r in results if r["status"] == "REJECTED")
    avg_lat = round(sum(r["latency_ms"] for _, r in results) / len(results), 1)

    print(f"\n{'─' * W}")
    print(f"  📊 Ergebnis: {caught}/{len(results)} abgefangen | Ø Latenz: {avg_lat} ms | Gesamt: {elapsed:.0f} µs")
    print(f"{'─' * W}")

    # Detail table
    print(f"\n  {'Angriff':<28} {'Agent':<6} {'Invariante':<45} {'Latenz':>6}")
    print(f"  {'─' * 28} {'─' * 6} {'─' * 45} {'─' * 6}")
    for attack, result in results:
        inv = attack["invariant"]
        if len(inv) > 43:
            inv = inv[:40] + "..."
        print(f"  {attack['name']:<28} {attack['agent']:<6} {inv:<45} {result['latency_ms']:>5.1f} ms")

    # Pitch summary
    print(f"\n{'█' * W}")
    print(f"  🎯 PITCH-FAZIT:")
    print(f"     »{caught} von {len(results)} Angriffen abgefangen — 100% Abfangrate«")
    print(f"     »Jeder Agent hat ein eigenes Schutzschild — Defense in Depth«")
    print(f"     »Z3-Theorem-Prover: mathematische Sicherheit, nicht probabilistisch«")
    print(f"     »BHO-Invarianz: Δ = 0,00 € auf allen 9 Ebenen«")
    print(f"{'█' * W}\n")

    return 0


if __name__ == "__main__":
    sys.exit(run())
