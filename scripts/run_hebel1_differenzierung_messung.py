"""Hebel 1 Follow-up: Evaluator-Differenzierung measurement runner.

Replays OFFERs through all nine differentiated rules (fan-out) and computes
the pairwise disagreement rate + dead-rule detection, on two datasets:
  (a) natural Provider-OFFERs  -> 'Wirksamkeit auf realen Daten'
  (b) enriched edge cases      -> 'Divergenz-Kapazität der Regeln'

Natural OFFERs are captured programmatically from ProviderAgent (same
distribution as --full cluster), not via NATS. Optional: pass a JSON file
of Cluster-OFFERs instead.

Usage:
  python3 scripts/run_hebel1_differenzierung_messung.py
  python3 scripts/run_hebel1_differenzierung_messung.py natural_offers.json
  python3 scripts/run_hebel1_differenzierung_messung.py --cycles 128
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.hebel1_disagreement_measurement import measure


def map_offer_to_tx(offer: dict) -> dict:
    """Map a Cluster-OFFER (net_amount/tax_amount/...) to rule-API names."""
    return {
        "net": offer.get("net_amount", 0.0),
        "tax": offer.get("tax_amount", 0.0),
        "ret": offer.get("retention_amount", 0.0),
        "gross": offer.get("gross_amount", 0.0),
        "inflated": offer.get("inflated", False),
        "contract_id": offer.get("contract_id", ""),
    }


def load_natural_offers(path: str) -> List[dict]:
    """Load natural Provider-OFFERs from a JSON file and map field names."""
    with open(path) as f:
        offers = json.load(f)
    return [map_offer_to_tx(o) for o in offers]


def capture_natural_offers(cycles: int = 128) -> List[dict]:
    """Run all nine ProviderAgents and collect OFFER contents.

    Same profiles/distribution as demo_producer_cluster --full:
      amount = (45000 + cycle*1000) * amount_multiplier
      clean:  net=0.80*amount, tax=0.15*amount, ret=0.05*amount, delta=0
      inflated (risk_factor cadence): net=0.83*amount → |delta|≈0.03*amount
    """
    from scripts.demo_producer_cluster import PROVIDER_PROFILES, create_agent
    from agents_b2g.protocol import TickController, PayloadType

    agents = [create_agent(p, "provider") for p in PROVIDER_PROFILES]
    tc = TickController(seed=1)
    for a in agents:
        tc.register(a)

    offers: List[dict] = []
    for _ in range(cycles):
        tc.cycle += 1
        env = {"cycle": tc.cycle, "agent_count": len(tc.agents)}
        for agent in tc.agents:
            for msg in agent.tick(env):
                if msg.payload_type == PayloadType.OFFER:
                    offers.append(dict(msg.content))
    return offers


def generate_edge_cases() -> List[dict]:
    """Synthetic Grenzfälle exercising every rule's FAIL path."""
    return [
        {"net": 100.0, "tax": 19.0, "ret": 5.0, "gross": 124.0,
         "inflated": False, "contract_id": "EDGE-000"},
        {"net": 100.0, "tax": 19.0, "ret": 5.0, "gross": 124.005,
         "inflated": False, "contract_id": "EDGE-001"},
        {"net": -10.0, "tax": 19.0, "ret": 5.0, "gross": 14.0,
         "inflated": False, "contract_id": "EDGE-002"},
        {"net": 0.0, "tax": 0.0, "ret": 0.0, "gross": 0.0,
         "inflated": False, "contract_id": "EDGE-003"},
        {"net": 100.0, "tax": 25.0, "ret": 5.0, "gross": 130.0,
         "inflated": False, "contract_id": "EDGE-004"},
        {"net": 100.0, "tax": 40.0, "ret": 5.0, "gross": 145.0,
         "inflated": False, "contract_id": "EDGE-005"},
        {"net": 100.0, "tax": 19.0, "ret": 20.0, "gross": 139.0,
         "inflated": False, "contract_id": "EDGE-006"},
        {"net": 100.0, "tax": 19.0, "ret": 5.0, "gross": 124.0,
         "inflated": False, "contract_id": "AB"},
        {"net": 5e7, "tax": 9.5e6, "ret": 2.5e6, "gross": 6.2e7,
         "inflated": False, "contract_id": "EDGE-008"},
        {"net": 100.0, "tax": 19.0, "ret": 5.0, "gross": 124.0,
         "inflated": True, "contract_id": "EDGE-009"},
    ]


def run(natural_path: Optional[str], out_path: str,
        cycles: int = 128, capture: bool = True) -> dict:
    results = {}

    # (a) Natural dataset
    if natural_path:
        natural_txs = load_natural_offers(natural_path)
        source = f"file:{natural_path}"
    elif capture:
        raw = capture_natural_offers(cycles=cycles)
        # Persist Cluster-field dump for reproducibility
        dump_path = "natural_offers.json"
        with open(dump_path, "w") as f:
            json.dump(raw, f, indent=2)
        natural_txs = [map_offer_to_tx(o) for o in raw]
        source = f"provider_capture cycles={cycles} dump={dump_path}"
    else:
        natural_txs = []
        source = "none"

    if natural_txs:
        nat = measure(natural_txs)
        nat["dataset"] = "natural_provider_offers"
        nat["source"] = source
        nat["n_inflated"] = sum(1 for t in natural_txs if t.get("inflated"))
        results["natural"] = nat

    # (b) Enriched dataset
    enriched_txs = generate_edge_cases()
    enr = measure(enriched_txs)
    enr["dataset"] = "enriched_edge_cases"
    results["enriched"] = enr

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return results


def print_report(results: dict) -> None:
    for key in ("natural", "enriched"):
        if key not in results:
            continue
        r = results[key]
        print(f"\n=== Dataset: {r['dataset']} ===")
        if "source" in r:
            print(f"  Source:                      {r['source']}")
        if "n_inflated" in r:
            print(f"  Inflated OFFERs:             {r['n_inflated']}")
        print(f"  Transactions:                {r['n_transactions']}")
        print(f"  Pairwise disagreement rate:  {r['pairwise_disagreement_rate']:.6f}")
        print(f"  Classification:              {r['classification']}")
        print(f"  Dead rules (always-PASS):    {r['dead_rules_always_pass']}")
        print(f"  Fail counts per rule:")
        for eid, count in r["fail_counts_per_rule"].items():
            marker = "  [DEAD]" if count == 0 else ""
            print(f"    {eid}: {count}{marker}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hebel 1 differentiation measurement")
    parser.add_argument("natural_path", nargs="?", default=None,
                        help="JSON list of Cluster-OFFERs (optional)")
    parser.add_argument("--cycles", type=int, default=128,
                        help="Provider capture cycles when no file given")
    parser.add_argument("--no-capture", action="store_true",
                        help="Skip natural dataset if no file given")
    parser.add_argument("--out", default="hebel1_differenzierung_ergebnis.json")
    args = parser.parse_args()

    results = run(
        natural_path=args.natural_path,
        out_path=args.out,
        cycles=args.cycles,
        capture=not args.no_capture,
    )
    print_report(results)
    print(f"\nErgebnis geschrieben nach: {args.out}")


if __name__ == "__main__":
    main()
