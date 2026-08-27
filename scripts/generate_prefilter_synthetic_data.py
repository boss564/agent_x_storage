#!/usr/bin/env python3
"""Phase 4A — synthetic feature matrix for queue-priority training.

Purpose (Gate-Map §4.2): features for a *prioritization* signal under backlog.
Every request still gets a full core check — this data is not for skip/abbrev.

Label modes (provenance — see Gate-Map):
  severity_proxy — plugin severity pseudo-label; smoke/features only; not "risk"
  gateway        — TrustedCoreGateway verdict; learns the gate function (circular
                   for AUC-vs-gate claims; banned as Phase-4A success metric)

Writes under data/raas/sandbox/prefilter_synth/ (D2 Red sandbox path).
Never signs envelopes. live_execution=false.

Usage:
  PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py
  PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --n 24 --label-mode severity_proxy
  PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --n 8 --label-mode gateway
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from zlib import crc32

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.mev_latency_redteam.scenario_runner import (  # noqa: E402
    initialize_scenario as mev_init,
    run_attack_scenario as mev_run,
)
from plugins.oracle_anomaly_swarm.scenario_runner import (  # noqa: E402
    initialize_scenario as ora_init,
    run_oracle_attack_scenario as ora_run,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
OUT_DIR = _ROOT / "data" / "raas" / "sandbox" / "prefilter_synth"

MEV_KINDS = ("LATENCY_SPIKE", "SANDWICH_SIM", "JITTER_BURST")
ORA_KINDS = ("STALE_PRICE", "FAT_FINGER", "FLASH_CRASH")

FEATURE_COLS = [
    "sample_id",
    "seed",
    "source_plugin",
    "scenario_kind",
    "latency_ms",
    "slippage_pct",
    "pool_depth_usd",
    "volatility_24h",
    "gas_price_gwei",
    "oracle_deviation_pct",
    "mev_bundle_activity",
    "strategy_complexity_score",
    "severity_score",
    "label_mode",
    "verdict",
    "risk_block_rate",
    "live_execution",
    "scope",
]


def _sev_score(severity: str) -> float:
    return {"LOW": 0.2, "MODERATE": 0.55, "HIGH": 0.9}.get(str(severity).upper(), 0.5)


def _features_from_mev(art: Dict[str, Any], dig: int) -> Dict[str, float]:
    latency = float(art.get("observed_ms") or art.get("p95_ms") or art.get("baseline_ms") or 5.0)
    slip = float(art.get("observed_bps") or 0.0) / 100.0  # bps → pct
    return {
        "latency_ms": round(latency, 4),
        "slippage_pct": round(slip if slip > 0 else 0.05 + (dig % 20) / 100.0, 4),
        "pool_depth_usd": float(500_000 + (dig % 50) * 10_000),
        "volatility_24h": round(0.02 + (dig % 30) / 1000.0, 4),
        "gas_price_gwei": float(15 + (dig % 80)),
        "oracle_deviation_pct": 0.0,
        "mev_bundle_activity": round(0.1 + (dig % 90) / 100.0, 4),
        "strategy_complexity_score": round(0.3 + (dig % 50) / 100.0, 4),
        "severity_score": _sev_score(str(art.get("severity", "MODERATE"))),
    }


def _features_from_oracle(art: Dict[str, Any], dig: int) -> Dict[str, float]:
    if "deviation_pct" in art:
        dev = float(art["deviation_pct"])
    elif "drawdown_pct" in art:
        dev = float(art["drawdown_pct"])
    elif "staleness_s" in art:
        dev = float(art["staleness_s"]) / 10.0  # scale stale seconds → proxy %
    else:
        dev = 1.0 + (dig % 20) / 10.0
    return {
        "latency_ms": float(2 + (dig % 15)),
        "slippage_pct": round(0.1 + min(dev, 50.0) / 200.0, 4),
        "pool_depth_usd": float(400_000 + (dig % 40) * 12_000),
        "volatility_24h": round(0.03 + min(dev, 40.0) / 500.0, 4),
        "gas_price_gwei": float(12 + (dig % 60)),
        "oracle_deviation_pct": round(dev, 4),
        "mev_bundle_activity": round(0.05 + (dig % 40) / 100.0, 4),
        "strategy_complexity_score": round(0.25 + (dig % 45) / 100.0, 4),
        "severity_score": _sev_score(str(art.get("severity", "MODERATE"))),
    }


def _proxy_label(severity_score: float) -> tuple[str, float]:
    """Documented proxy — NOT a core/Z3 decision."""
    if severity_score >= 0.85:
        return "BLOCKED", round(0.55 + 0.4 * severity_score, 4)
    if severity_score >= 0.5:
        return "VORBEHALT", round(0.15 + 0.3 * severity_score, 4)
    return "RELEASED", round(0.02 + 0.1 * severity_score, 4)


def _gateway_label(row: Dict[str, Any], idx: int) -> tuple[str, float]:
    from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal
    from prototypes.raas_hybrid_shell.trusted_gateway import TrustedCoreGateway

    # Map features → untrusted proposal; core decides
    slip = max(0.1, float(row["slippage_pct"]))
    if row["severity_score"] >= 0.85:
        slip = max(slip, 2.5)  # above core ceiling → hard block path
        profile = "aggressive"
    elif row["oracle_deviation_pct"] >= 20:
        profile = "oracle_stress"
    else:
        profile = "default"

    gw = TrustedCoreGateway(tenant_id="prefilter-synth")
    prop = LLMStrategyProposal(
        proposal_id=f"synth-{idx:05d}",
        label=str(row["scenario_kind"]),
        rebalance_interval_h=1.0,
        max_slippage_pct=slip,
        latency_budget_ms=float(row["latency_ms"]),
        profile_hint=profile,
        untrusted=True,
        source="prefilter_synth_batch",
    )
    env = gw.evaluate_shell_proposal(prop, n_scenarios=20)
    return env.gate_verdict, float(env.risk_block_rate)


def generate_rows(
    n: int,
    *,
    seed: int = 20260827,
    label_mode: str = "severity_proxy",
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    kinds_cycle: List[tuple[str, str]] = []
    while len(kinds_cycle) < n:
        for k in MEV_KINDS:
            kinds_cycle.append(("mev", k))
        for k in ORA_KINDS:
            kinds_cycle.append(("oracle", k))
    kinds_cycle = kinds_cycle[:n]

    for i, (plugin, kind) in enumerate(kinds_cycle):
        dig = crc32(f"{seed}|{plugin}|{kind}|{i}".encode()) & 0xFFFFFFFF
        if plugin == "mev":
            st = mev_init(
                kind,
                scenario_id=f"pf-mev-{i}",
                params={"base_latency_ms": 5.0 + (dig % 10)},
                seed=seed + i,
            )
            attack = mev_run(st)
            feats = _features_from_mev(attack["artifact"], dig)
        else:
            st = ora_init(
                kind,
                scenario_id=f"pf-ora-{i}",
                params={"fair_price": 100.0, "feed_id": "SYNTHETIC_ORACLE_A"},
                seed=seed + i,
            )
            attack = ora_run(st)
            feats = _features_from_oracle(attack["artifact"], dig)

        row: Dict[str, Any] = {
            "sample_id": f"{seed}-{i:05d}",
            "seed": seed + i,
            "source_plugin": plugin,
            "scenario_kind": kind,
            **feats,
            "label_mode": label_mode,
            "live_execution": False,
            "scope": SCOPE,
        }

        if label_mode == "gateway":
            verdict, rbr = _gateway_label(row, i)
        else:
            verdict, rbr = _proxy_label(float(row["severity_score"]))
        row["verdict"] = verdict
        row["risk_block_rate"] = rbr
        # Training labels may store verdict; the future prefilter service must
        # never *emit* gate_verdict as a decision field.
        rows.append(row)
    return rows


def write_outputs(rows: List[Dict[str, Any]], out_dir: Path) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "features.jsonl"
    csv_path = out_dir / "features.csv"
    meta_path = out_dir / "manifest.json"

    with jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEATURE_COLS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in FEATURE_COLS})

    material = {
        "n": len(rows),
        "label_modes": sorted({r["label_mode"] for r in rows}),
        "verdicts": {
            v: sum(1 for r in rows if r["verdict"] == v)
            for v in sorted({r["verdict"] for r in rows})
        },
        "scope": SCOPE,
        "live_execution": False,
        "note": (
            "Synthetic rows for queue-priority features (Phase 4A). "
            "severity_proxy ≠ risk. gateway labels are circular vs evaluate_gate — "
            "do not cite AUC-against-gate as success. No core skip."
        ),
    }
    digest = hashlib.sha256(
        json.dumps([r["sample_id"] for r in rows], sort_keys=True).encode()
    ).hexdigest()
    material["sample_id_sha256"] = digest
    meta_path.write_text(json.dumps(material, indent=2), encoding="utf-8")
    return {
        "jsonl": str(jsonl),
        "csv": str(csv_path),
        "manifest": str(meta_path),
        "sample_id_sha256": digest,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Phase 4A synthetic prefilter data")
    p.add_argument("--n", type=int, default=48, help="number of rows")
    p.add_argument("--seed", type=int, default=20260827)
    p.add_argument(
        "--label-mode",
        choices=("severity_proxy", "gateway"),
        default="severity_proxy",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=OUT_DIR,
        help="output directory (default: sandbox prefilter_synth)",
    )
    args = p.parse_args(argv)

    print("Phase 4A synthetic prefilter datagen")
    print("=" * 60)
    print(f"n={args.n} seed={args.seed} label_mode={args.label_mode}")
    rows = generate_rows(args.n, seed=args.seed, label_mode=args.label_mode)
    paths = write_outputs(rows, args.out)
    print(f"jsonl: {paths['jsonl']}")
    print(f"csv:   {paths['csv']}")
    print(f"manifest sample_id_sha256={paths['sample_id_sha256'][:16]}…")
    print("VERDICT: PREFILTER_DATAGEN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
