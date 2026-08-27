#!/usr/bin/env python3
"""RaaS FN-belt screen — classify false negatives (hypotheses A–D).

Reuses flash-crash retrospective definitions (same definition_hash).
Does not retune gate thresholds.

Usage:
  PYTHONPATH=. python3 scripts/raas_fn_belt_screen.py --days 180
  make raas-fn-belt-screen
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.ingest_public_distributions import fetch_binance_klines  # noqa: E402
from scripts.raas_flash_crash_retrospective import (  # noqa: E402
    BAR_DROP_OBS_PCT,
    CASCADE_RISK_SCALE_PCT,
    EXEC_RISK_SCALE_PCT,
    ROLL_DD_OBS_PCT,
    definition_hash,
    extract_features,
    predict_breaks,
)
from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    EnforcerContext,
)
from services.fail_closed_gate.gate_core import CASCADE_BLOCK, EXEC_RISK_BLOCK  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
MAP_REF = "docs/RaaS_FN_BELT_SCREEN_v0.md"
PARENT_MAP = "docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md"
BASELINE_TAG = "v1.0-raas-baseline"
EXPECTED_DEF_HASH = (
    "bbae3cb16d893e6380665843415c430aedf9946a084010e94b88dca7a0ccb01b"
)

# Algebraic trip edges from parent MAP (not new tuning)
EXEC_TRIP_DROP_PCT = round(EXEC_RISK_BLOCK * EXEC_RISK_SCALE_PCT, 6)  # 2.4
CASCADE_TRIP_DD_PCT = round(CASCADE_BLOCK * CASCADE_RISK_SCALE_PCT, 6)  # 6.0

# D-proxy: intra-bar range clearly dominates close-to-close drop
D_HL_VS_DROP_RATIO = 2.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "services" / "fail_closed_gate").is_dir():
        return cwd
    return _ROOT


def _mean_std(xs: Sequence[float]) -> Tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(max(var, 0.0))


def _z(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.0
    return (x - mean) / std


def load_rows(symbol: str, days: int) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    symbols_try = [symbol.upper()]
    if symbols_try[0] != "ETHUSDT":
        symbols_try.append("ETHUSDT")
    fetch_log: List[str] = []
    for sym in symbols_try:
        rows, fetch_log = fetch_binance_klines(sym, "1m", days)
        if rows:
            return sym, rows, fetch_log
    raise RuntimeError(f"No klines for {symbols_try} days={days}")


def attach_proxies(
    rows: Sequence[Dict[str, Any]],
    features: Sequence[Any],
) -> List[Dict[str, Any]]:
    vols = [float(r.get("volume") or 0.0) for r in rows]
    v_mean, v_std = _mean_std(vols)
    out: List[Dict[str, Any]] = []
    for i, feat in enumerate(features):
        r = rows[i]
        close = float(r["close"]) or 1.0
        hl = 100.0 * (float(r["high"]) - float(r["low"])) / close
        vol_z = _z(vols[i], v_mean, v_std)
        out.append(
            {
                "condition_id": feat.condition_id,
                "open_time": feat.open_time,
                "bar_drop_pct": feat.bar_drop_pct,
                "roll_dd_60_pct": feat.roll_dd_60_pct,
                "exec_risk": feat.exec_risk,
                "cascade_risk": feat.cascade_risk,
                "observed_break": feat.observed_break,
                "hl_range_pct": round(hl, 6),
                "volume": vols[i],
                "volume_z": round(vol_z, 6),
            }
        )
    return out


def classify_fn(row: Dict[str, Any]) -> str:
    """A-band vs above-trip (parent MAP edges)."""
    drop = float(row["bar_drop_pct"])
    dd = float(row["roll_dd_60_pct"])
    above = (drop >= EXEC_TRIP_DROP_PCT) or (dd >= CASCADE_TRIP_DD_PCT)
    if above:
        return "ABOVE_TRIP_BUT_FN"
    return "STRUCTURAL_GAP_A"


def run_screen(*, symbol: str = "ETHUSDC", days: int = 180) -> Dict[str, Any]:
    def_hash = definition_hash()
    if def_hash != EXPECTED_DEF_HASH:
        raise RuntimeError(
            f"definition_hash drift: got {def_hash}, expected {EXPECTED_DEF_HASH}. "
            "FN screen must match parent retrospective MAP."
        )

    used_symbol, rows, fetch_log = load_rows(symbol, days)
    features = extract_features(rows, symbol=used_symbol)
    predictions, reason_counts = predict_breaks(features)
    pred_map = {p["condition_id"]: p for p in predictions}
    enriched = attach_proxies(rows, features)

    fns: List[Dict[str, Any]] = []
    tps: List[Dict[str, Any]] = []
    for row in enriched:
        pred = pred_map[row["condition_id"]]
        predicted = bool(pred["break"])
        observed = bool(row["observed_break"])
        item = {
            **row,
            "predicted_break": predicted,
            "gate_reasons": pred.get("reasons", []),
            "decision": pred.get("decision"),
        }
        if observed and not predicted:
            item["fn_class"] = classify_fn(row)
            item["d_proxy_intrabar"] = (
                float(row["hl_range_pct"])
                >= D_HL_VS_DROP_RATIO * max(float(row["bar_drop_pct"]), 1e-9)
            )
            fns.append(item)
        elif observed and predicted:
            tps.append(item)

    n_fn = len(fns)
    n_struct = sum(1 for f in fns if f["fn_class"] == "STRUCTURAL_GAP_A")
    n_above = sum(1 for f in fns if f["fn_class"] == "ABOVE_TRIP_BUT_FN")
    n_d_proxy = sum(1 for f in fns if f.get("d_proxy_intrabar"))

    def _avg(key: str, xs: Sequence[Dict[str, Any]]) -> Optional[float]:
        if not xs:
            return None
        return round(sum(float(x[key]) for x in xs) / len(xs), 6)

    # --- Hypothesis verdicts (frozen rules) ---
    if n_fn == 0:
        verdict_a = "DATA_INSUFFICIENT"
    elif n_above == 0 and n_struct == n_fn:
        verdict_a = "SUPPORTED"
    elif n_above > 0 and n_struct / n_fn < 0.5:
        verdict_a = "REJECTED"
    elif n_struct / n_fn >= 0.5:
        verdict_a = "SUPPORTED"  # majority structural gap
    else:
        verdict_a = "PARTIAL"

    # B: with only kline proxies — if structural gap explains all, B not needed for FN;
    # if above-trip FNs exist and proxies differ, PARTIAL signal toward B.
    if n_above == 0:
        verdict_b = "PARTIAL"  # no order book; gap explained by A → B not required for FN
        b_note = (
            "No ABOVE_TRIP_BUT_FN; structural A-gap explains FNs with current features. "
            "Order-book depth not in dataset — full B test DATA_INSUFFICIENT."
        )
    else:
        verdict_b = "PARTIAL"
        b_note = (
            "Above-trip FNs exist — investigate missing features; "
            "order book still absent (DATA_INSUFFICIENT for full B)."
        )

    verdict_c = "NOT_SEPARABLE"
    c_note = (
        "Parent MAP cascade_risk is univariate (dd/scale). "
        "Reweighting ≡ changing CASCADE_RISK_SCALE / block — not independent of A."
    )

    if n_fn == 0:
        verdict_d = "DATA_INSUFFICIENT"
    elif n_d_proxy / n_fn >= 0.5:
        verdict_d = "PARTIAL"
    else:
        verdict_d = "REJECTED"
    d_note = (
        f"Intra-bar HL≫drop proxy on {n_d_proxy}/{n_fn} FNs "
        f"(ratio≥{D_HL_VS_DROP_RATIO}). Sub-1m data not fetched — full D needs 1s klines."
    )

    hypotheses = {
        "A_trip_thresholds_above_observed": {
            "verdict": verdict_a,
            "fn_structural_gap": n_struct,
            "fn_above_trip": n_above,
            "fn_structural_gap_share": round(n_struct / n_fn, 6) if n_fn else None,
            "exec_trip_drop_pct": EXEC_TRIP_DROP_PCT,
            "cascade_trip_dd_pct": CASCADE_TRIP_DD_PCT,
            "observed_drop_pct": BAR_DROP_OBS_PCT,
            "observed_dd_pct": ROLL_DD_OBS_PCT,
        },
        "B_feature_extraction_incomplete": {
            "verdict": verdict_b,
            "note": b_note,
            "fn_avg_volume_z": _avg("volume_z", fns),
            "tp_avg_volume_z": _avg("volume_z", tps),
            "fn_avg_hl_range_pct": _avg("hl_range_pct", fns),
            "tp_avg_hl_range_pct": _avg("hl_range_pct", tps),
        },
        "C_score_cascade_weighting": {
            "verdict": verdict_c,
            "note": c_note,
        },
        "D_temporal_resolution_too_coarse": {
            "verdict": verdict_d,
            "note": d_note,
            "fn_d_proxy_count": n_d_proxy,
            "fn_d_proxy_share": round(n_d_proxy / n_fn, 6) if n_fn else None,
            "proxy_ratio_threshold": D_HL_VS_DROP_RATIO,
        },
    }

    # Sort FNs: largest drop first
    fns_sorted = sorted(fns, key=lambda x: x["bar_drop_pct"], reverse=True)

    result: Dict[str, Any] = {
        "schema": "raas_fn_belt_screen_v0",
        "map": MAP_REF,
        "parent_map": PARENT_MAP,
        "baseline_tag": BASELINE_TAG,
        "scope": SCOPE,
        "live_execution": False,
        "not_investment_advice": True,
        "order_send_count": 0,
        "definition_hash": def_hash,
        "definition_hash_match": True,
        "symbol": used_symbol,
        "days_requested": days,
        "n_bars": len(rows),
        "n_observed": sum(1 for f in features if f.observed_break),
        "n_predicted": sum(1 for p in predictions if p["break"]),
        "n_fn": n_fn,
        "n_tp": len(tps),
        "gate_reason_counts": reason_counts,
        "hypotheses": hypotheses,
        "false_negatives": fns_sorted,
        "fetch_log_tail": fetch_log[-15:],
        "generated_at": _now(),
        "note": (
            "Cause screen only — does not retune EXEC_RISK_BLOCK / CASCADE_BLOCK. "
            "A SUPPORTED means FN belt is the obs↔trip definition gap."
        ),
    }

    enforcer = DSuiteEnforcer()
    stamped = enforcer.enforce_all(
        EnforcerContext(
            caller_role="UNTRUSTED_SHELL",
            target_path="/api/v1/raas/evaluate",
            payload={
                "phase": "fn_belt_screen",
                "definition_hash": def_hash,
                "n_fn": n_fn,
                "verdict_a": verdict_a,
            },
        )
    )
    result["_worm_anchor_sha256"] = stamped.get("_worm_anchor_sha256")
    result["_d_suite_checked"] = True

    root = _repo_root()
    worm_dir = root / "logs" / "worm"
    worm_dir.mkdir(parents=True, exist_ok=True)
    worm_path = worm_dir / "fn_belt_screen.jsonl"
    with worm_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": _now(),
                    "phase": "fn_belt_screen",
                    "definition_hash": def_hash,
                    "n_fn": n_fn,
                    "hypotheses": {
                        k: v.get("verdict") for k, v in hypotheses.items()
                    },
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
    json_path = report_dir / "fn_belt_screen_latest.json"
    # Cap FN dump in markdown; full list in JSON
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    md_path = report_dir / "fn_belt_screen_latest.md"
    md_path.write_text(_to_markdown(result), encoding="utf-8")
    result["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def _to_markdown(result: Dict[str, Any]) -> str:
    h = result["hypotheses"]
    lines = [
        "# FN-Gürtel Screen (Ursachen A–D)",
        "",
        f"**Generated:** {result['generated_at']}",
        f"**Map:** `{result['map']}`",
        f"**Parent:** `{result['parent_map']}`",
        f"**definition_hash:** `{result['definition_hash']}` (match={result['definition_hash_match']})",
        f"**Scope:** `{result['scope']}` · `live_execution=false`",
        "",
        "## Cohort",
        "",
        f"- Symbol: `{result['symbol']}` · days={result['days_requested']} · bars={result['n_bars']}",
        f"- Observed={result['n_observed']} · Predicted={result['n_predicted']} · "
        f"**FN={result['n_fn']}** · TP={result['n_tp']}",
        "",
        "## Hypothesis verdicts",
        "",
        "| ID | Verdict | Key numbers |",
        "|----|---------|-------------|",
        (
            f"| **A** Trip-Schwellen | `{h['A_trip_thresholds_above_observed']['verdict']}` | "
            f"structural_gap={h['A_trip_thresholds_above_observed']['fn_structural_gap']}/"
            f"{result['n_fn']} · above_trip={h['A_trip_thresholds_above_observed']['fn_above_trip']} · "
            f"edges drop≥{EXEC_TRIP_DROP_PCT}% / dd≥{CASCADE_TRIP_DD_PCT}% |"
        ),
        (
            f"| **B** Features | `{h['B_feature_extraction_incomplete']['verdict']}` | "
            f"vol_z FN={h['B_feature_extraction_incomplete']['fn_avg_volume_z']} "
            f"TP={h['B_feature_extraction_incomplete']['tp_avg_volume_z']} |"
        ),
        (
            f"| **C** Cascade-Gewicht | `{h['C_score_cascade_weighting']['verdict']}` | "
            f"univariat unter Parent-MAP |"
        ),
        (
            f"| **D** Zeitauflösung | `{h['D_temporal_resolution_too_coarse']['verdict']}` | "
            f"HL-proxy {h['D_temporal_resolution_too_coarse']['fn_d_proxy_count']}/{result['n_fn']} |"
        ),
        "",
        "### Notes",
        "",
        f"- **B:** {h['B_feature_extraction_incomplete']['note']}",
        f"- **C:** {h['C_score_cascade_weighting']['note']}",
        f"- **D:** {h['D_temporal_resolution_too_coarse']['note']}",
        "",
        "## FN catalogue (all)",
        "",
        "| # | drop% | dd60% | class | HL% | vol_z | D-proxy |",
        "|---|-------|-------|-------|-----|-------|---------|",
    ]
    for i, fn in enumerate(result["false_negatives"], 1):
        lines.append(
            f"| {i} | {fn['bar_drop_pct']:.3f} | {fn['roll_dd_60_pct']:.3f} | "
            f"`{fn['fn_class']}` | {fn['hl_range_pct']:.3f} | {fn['volume_z']:.2f} | "
            f"{fn.get('d_proxy_intrabar')} |"
        )
    lines.extend(
        [
            "",
            "## Compliance",
            "",
            "```text",
            "live_execution = false",
            "order_send_count = 0",
            "status = RAAS_FN_BELT_SCREEN_PASS",
            "no_threshold_retune = true",
            "```",
            "",
            "*Cause screen — not a gate configuration change.*",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="RaaS FN-belt cause screen (A–D)")
    p.add_argument("--symbol", default="ETHUSDC")
    p.add_argument("--days", type=int, default=180)
    args = p.parse_args(argv)

    print("RaaS FN-Belt Screen (A–D)")
    print("=" * 60)
    print(f"map={MAP_REF}")
    print(f"definition_hash={definition_hash()} (expect {EXPECTED_DEF_HASH[:12]}…)")
    print(
        f"trip edges: drop≥{EXEC_TRIP_DROP_PCT}% · dd≥{CASCADE_TRIP_DD_PCT}% "
        f"(obs drop≥{BAR_DROP_OBS_PCT}% · dd≥{ROLL_DD_OBS_PCT}%)"
    )

    try:
        result = run_screen(symbol=args.symbol, days=args.days)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}")
        return 1

    print(
        f"FN={result['n_fn']} TP={result['n_tp']} "
        f"observed={result['n_observed']} predicted={result['n_predicted']}"
    )
    for key, body in result["hypotheses"].items():
        short = key.split("_", 1)[0].upper()
        print(f"  {short}: {body['verdict']}")
    print(f"report: {result['paths']['markdown']}")
    print("=" * 60)
    print("VERDICT: RAAS_FN_BELT_SCREEN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
