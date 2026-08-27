#!/usr/bin/env python3
"""RaaS Flash-Crash Retrospective — Option 5 screen (MAP v0).

Replays public 1m klines through evaluate_gate risk layer and scores
envelope break hit-rate (precision/recall). Does not tune thresholds,
send orders, or claim investment performance.

Usage:
  PYTHONPATH=. python3 scripts/raas_flash_crash_retrospective.py --days 14
  PYTHONPATH=. python3 scripts/raas_flash_crash_retrospective.py --days 180
  make raas-flash-crash-retro
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
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
from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    EnforcerContext,
)
from services.fail_closed_gate.gate_core import (  # noqa: E402
    CASCADE_BLOCK,
    EXEC_RISK_BLOCK,
    GateInput,
    TradeSignal,
    evaluate_gate,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
MAP_REF = "docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md"
BASELINE_TAG = "v1.0-raas-baseline"

# --- Frozen MAP §3 (amendment requires new definition_hash) ---
BAR_DROP_OBS_PCT = 2.0
ROLL_DD_OBS_PCT = 5.0
ROLL_WINDOW = 60
EXEC_RISK_SCALE_PCT = 3.0
CASCADE_RISK_SCALE_PCT = 8.0

DEFINITION_PAYLOAD = {
    "bar_drop_obs_pct": BAR_DROP_OBS_PCT,
    "roll_dd_obs_pct": ROLL_DD_OBS_PCT,
    "roll_window": ROLL_WINDOW,
    "exec_risk_scale_pct": EXEC_RISK_SCALE_PCT,
    "cascade_risk_scale_pct": CASCADE_RISK_SCALE_PCT,
    "exec_risk_block": EXEC_RISK_BLOCK,
    "cascade_block": CASCADE_BLOCK,
    "human_gate_open_analysis_only": True,
    "latency_spike": None,
    "map": MAP_REF,
}


def definition_hash() -> str:
    blob = json.dumps(DEFINITION_PAYLOAD, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "services" / "fail_closed_gate").is_dir():
        return cwd
    return _ROOT


@dataclass
class BarFeatures:
    condition_id: str
    open_time: int
    bar_drop_pct: float
    roll_dd_60_pct: float
    exec_risk: float
    cascade_risk: float
    observed_break: bool


def _roll_drawdown_pct(closes: Sequence[float], i: int, window: int) -> float:
    start = max(0, i - window + 1)
    chunk = closes[start : i + 1]
    if not chunk:
        return 0.0
    peak = max(chunk)
    if peak <= 0:
        return 0.0
    return 100.0 * max(0.0, (peak - closes[i]) / peak)


def extract_features(
    rows: Sequence[Dict[str, Any]],
    *,
    symbol: str,
) -> List[BarFeatures]:
    closes = [float(r["close"]) for r in rows]
    out: List[BarFeatures] = []
    for i, r in enumerate(rows):
        if i == 0:
            drop = 0.0
        else:
            prev = closes[i - 1]
            drop = (
                100.0 * max(0.0, (prev - closes[i]) / prev) if prev > 0 else 0.0
            )
        dd = _roll_drawdown_pct(closes, i, ROLL_WINDOW)
        exec_risk = min(1.0, drop / EXEC_RISK_SCALE_PCT)
        cascade_risk = min(1.0, dd / CASCADE_RISK_SCALE_PCT)
        observed = (drop >= BAR_DROP_OBS_PCT) or (dd >= ROLL_DD_OBS_PCT)
        cid = f"{symbol}:{r['open_time']}"
        out.append(
            BarFeatures(
                condition_id=cid,
                open_time=int(r["open_time"]),
                bar_drop_pct=round(drop, 6),
                roll_dd_60_pct=round(dd, 6),
                exec_risk=round(exec_risk, 6),
                cascade_risk=round(cascade_risk, 6),
                observed_break=observed,
            )
        )
    return out


def predict_breaks(
    features: Sequence[BarFeatures],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    predictions: List[Dict[str, Any]] = []
    reason_counts: Dict[str, int] = {}
    for feat in features:
        inp = GateInput(
            signal=TradeSignal(
                signal_id=feat.condition_id,
                source="P3",
                notional_eur=1000.0,
                stress_score=max(feat.exec_risk, feat.cascade_risk),
                oracle_ok=True,
                scenario_ok=True,
            ),
            exec_risk=feat.exec_risk,
            cascade_risk=feat.cascade_risk,
            latency_spike=None,
            bho_delta=0.0,
            human_gate_open=True,  # analysis isolation — not live auth
        )
        verdict = evaluate_gate(inp)
        blocked = verdict.decision == "BLOCKED"
        for reason in verdict.reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        predictions.append(
            {
                "condition_id": feat.condition_id,
                "break": blocked,
                "decision": verdict.decision,
                "reasons": list(verdict.reasons),
            }
        )
    return predictions, reason_counts


def run_retrospective(
    *,
    symbol: str = "ETHUSDC",
    days: int = 14,
) -> Dict[str, Any]:
    root = _repo_root()
    symbols_try = [symbol.upper()]
    if symbols_try[0] != "ETHUSDT":
        symbols_try.append("ETHUSDT")

    rows: List[Dict[str, Any]] = []
    fetch_log: List[str] = []
    used_symbol = symbols_try[0]
    for sym in symbols_try:
        rows, fetch_log = fetch_binance_klines(sym, "1m", days)
        if rows:
            used_symbol = sym
            break

    if not rows:
        raise RuntimeError(
            f"No klines for {symbols_try} days={days}. "
            "Run without --cache-only or make raas-public-ingest-sondierung."
        )

    features = extract_features(rows, symbol=used_symbol)
    predictions, reason_counts = predict_breaks(features)
    observations = [
        {"condition_id": f.condition_id, "break": f.observed_break} for f in features
    ]
    stats = score_envelope_hits(predictions, observations)

    n_obs = sum(1 for o in observations if o["break"])
    n_pred = sum(1 for p in predictions if p["break"])

    # Sample extreme observed events for the report (top drops)
    extremes = sorted(features, key=lambda f: f.bar_drop_pct, reverse=True)[:10]
    extreme_rows = []
    pred_map = {p["condition_id"]: p for p in predictions}
    for f in extremes:
        if f.bar_drop_pct < BAR_DROP_OBS_PCT and f.roll_dd_60_pct < ROLL_DD_OBS_PCT:
            continue
        p = pred_map.get(f.condition_id, {})
        extreme_rows.append(
            {
                "condition_id": f.condition_id,
                "bar_drop_pct": f.bar_drop_pct,
                "roll_dd_60_pct": f.roll_dd_60_pct,
                "exec_risk": f.exec_risk,
                "cascade_risk": f.cascade_risk,
                "observed_break": f.observed_break,
                "predicted_break": bool(p.get("break")),
                "gate_reasons": p.get("reasons", []),
            }
        )

    def_hash = definition_hash()
    result: Dict[str, Any] = {
        "schema": "raas_flash_crash_retrospective_v0",
        "map": MAP_REF,
        "baseline_tag": BASELINE_TAG,
        "scope": SCOPE,
        "live_execution": False,
        "not_investment_advice": True,
        "order_send_count": 0,
        "definition_hash": def_hash,
        "definitions": DEFINITION_PAYLOAD,
        "symbol": used_symbol,
        "days_requested": days,
        "n_bars": len(rows),
        "n_observed_breaks": n_obs,
        "n_predicted_breaks": n_pred,
        "envelope_hit_rate": stats.to_dict(),
        "gate_reason_counts": reason_counts,
        "extreme_observed_sample": extreme_rows[:10],
        "fetch_log_tail": fetch_log[-20:],
        "generated_at": _now(),
        "note": (
            "Open hypothesis screen — results are not a track record. "
            "human_gate_open=True only isolates risk layer (MAP §3.2)."
        ),
    }

    enforcer = DSuiteEnforcer()
    stamped = enforcer.enforce_all(
        EnforcerContext(
            caller_role="UNTRUSTED_SHELL",
            target_path="/api/v1/raas/evaluate",
            payload={
                "phase": "flash_crash_retrospective",
                "definition_hash": def_hash,
                "symbol": used_symbol,
                "n_bars": len(rows),
                "envelope_summary": {
                    "precision": stats.precision,
                    "recall": stats.recall,
                    "tp": stats.true_positives,
                    "fp": stats.false_positives,
                    "fn": stats.false_negatives,
                },
            },
        )
    )
    result["_worm_anchor_sha256"] = stamped.get("_worm_anchor_sha256")
    result["_d_suite_checked"] = True

    # WORM append
    worm_dir = root / "logs" / "worm"
    worm_dir.mkdir(parents=True, exist_ok=True)
    worm_path = worm_dir / "flash_crash_retrospective.jsonl"
    worm_line = {
        "ts": _now(),
        "phase": "flash_crash_retrospective",
        "definition_hash": def_hash,
        "symbol": used_symbol,
        "n_bars": len(rows),
        "envelope_hit_rate": stats.to_dict(),
        "live_execution": False,
        "not_investment_advice": True,
        "order_send_count": 0,
        "scope": SCOPE,
        "_worm_anchor_sha256": result.get("_worm_anchor_sha256"),
    }
    with worm_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(worm_line, sort_keys=True) + "\n")
    result["worm_path"] = str(worm_path)

    # Reports
    report_dir = root / "exports" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "flash_crash_retrospective_latest.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    md_path = report_dir / "flash_crash_retrospective_latest.md"
    md_path.write_text(_to_markdown(result), encoding="utf-8")
    result["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def _to_markdown(result: Dict[str, Any]) -> str:
    hit = result["envelope_hit_rate"]
    lines = [
        "# Flash-Crash Retrospective (Option 5)",
        "",
        f"**Generated:** {result['generated_at']}",
        f"**Map:** `{result['map']}`",
        f"**definition_hash:** `{result['definition_hash']}`",
        f"**Baseline:** `{result['baseline_tag']}`",
        f"**Scope:** `{result['scope']}` · `live_execution=false` · `not_investment_advice=true`",
        "",
        "## Data",
        "",
        f"- Symbol: `{result['symbol']}`",
        f"- Days requested: {result['days_requested']}",
        f"- Bars: {result['n_bars']}",
        f"- Observed breaks: {result['n_observed_breaks']}",
        f"- Predicted breaks (risk layer): {result['n_predicted_breaks']}",
        "",
        "## Primary metric (envelope hit-rate)",
        "",
        "```text",
        f"precision = {hit['precision']}",
        f"recall    = {hit['recall']}",
        f"TP={hit['true_positives']}  FP={hit['false_positives']}  "
        f"FN={hit['false_negatives']}",
        "```",
        "",
        "## Gate reason counts (diagnostic)",
        "",
        "```text",
    ]
    for k, v in sorted(result.get("gate_reason_counts", {}).items()):
        lines.append(f"{k} = {v}")
    lines.extend(
        [
            "```",
            "",
            "## Compliance",
            "",
            "```text",
            "live_execution = false",
            "order_send_count = 0",
            "status = RAAS_FLASH_CRASH_RETRO_PASS",
            "```",
            "",
            "*Open hypothesis screen — not investment advice, not a track record.*",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="RaaS flash-crash retrospective screen")
    p.add_argument("--symbol", default="ETHUSDC")
    p.add_argument("--days", type=int, default=14, help="1m window (180 for full screen)")
    args = p.parse_args(argv)

    print("RaaS Flash-Crash Retrospective (Option 5)")
    print("=" * 60)
    print(f"map={MAP_REF}")
    print(f"definition_hash={definition_hash()}")
    print(f"symbol={args.symbol} days={args.days}")
    print(
        f"frozen: drop≥{BAR_DROP_OBS_PCT}% OR dd60≥{ROLL_DD_OBS_PCT}% | "
        f"exec_scale={EXEC_RISK_SCALE_PCT}% cascade_scale={CASCADE_RISK_SCALE_PCT}%"
    )

    try:
        result = run_retrospective(symbol=args.symbol, days=args.days)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}")
        return 1

    hit = result["envelope_hit_rate"]
    print(f"bars={result['n_bars']} observed={result['n_observed_breaks']} "
          f"predicted={result['n_predicted_breaks']}")
    print(
        f"precision={hit['precision']:.4f} recall={hit['recall']:.4f} "
        f"TP={hit['true_positives']} FP={hit['false_positives']} "
        f"FN={hit['false_negatives']}"
    )
    print(f"report: {result['paths']['markdown']}")
    print("=" * 60)
    print("VERDICT: RAAS_FLASH_CRASH_RETRO_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
