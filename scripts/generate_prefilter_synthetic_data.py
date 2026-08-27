#!/usr/bin/env python3
"""Phase 4A — synthetic feature matrix for queue-priority training.

Purpose (Gate-Map §4.2): features for a *prioritization* signal under backlog.
Every request still gets a full core check — this data is not for skip/abbrev.

Profiles:
  mixed    — mild+moderate cycle (default)
  extremes — controlled OOD: latency jitter, sandwich, flash, depeg, fat-finger

Label modes (provenance — see Gate-Map):
  severity_proxy — plugin severity pseudo-label; smoke/features only; not "risk"
  gateway        — TrustedCoreGateway gate_verdict (circular for AUC-vs-gate;
                   stored as gate_verdict_label — NOT live BHO/Z3 HTTP)

Writes under data/raas/sandbox/prefilter_synth/ (D2 Red sandbox path).
Never signs envelopes. live_execution=false.

Usage:
  PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --profile extremes --n 96
  PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --profile extremes --label-mode gateway --n 24
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
# Structured synth corpus for Phase 4A (gitignored under data/)
OUT_DIR = _ROOT / "data" / "synthetic" / "prefilter"
SANDBOX_OUT = _ROOT / "data" / "raas" / "sandbox" / "prefilter_synth"
DEFAULT_CALIBRATION_DIR = _ROOT / "exports" / "open_data"

MEV_KINDS = ("LATENCY_SPIKE", "SANDWICH_SIM", "JITTER_BURST")
ORA_KINDS = ("STALE_PRICE", "FAT_FINGER", "FLASH_CRASH", "DEPEG_SIM")
EXTREME_CYCLE: Tuple[Tuple[str, str], ...] = (
    ("mev", "LATENCY_SPIKE"),
    ("mev", "JITTER_BURST"),
    ("mev", "SANDWICH_SIM"),
    ("oracle", "FLASH_CRASH"),
    ("oracle", "FAT_FINGER"),
    ("oracle", "DEPEG_SIM"),
    ("oracle", "STALE_PRICE"),
)
STRESS_KINDS = frozenset(
    {"LATENCY_SPIKE", "SANDWICH_SIM", "FLASH_CRASH", "FAT_FINGER", "DEPEG_SIM"}
)

FEATURE_COLS = [
    "sample_id",
    "seed",
    "profile",
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
    "label_provenance",
    "verdict",
    "gate_verdict_label",
    "risk_block_rate",
    "live_execution",
    "scope",
    "calibration_applied",
]


def _sev_score(severity: str) -> float:
    return {"LOW": 0.2, "MODERATE": 0.55, "HIGH": 0.9}.get(str(severity).upper(), 0.5)


def load_calibration_profiles(cal_dir: Path) -> Optional[Dict[str, Any]]:
    """Load §4.3 distribution profiles (not labels). Returns None if missing."""
    if not cal_dir.is_dir():
        return None
    index_path = cal_dir / "calibration_profiles_index.json"
    binance = None
    flashbots = None
    paths: List[str] = []
    if index_path.is_file():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        for p in idx.get("profiles") or []:
            path = Path(p)
            if not path.is_file():
                path = cal_dir / Path(p).name
            if not path.is_file():
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            paths.append(str(path))
            src = str(doc.get("source", ""))
            if "binance" in src:
                binance = doc
            elif "flashbots" in src:
                flashbots = doc
    # Fallback by filename
    if binance is None:
        for cand in sorted(cal_dir.glob("binance_*_klines_profile.json")):
            binance = json.loads(cand.read_text(encoding="utf-8"))
            paths.append(str(cand))
            break
    if flashbots is None:
        fb = cal_dir / "flashbots_latency_profile.json"
        if fb.is_file():
            flashbots = json.loads(fb.read_text(encoding="utf-8"))
            paths.append(str(fb))
    if binance is None and flashbots is None:
        return None
    return {
        "binance": binance,
        "flashbots": flashbots,
        "paths": paths,
        "purpose": "calibration_profile_not_training_labels",
        "label_mode": None,
    }


def _pctile_band(dig: int, *, stress: bool) -> str:
    """Deterministic band from dig — stress biases toward tails."""
    r = dig % 100
    if stress:
        if r < 35:
            return "p90"
        if r < 75:
            return "p99"
        return "max"
    if r < 50:
        return "p50"
    if r < 80:
        return "p90"
    if r < 95:
        return "p99"
    return "max"


def _draw_pctile(stats: Optional[Dict[str, Any]], dig: int, *, stress: bool) -> Optional[float]:
    if not stats or not isinstance(stats, dict):
        return None
    key = _pctile_band(dig, stress=stress)
    val = stats.get(key)
    if val is None or (isinstance(val, float) and val != val):  # NaN
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _rescale_gas_proxy(raw: float, stats: Dict[str, Any]) -> float:
    """Map Flashbots effective gas proxy into synth gwei-like range (~10–150)."""
    lo = float(stats.get("p50") or raw)
    hi = float(stats.get("max") or (raw * 2 if raw else 1.0))
    if hi <= lo:
        return 25.0
    t = (raw - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return round(12.0 + t * (140.0 - 12.0), 4)


def apply_calibration(
    feats: Dict[str, float],
    cal: Dict[str, Any],
    *,
    dig: int,
    scenario_kind: str,
    blend: float = 0.30,
) -> Dict[str, float]:
    """Calibrate gas/MEV from public profiles; leave severity-linked features to plugins.

    Full/slippage replacement broke severity↔feature rank (paired FAIL). Soft-blend
    on those features still hurt. Gas/MEV are weaker label drivers — safe anchors.
    Labels stay severity_proxy — calibration changes inputs only.
    """
    out = dict(feats)
    stress = scenario_kind in STRESS_KINDS
    fb = (cal.get("flashbots") or {}).get("features") or {}
    w = min(1.0, max(0.0, blend))

    def _blend(plugin_val: float, public_val: Optional[float]) -> float:
        if public_val is None:
            return plugin_val
        return (1.0 - w) * plugin_val + w * public_val

    gas_raw = _draw_pctile(fb.get("gas_price_gwei"), dig ^ 0x11, stress=stress)
    if gas_raw is not None and isinstance(fb.get("gas_price_gwei"), dict):
        gas = _rescale_gas_proxy(gas_raw, fb["gas_price_gwei"])
        out["gas_price_gwei"] = round(_blend(float(out["gas_price_gwei"]), gas), 4)

    mev_act = _draw_pctile(fb.get("mev_bundle_activity"), dig ^ 0x55, stress=stress)
    if mev_act is not None:
        act = max(0.0, min(1.0, mev_act / 100.0))
        out["mev_bundle_activity"] = round(_blend(float(out["mev_bundle_activity"]), act), 4)

    # Binance slip/vol/oracle: recorded in manifest for future experiments;
    # not applied to features here (preserves severity rank).
    # latency_ms: no public timing — keep plugin
    return out


def _extreme_mev_params(kind: str, dig: int) -> Dict[str, Any]:
    if kind == "LATENCY_SPIKE":
        return {"base_latency_ms": 50.0 + (dig % 200)}  # 50–249 ms baseline → large spike
    if kind == "SANDWICH_SIM":
        return {"base_latency_ms": 20.0}
    return {"base_latency_ms": 30.0 + (dig % 40)}


def _extreme_ora_params(kind: str, dig: int) -> Dict[str, Any]:
    base = {"fair_price": 100.0, "feed_id": "SYNTHETIC_ORACLE_EXTREME"}
    if kind == "DEPEG_SIM":
        base["peg_price"] = 1.0
        base["break_pct"] = 15 + (dig % 40)  # 15–54% break
        base["fair_price"] = 1.0
    elif kind == "FLASH_CRASH":
        base["fair_price"] = 100.0
    elif kind == "STALE_PRICE":
        base["fair_price"] = 100.0
    return base


def _features_from_mev(art: Dict[str, Any], dig: int) -> Dict[str, float]:
    latency = float(art.get("observed_ms") or art.get("p95_ms") or art.get("baseline_ms") or 5.0)
    slip = float(art.get("observed_bps") or 0.0) / 100.0
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
        dev = float(art["staleness_s"]) / 10.0
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
    """TrustedCoreGateway stress gate — circular vs evaluate_gate; not live BHO Z3."""
    from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal
    from prototypes.raas_hybrid_shell.trusted_gateway import TrustedCoreGateway

    slip = max(0.1, float(row["slippage_pct"]))
    if row["severity_score"] >= 0.85 or row["profile"] == "extremes":
        slip = max(slip, 2.5)
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
        latency_budget_ms=min(float(row["latency_ms"]), 500.0),
        profile_hint=profile,
        untrusted=True,
        source="prefilter_synth_batch",
    )
    env = gw.evaluate_shell_proposal(prop, n_scenarios=20)
    return env.gate_verdict, float(env.risk_block_rate)


def _kind_cycle(n: int, profile: str) -> List[Tuple[str, str]]:
    if profile == "extremes":
        base = list(EXTREME_CYCLE)
    else:
        base = [("mev", k) for k in MEV_KINDS] + [("oracle", k) for k in ORA_KINDS]
    out: List[Tuple[str, str]] = []
    while len(out) < n:
        out.extend(base)
    return out[:n]


def generate_rows(
    n: int,
    *,
    seed: int = 20260827,
    label_mode: str = "severity_proxy",
    profile: str = "mixed",
    calibration: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if profile not in ("mixed", "extremes"):
        raise ValueError(f"unknown profile: {profile}")
    rows: List[Dict[str, Any]] = []
    provenance = (
        "TrustedCoreGateway.evaluate_shell_proposal→gate_verdict "
        "(circular vs evaluate_gate; not live infra-z3 BHO)"
        if label_mode == "gateway"
        else "plugin_severity_proxy (not risk / not gate)"
    )

    for i, (plugin, kind) in enumerate(_kind_cycle(n, profile)):
        dig = crc32(f"{seed}|{profile}|{plugin}|{kind}|{i}".encode()) & 0xFFFFFFFF
        if plugin == "mev":
            params = (
                _extreme_mev_params(kind, dig)
                if profile == "extremes"
                else {"base_latency_ms": 5.0 + (dig % 10)}
            )
            st = mev_init(kind, scenario_id=f"pf-mev-{i}", params=params, seed=seed + i)
            attack = mev_run(st)
            feats = _features_from_mev(attack["artifact"], dig)
        else:
            params = (
                _extreme_ora_params(kind, dig)
                if profile == "extremes"
                else {"fair_price": 100.0, "feed_id": "SYNTHETIC_ORACLE_A"}
            )
            st = ora_init(kind, scenario_id=f"pf-ora-{i}", params=params, seed=seed + i)
            attack = ora_run(st)
            feats = _features_from_oracle(attack["artifact"], dig)

        cal_applied = False
        if calibration is not None:
            feats = apply_calibration(feats, calibration, dig=dig, scenario_kind=kind)
            cal_applied = True

        row: Dict[str, Any] = {
            "sample_id": f"{seed}-{profile}-{i:05d}",
            "seed": seed + i,
            "profile": profile,
            "source_plugin": plugin,
            "scenario_kind": kind,
            "scenario_inputs": dict(params),
            "scenario_artifact": attack.get("artifact"),
            **feats,
            "label_mode": label_mode,
            "label_provenance": provenance,
            "live_execution": False,
            "scope": SCOPE,
            "calibration_applied": cal_applied,
        }

        if label_mode == "gateway":
            verdict, rbr = _gateway_label(row, i)
            row["gate_verdict_label"] = verdict
        else:
            verdict, rbr = _proxy_label(float(row["severity_score"]))
            row["gate_verdict_label"] = ""
        row["verdict"] = verdict
        row["risk_block_rate"] = rbr
        rows.append(row)
    return rows


def write_outputs(
    rows: List[Dict[str, Any]],
    out_dir: Path,
    *,
    calibration_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "features.jsonl"
    csv_path = out_dir / "features.csv"
    meta_path = out_dir / "manifest.json"

    with jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEATURE_COLS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in FEATURE_COLS})

    material = {
        "n": len(rows),
        "profiles": sorted({r["profile"] for r in rows}),
        "label_modes": sorted({r["label_mode"] for r in rows}),
        "scenario_kinds": sorted({r["scenario_kind"] for r in rows}),
        "verdicts": {
            v: sum(1 for r in rows if r["verdict"] == v)
            for v in sorted({r["verdict"] for r in rows})
        },
        "scope": SCOPE,
        "live_execution": False,
        "purpose": "queue_prioritization_under_backlog",
        "purpose_statement": (
            "Model approximates the gate verdict for sorting; "
            "it does not predict market risk."
        ),
        "training_allowed": all(r.get("label_mode") == "severity_proxy" for r in rows),
        "calibration_applied": any(r.get("calibration_applied") for r in rows),
        "calibration": calibration_meta,
        "note": (
            "Synthetic rows for queue-priority features (Phase 4A / §4.3). "
            "Train only on severity_proxy batches (training_allowed=true). "
            "Public profiles calibrate feature distributions only — not labels. "
            "gateway→gate_verdict_label is circular vs evaluate_gate — "
            "ban AUC-against-gate as success. No core skip. "
            "Not live infra-z3 BHO."
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
        "--profile",
        choices=("mixed", "extremes"),
        default="mixed",
        help="mixed=balanced cycle; extremes=OOD stress params",
    )
    p.add_argument(
        "--label-mode",
        choices=("severity_proxy", "gateway"),
        default="severity_proxy",
    )
    p.add_argument(
        "--calibration-dir",
        type=Path,
        default=None,
        help="§4.3 profile dir (default: exports/open_data if present)",
    )
    p.add_argument(
        "--no-calibration",
        action="store_true",
        help="disable public-profile feature calibration",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: sandbox prefilter_synth[/extremes])",
    )
    args = p.parse_args(argv)
    out = args.out or (OUT_DIR / args.profile)

    cal = None
    cal_meta = None
    if not args.no_calibration:
        cal_dir = args.calibration_dir or DEFAULT_CALIBRATION_DIR
        cal = load_calibration_profiles(cal_dir)
        if cal is not None:
            cal_meta = {
                "dir": str(cal_dir),
                "paths": cal.get("paths"),
                "purpose": cal.get("purpose"),
                "label_mode": None,
            }

    print("Phase 4A synthetic prefilter datagen")
    print("=" * 60)
    print(
        f"n={args.n} seed={args.seed} profile={args.profile} "
        f"label_mode={args.label_mode} calibration={'on' if cal else 'off'}"
    )
    rows = generate_rows(
        args.n,
        seed=args.seed,
        label_mode=args.label_mode,
        profile=args.profile,
        calibration=cal,
    )
    paths = write_outputs(rows, out, calibration_meta=cal_meta)
    print(f"jsonl: {paths['jsonl']}")
    print(f"csv:   {paths['csv']}")
    print(f"kinds: {sorted({r['scenario_kind'] for r in rows})}")
    print(f"manifest sample_id_sha256={paths['sample_id_sha256'][:16]}…")
    print("VERDICT: PREFILTER_DATAGEN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
