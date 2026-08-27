#!/usr/bin/env python3
"""RaaS P1 — counterfactual barrier FP/FN surface (calibration plan).

Varies exec_block × cascade_block as *labels only*. Does not change
production gate_core thresholds. Parent definition_hash is ground truth.

Usage:
  PYTHONPATH=. python3 scripts/raas_barrier_cal_surface.py --days 180
  make raas-barrier-cal-surface

Verdict RAAS_BARRIER_CAL_SURFACE_PASS = screen completed (not threshold endorsement).
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.envelope_score import (  # noqa: E402
    score_envelope_hits,
)
from scripts.ingest_public_distributions import fetch_binance_klines  # noqa: E402
from scripts.raas_flash_crash_retrospective import (  # noqa: E402
    BAR_DROP_OBS_PCT,
    CASCADE_RISK_SCALE_PCT,
    EXEC_RISK_SCALE_PCT,
    ROLL_DD_OBS_PCT,
    definition_hash,
    extract_features,
)
from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    EnforcerContext,
    WormAnchorStore,
)
from services.fail_closed_gate.gate_core import CASCADE_BLOCK, EXEC_RISK_BLOCK  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
MAP_REF = "docs/RaaS_Z3_BARRIER_CALIBRATION_v0.md"
PARENT_MAP = "docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md"
BASELINE_TAG = "v1.0-raas-baseline"
EXPECTED_DEF_HASH = (
    "bbae3cb16d893e6380665843415c430aedf9946a084010e94b88dca7a0ccb01b"
)

# Frozen parent trip edges (algebraic) — ground truth, not grid
FROZEN_EXEC_TRIP_DROP = round(EXEC_RISK_BLOCK * EXEC_RISK_SCALE_PCT, 6)
FROZEN_CASCADE_TRIP_DD = round(CASCADE_BLOCK * CASCADE_RISK_SCALE_PCT, 6)

# Plan §4.1 grid (frozen before first look)
EXEC_BLOCK_GRID = (0.70, 0.75, 0.80, 0.85)
CASCADE_BLOCK_GRID = (0.65, 0.70, 0.75, 0.80)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "services" / "fail_closed_gate").is_dir():
        return cwd
    return _ROOT


def load_rows(symbol: str, days: int) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    symbols_try = [symbol.upper()]
    if symbols_try[0] != "ETHUSDT":
        symbols_try.append("ETHUSDT")
    for sym in symbols_try:
        rows, fetch_log = fetch_binance_klines(sym, "1m", days)
        if rows:
            return sym, rows, fetch_log
    raise RuntimeError(f"No klines for {symbols_try} days={days}")


def ground_labels(feat: Any) -> Tuple[bool, bool, bool]:
    """observed, ground_trip (frozen), ground_warn."""
    observed = bool(feat.observed_break)
    ground_trip = (feat.bar_drop_pct >= FROZEN_EXEC_TRIP_DROP) or (
        feat.roll_dd_60_pct >= FROZEN_CASCADE_TRIP_DD
    )
    ground_warn = observed and not ground_trip
    return observed, ground_trip, ground_warn


def pred_trip(feat: Any, exec_block: float, cascade_block: float) -> bool:
    """Counterfactual risk-layer trip (P3/P8/Z3-score path only)."""
    return (feat.exec_risk >= exec_block) or (feat.cascade_risk >= cascade_block)


def score_pair(
    preds: Sequence[bool],
    grounds: Sequence[bool],
    *,
    prefix: str,
) -> Dict[str, Any]:
    predictions = [
        {"condition_id": f"{prefix}:{i}", "break": bool(p)} for i, p in enumerate(preds)
    ]
    observations = [
        {"condition_id": f"{prefix}:{i}", "break": bool(g)} for i, g in enumerate(grounds)
    ]
    return score_envelope_hits(predictions, observations).to_dict()


def evaluate_grid(features: Sequence[Any]) -> List[Dict[str, Any]]:
    grounds_trip = []
    grounds_warn = []
    for f in features:
        _, gt, gw = ground_labels(f)
        grounds_trip.append(gt)
        grounds_warn.append(gw)

    rows_out: List[Dict[str, Any]] = []
    for exec_b, casc_b in itertools.product(EXEC_BLOCK_GRID, CASCADE_BLOCK_GRID):
        preds_t = [pred_trip(f, exec_b, casc_b) for f in features]
        # Warn label: observed band feature AND not candidate-trip
        # (design: WARNUNG = Observed erreicht, Trip nicht)
        preds_w = [
            bool(f.observed_break) and not pt for f, pt in zip(features, preds_t)
        ]
        trip_stats = score_pair(preds_t, grounds_trip, prefix="trip")
        warn_stats = score_pair(preds_w, grounds_warn, prefix="warn")
        is_prod = (
            abs(exec_b - EXEC_RISK_BLOCK) < 1e-9
            and abs(casc_b - CASCADE_BLOCK) < 1e-9
        )
        rows_out.append(
            {
                "exec_block": exec_b,
                "cascade_block": casc_b,
                "is_production_point": is_prod,
                "n_pred_trip": sum(preds_t),
                "n_pred_warn": sum(preds_w),
                "trip": {
                    "precision": trip_stats["precision"],
                    "recall": trip_stats["recall"],
                    "tp": trip_stats["true_positives"],
                    "fp": trip_stats["false_positives"],
                    "fn": trip_stats["false_negatives"],
                },
                "warn": {
                    "precision": warn_stats["precision"],
                    "recall": warn_stats["recall"],
                    "tp": warn_stats["true_positives"],
                    "fp": warn_stats["false_positives"],
                    "fn": warn_stats["false_negatives"],
                },
                "note": (
                    "counterfactual_label_only"
                    if not is_prod
                    else "matches_frozen_prod_blocks"
                ),
            }
        )
    return rows_out


def run_surface(*, symbol: str = "ETHUSDC", days: int = 180) -> Dict[str, Any]:
    def_hash = definition_hash()
    if def_hash != EXPECTED_DEF_HASH:
        raise RuntimeError(
            f"definition_hash drift: {def_hash} != {EXPECTED_DEF_HASH}"
        )

    used_symbol, rows, fetch_log = load_rows(symbol, days)
    features = extract_features(rows, symbol=used_symbol)

    n_obs = sum(1 for f in features if f.observed_break)
    n_ground_trip = 0
    n_ground_warn = 0
    for f in features:
        _, gt, gw = ground_labels(f)
        n_ground_trip += int(gt)
        n_ground_warn += int(gw)

    surface = evaluate_grid(features)
    prod_row = next(r for r in surface if r["is_production_point"])

    result: Dict[str, Any] = {
        "schema": "raas_barrier_cal_surface_v0",
        "phase": "P1",
        "map": MAP_REF,
        "parent_map": PARENT_MAP,
        "baseline_tag": BASELINE_TAG,
        "scope": SCOPE,
        "live_execution": False,
        "not_investment_advice": True,
        "order_send_count": 0,
        "definition_hash": def_hash,
        "definition_hash_match": True,
        "prod_edges_frozen": True,
        "prod_exec_block": EXEC_RISK_BLOCK,
        "prod_cascade_block": CASCADE_BLOCK,
        "frozen_trip_drop_pct": FROZEN_EXEC_TRIP_DROP,
        "frozen_trip_dd_pct": FROZEN_CASCADE_TRIP_DD,
        "observed_drop_pct": BAR_DROP_OBS_PCT,
        "observed_dd_pct": ROLL_DD_OBS_PCT,
        "grid": {
            "exec_block": list(EXEC_BLOCK_GRID),
            "cascade_block": list(CASCADE_BLOCK_GRID),
        },
        "symbol": used_symbol,
        "days_requested": days,
        "n_bars": len(rows),
        "n_observed": n_obs,
        "n_ground_trip": n_ground_trip,
        "n_ground_warn": n_ground_warn,
        "surface": surface,
        "production_point": prod_row,
        "fetch_log_tail": fetch_log[-15:],
        "generated_at": _now(),
        "verdict_note": (
            "RAAS_BARRIER_CAL_SURFACE_PASS means the screen completed. "
            "It does not endorse any grid point as a new production threshold."
        ),
    }

    root = _repo_root()
    enforcer = DSuiteEnforcer(
        worm=WormAnchorStore(root / "logs" / "worm" / "barrier_cal_d_suite_anchors.jsonl")
    )
    stamped = enforcer.enforce_all(
        EnforcerContext(
            caller_role="UNTRUSTED_SHELL",
            target_path="/api/v1/raas/evaluate",
            payload={
                "phase": "barrier_cal_surface_p1",
                "definition_hash": def_hash,
                "n_grid": len(surface),
            },
        )
    )
    result["_worm_anchor_sha256"] = stamped.get("_worm_anchor_sha256")
    result["_d_suite_checked"] = True

    worm_dir = root / "logs" / "worm"
    worm_dir.mkdir(parents=True, exist_ok=True)
    worm_path = worm_dir / "barrier_cal_surface.jsonl"
    with worm_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": _now(),
                    "phase": "barrier_cal_surface_p1",
                    "definition_hash": def_hash,
                    "n_bars": len(rows),
                    "n_grid": len(surface),
                    "live_execution": False,
                    "not_investment_advice": True,
                    "order_send_count": 0,
                    "scope": SCOPE,
                    "_worm_anchor_sha256": result["_worm_anchor_sha256"],
                },
                sort_keys=True,
            )
            + "\n"
        )
    result["worm_path"] = str(worm_path)

    report_dir = root / "exports" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "barrier_cal_surface_latest.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    md_path = report_dir / "barrier_cal_surface_latest.md"
    md_path.write_text(_to_markdown(result), encoding="utf-8")
    result["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def _to_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Barrier Calibration Surface (P1)",
        "",
        f"**Generated:** {result['generated_at']}",
        f"**Map:** `{result['map']}`",
        f"**definition_hash:** `{result['definition_hash']}` (match={result['definition_hash_match']})",
        f"**Prod edges frozen:** exec={result['prod_exec_block']} cascade={result['prod_cascade_block']}",
        f"**Scope:** `{result['scope']}` · `live_execution=false`",
        "",
        "> `RAAS_BARRIER_CAL_SURFACE_PASS` = screen completed. "
        "**Not** a claim that any grid point should become production.",
        "",
        "## Cohort",
        "",
        f"- Symbol `{result['symbol']}` · days={result['days_requested']} · bars={result['n_bars']}",
        f"- Observed={result['n_observed']} · ground_trip={result['n_ground_trip']} · "
        f"ground_warn={result['n_ground_warn']}",
        f"- Frozen trip edges: drop≥{result['frozen_trip_drop_pct']}% / "
        f"dd≥{result['frozen_trip_dd_pct']}%",
        "",
        "## Production point (frozen blocks) — consistency check only",
        "",
        "> At `(prod_exec, prod_cascade)`, ground trip edges are "
        "`block × scale` — the same inequality as `pred_trip`. "
        "P/R=1.0 is **algebraically expected**. Deviation = wiring bug, "
        "not detection quality. Empirical signal = the other 15 grid points. "
        f"`ground_trip={result['n_ground_trip']}` is too small for precision claims.",
        "",
    ]
    pp = result["production_point"]
    lines.extend(
        [
            f"- exec={pp['exec_block']} cascade={pp['cascade_block']}",
            f"- Trip: P={pp['trip']['precision']} R={pp['trip']['recall']} "
            f"TP={pp['trip']['tp']} FP={pp['trip']['fp']} FN={pp['trip']['fn']}",
            f"- Warn: P={pp['warn']['precision']} R={pp['warn']['recall']} "
            f"TP={pp['warn']['tp']} FP={pp['warn']['fp']} FN={pp['warn']['fn']}",
            "",
            "## Full surface (Trip / Warn)",
            "",
            "| exec | casc | prod? | Trip P | Trip R | Trip FP | Trip FN | Warn P | Warn R | Warn FP | Warn FN |",
            "|------|------|-------|--------|--------|---------|---------|--------|--------|---------|---------|",
        ]
    )
    for r in result["surface"]:
        t, w = r["trip"], r["warn"]
        lines.append(
            f"| {r['exec_block']:.2f} | {r['cascade_block']:.2f} | "
            f"{'Y' if r['is_production_point'] else ''} | "
            f"{t['precision']:.3f} | {t['recall']:.3f} | {t['fp']} | {t['fn']} | "
            f"{w['precision']:.3f} | {w['recall']:.3f} | {w['fp']} | {w['fn']} |"
        )
    lines.extend(
        [
            "",
            "## Compliance",
            "",
            "```text",
            "live_execution = false",
            "order_send_count = 0",
            "prod_trip_edges = frozen",
            "status = RAAS_BARRIER_CAL_SURFACE_PASS",
            "pass_means = screen_completed_not_threshold_endorsement",
            "```",
            "",
            "*Counterfactual labels only — P3 adoption requires separate amendment + new hash.*",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="RaaS P1 barrier calibration surface")
    p.add_argument("--symbol", default="ETHUSDC")
    p.add_argument("--days", type=int, default=180)
    args = p.parse_args(argv)

    print("RaaS Barrier Cal Surface (P1)")
    print("=" * 60)
    print(f"map={MAP_REF}")
    print(f"definition_hash={definition_hash()}")
    print(f"grid exec={EXEC_BLOCK_GRID} cascade={CASCADE_BLOCK_GRID}")
    print("PASS = run completed — not threshold endorsement")

    try:
        result = run_surface(symbol=args.symbol, days=args.days)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}")
        return 1

    pp = result["production_point"]
    print(
        f"bars={result['n_bars']} observed={result['n_observed']} "
        f"ground_trip={result['n_ground_trip']} ground_warn={result['n_ground_warn']}"
    )
    print(
        f"prod point trip P={pp['trip']['precision']:.3f} R={pp['trip']['recall']:.3f} "
        f"FP={pp['trip']['fp']} FN={pp['trip']['fn']}"
    )
    print(
        f"prod point warn P={pp['warn']['precision']:.3f} R={pp['warn']['recall']:.3f} "
        f"FP={pp['warn']['fp']} FN={pp['warn']['fn']}"
    )
    print(f"grid points={len(result['surface'])}")
    print(f"report: {result['paths']['markdown']}")
    print("=" * 60)
    print("VERDICT: RAAS_BARRIER_CAL_SURFACE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
