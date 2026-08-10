#!/usr/bin/env python3
"""Agent X — Finale Veredelung: Durchsatz-Benchmark & Pitch-Demo.

Führt N Zyklen des Transaktions-Splits aus:
  Auftrag → Settlement → BHO-Prüfung → Audit → Metrics.

Einige Zyklen enthalten absichtlich manipulierte Beträge, um die
BHO-Verletzungserkennung zu demonstrieren.

Usage:
  python3 scripts/demo_finale.py                    # 10 Zyklen (schnell)
  python3 scripts/demo_finale.py --cycles 1000       # 1.000 Zyklen (Workload)
  python3 scripts/demo_finale.py --cycles 100 --json  # JSON-Report
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents_b2g.finale import FinaleOrchestrator

SECTORS = ["BAU", "HEALTH", "CUSTOMS", "SUBSIDY", "JUSTICE"]
FIRMS   = [f"firma-{i:02d}.b2g" for i in range(1, 21)]


def run_simulation(cycles: int = 10) -> dict:
    """Führt N Zyklen des wirtschaftlichen Kreislaufs aus."""
    orch = FinaleOrchestrator(user_id="simulation")

    results = []
    t_start = time.perf_counter()
    bho_passed = 0
    z3_verified = 0
    total_volume = 0.0

    sys.stderr.write(f"🔄 Starte {cycles} Wirtschaftszyklen...\n")
    sys.stderr.write(f"   {'Zyklus':<8} {'Sektor':<12} {'Betrag':>12} {'BHO':>6} {'Z3':>20} {'Latenz':>10}\n")
    sys.stderr.write(f"   {'─'*8} {'─'*12} {'─'*12} {'─'*6} {'─'*20} {'─'*10}\n")

    for i in range(cycles):
        sector = SECTORS[i % len(SECTORS)]
        firm = FIRMS[i % len(FIRMS)]
        # Steigende, variierende Beträge mit etwas Streuung
        base = 10_000.0 + (i * 5_000.0)
        amount = base * (1.0 + (hash(f"{i}") % 21 - 10) / 100.0)

        t0 = time.perf_counter()
        tx = {
            "contract_id": f"SIM-{i:04d}",
            "sector": sector,
            "gross_amount": amount,
            "net_amount": amount * 0.80,
            "tax_amount": amount * 0.15,
            "retention_amount": amount * 0.05,
            "contractor": firm,
            "milestone": f"MS_{(i % 5) + 1}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Einige Zyklen absichtlich manipulieren (deterministisch, demonstriert BHO-Erkennung)
        manipulated = i in (17, 42, 73)
        if manipulated:
            tx["net_amount"] = amount * 0.83  # 3 % zu viel abgerechnet

        result = orch.generate_full_audit_package(tx)
        t1 = time.perf_counter()

        cert = result["artifacts"][0]["certificate"]
        if cert["bho_invariant_holds"]:
            bho_passed += 1
        if cert["z3_proof_verified"]:
            z3_verified += 1
        total_volume += amount
        latency_us = (t1 - t0) * 1_000_000

        results.append({
            "cycle": i + 1,
            "sector": sector,
            "amount": round(amount, 2),
            "bho_holds": cert["bho_invariant_holds"],
            "z3_status": cert["z3_proof_status"],
            "z3_verified": cert["z3_proof_verified"],
            "seal": cert["seal"][:16],
            "latency_us": round(latency_us, 1),
        })

        # Fortschritt alle 100 Zyklen
        if (i + 1) % 100 == 0 or i == cycles - 1:
            elapsed = time.perf_counter() - t_start
            tps = (i + 1) / elapsed if elapsed > 0 else 0
            bho_symbol = "⚠️" if manipulated else ("✅" if cert["bho_invariant_holds"] else "❌")
            sys.stderr.write(f"   {i+1:<8} {sector:<12} {amount:>10,.0f} €  "
                  f"{bho_symbol:>6}  "
                  f"{cert['z3_proof_status']:<20} {latency_us:>8.0f} µs  "
                  f"({tps:.0f} TPS)")

    t_total = time.perf_counter() - t_start

    return {
        "simulation": {
            "total_cycles": cycles,
            "duration_s": round(t_total, 2),
            "throughput_tps": round(cycles / t_total, 1) if t_total > 0 else 0,
            "avg_latency_us": round(
                sum(r["latency_us"] for r in results) / len(results), 1
            ) if results else 0,
        },
        "results": {
            "bho_passed": bho_passed,
            "bho_failed": cycles - bho_passed,
            "bho_pass_pct": round(bho_passed / cycles * 100, 2),
            "z3_verified": z3_verified,
            "z3_unverified": cycles - z3_verified,
            "total_volume_eur": round(total_volume, 2),
        },
        "audit": {
            "chain_intact": orch.audit.verify_chain()["artifacts"][0]["verified"],
            "total_entries": orch.audit.get_stats()["total_entries"],
            "first_seal": results[0]["seal"] if results else None,
            "last_seal": results[-1]["seal"] if results else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Agent X Wirtschaftssimulation")
    parser.add_argument("--cycles", type=int, default=10,
                        help="Anzahl Simulationszyklen (default: 10)")
    parser.add_argument("--json", action="store_true",
                        help="Ausgabe als JSON")
    args = parser.parse_args()

    report = run_simulation(args.cycles)
    r = report["results"]
    s = report["simulation"]
    a = report["audit"]

    if args.json:
        # Nur JSON auf stdout, Fortschritt auf stderr
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return

    print()
    print("=" * 72)
    print("🏛️  AGENT X — WIRTSCHAFTSSIMULATION ABGESCHLOSSEN")
    print("=" * 72)
    print(f"  Zyklen gesamt:         {s['total_cycles']}")
    print(f"  Dauer:                 {s['duration_s']:.1f} s")
    print(f"  Durchsatz:             {s['throughput_tps']:.0f} TPS")
    print(f"  Ø Latenz:              {s['avg_latency_us']:.0f} µs")
    print()
    print(f"  BHO Δ=0 bestanden:     {r['bho_passed']}/{s['total_cycles']} ({r['bho_pass_pct']}%)")
    print(f"  BHO verletzt:          {r['bho_failed']}/{s['total_cycles']}")
    print(f"  Z3-Proofs verified:    {r['z3_verified']}/{s['total_cycles']}")
    print(f"  Gesamtvolumen:         {r['total_volume_eur']:,.0f} €")
    print()
    print(f"  Audit-Kette intakt:    {'✅' if a['chain_intact'] else '❌'}")
    print(f"  Audit-Einträge:        {a['total_entries']}")
    print(f"  Erster Seal:           {a['first_seal']}...")
    print(f"  Letzter Seal:          {a['last_seal']}...")
    print(f"  Erstellt:              {report['generated_at'][:19]}")
    print("=" * 72)

    # Exit-Code: 0 wenn alle BHO-Tests bestanden
    sys.exit(0 if r["bho_failed"] == 0 else 1)


if __name__ == "__main__":
    main()
