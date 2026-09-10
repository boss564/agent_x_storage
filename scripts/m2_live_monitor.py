#!/usr/bin/env python3
"""
M2 live monitor — rolling lag buckets (spec §2.2.1) + slippage diagnostic.

Metrics only; no trading decisions. Use Tag-7 ``--lag-report`` for GO/NO-GO;
use ``backtest_h1_news_m2_shadow.py`` after ≥90d + ≥200 gated events.

Audit-writer liveness (instance 7): appends ``kind=run_marker`` to
``data/m2_live_monitor.jsonl`` every cycle — absence = monitor dead, not
``lag_samples=0`` in news JSONL.

Cron-friendly: ``--once`` exits after one report (systemd timer / hourly).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_news_m2_shadow_lag import (  # noqa: E402
    LAG_BUCKETS_SEC,
    assign_lag_bucket,
    estimate_slippage_bps,
)
from services.m2_live_monitor.liveness import (  # noqa: E402
    DEFAULT_AUDIT_JSONL,
    append_run_marker,
    run_marker_freshness,
)
from src.ingestion.news_jsonl_loader import tail_jsonl_lines  # noqa: E402

REQUIRED_SCHEMA = "news_agent_multi/v1.3"
DEFAULT_JSONL = os.environ.get("NEWS_AGENT_MULTI_JSONL", "data/news_scores.jsonl")
DEFAULT_INTERVAL_SEC = 3600
DEFAULT_SAMPLE = 1000

logger = logging.getLogger("m2_live_monitor")


def _extract_lag(record: Mapping[str, Any]) -> Optional[float]:
    lag = record.get("detection_lag")
    if lag is None:
        lag = record.get("detection_lag_sec")
    if lag is None:
        return None
    try:
        return float(lag)
    except (TypeError, ValueError):
        return None


def _sigma_from_record(record: Mapping[str, Any]) -> Optional[float]:
    vola = record.get("volatility_15m")
    if vola is None:
        return None
    try:
        return float(vola)
    except (TypeError, ValueError):
        return None


def count_lag_buckets(lags: List[float]) -> Dict[str, int]:
    counts = {name: 0 for name in LAG_BUCKETS_SEC}
    for lag in lags:
        bucket = assign_lag_bucket(lag)
        if bucket is not None:
            counts[bucket] += 1
    return counts


def bucket_labels() -> Dict[str, str]:
    return {
        "LT_15M": "<15 min",
        "M15_60": "15–60 min",
        "GT_60": ">60 min",
    }


def build_report(
    jsonl_path: Path,
    *,
    sample_size: int = DEFAULT_SAMPLE,
) -> Dict[str, Any]:
    lines = tail_jsonl_lines(jsonl_path, sample_size)
    lags: List[float] = []
    slippages: List[float] = []
    schema_rows = 0
    content_rows = 0

    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("source_type") == "run_marker":
            continue
        content_rows += 1
        if rec.get("schema") == REQUIRED_SCHEMA:
            schema_rows += 1
        lag = _extract_lag(rec)
        if lag is not None:
            lags.append(lag)
        sigma = _sigma_from_record(rec)
        slippages.append(estimate_slippage_bps(sigma_15m=sigma))

    bucket_counts = count_lag_buckets(lags)
    total_lags = len(lags)
    bucket_pct = {
        name: round(count / total_lags, 4) if total_lags else 0.0
        for name, count in bucket_counts.items()
    }

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "jsonl": str(jsonl_path),
        "sample_size": sample_size,
        "lines_read": len(lines),
        "content_rows": content_rows,
        "schema_v13_rows": schema_rows,
        "lag_samples": total_lags,
        "lag_bucket_counts": bucket_counts,
        "lag_bucket_pct": bucket_pct,
        "lag_bucket_labels": bucket_labels(),
        "median_lag_min": (
            round(statistics.median(lags) / 60.0, 2) if lags else None
        ),
        "avg_slippage_bps": round(statistics.mean(slippages), 2) if slippages else None,
        "note": (
            "M15_60 carries shadow backtest; LT_15M often thin at hourly cron. "
            "Non-significance with MDE caveat ≠ no alpha."
        ),
    }

    if total_lags > 100 and bucket_pct.get("M15_60", 0.0) < 0.5:
        report["warning"] = (
            "M15_60 share <50% in rolling window — check polling / published_at coverage"
        )

    return report


def emit_report(report: Dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    labels = report.get("lag_bucket_labels") or {}
    counts = report.get("lag_bucket_counts") or {}
    pct = report.get("lag_bucket_pct") or {}
    print("=== M2 LIVE MONITOR (metrics only) ===")
    print(f"UTC:           {report.get('timestamp_utc')}")
    print(f"JSONL:         {report.get('jsonl')}")
    print(f"Content rows:  {report.get('content_rows')} (v1.3: {report.get('schema_v13_rows')})")
    print(f"Lag samples:   {report.get('lag_samples')} (window={report.get('sample_size')})")
    if report.get("median_lag_min") is not None:
        print(f"Median lag:    {report['median_lag_min']} min")
    if report.get("avg_slippage_bps") is not None:
        print(f"Avg slippage:  {report['avg_slippage_bps']} bps (proxy)")
    print("Lag buckets (spec §2.2.1):")
    for name in LAG_BUCKETS_SEC:
        print(
            f"  {name} ({labels.get(name, name)}): "
            f"{counts.get(name, 0)} ({pct.get(name, 0.0):.0%})"
        )
    if report.get("warning"):
        print(f"WARNING: {report['warning']}")
    print(f"Note: {report.get('note')}")


def run_cycle(
    jsonl_path: Path,
    audit_path: Path,
    *,
    sample_size: int,
    as_json: bool,
    log_file: str,
) -> int:
    """One observation cycle — always appends run_marker to audit JSONL."""
    stub: Dict[str, Any] = {
        "jsonl": str(jsonl_path),
        "lag_samples": 0,
        "lag_bucket_counts": {name: 0 for name in LAG_BUCKETS_SEC},
    }
    prior = run_marker_freshness(audit_path)
    if not prior.get("ok"):
        logger.warning("Prior monitor marker: %s", prior.get("status"))

    if not jsonl_path.is_file():
        append_run_marker(
            audit_path,
            stub,
            status="error",
            error=f"news_jsonl_not_found:{jsonl_path}",
        )
        logger.error("JSONL not found: %s", jsonl_path)
        return 2

    try:
        report = build_report(jsonl_path, sample_size=sample_size)
        emit_report(report, as_json=as_json)
        if log_file:
            logger.info("%s", json.dumps(report, ensure_ascii=False))
        warn = report.get("warning")
        if warn:
            logger.warning(warn)
        marker = append_run_marker(audit_path, report, status="ok")
        if as_json:
            print(json.dumps({"run_marker": marker}, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        append_run_marker(audit_path, stub, status="error", error=str(exc))
        logger.exception("Monitor cycle failed: %s", exc)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="M2 live lag/slippage monitor (metrics only)")
    parser.add_argument(
        "jsonl",
        nargs="?",
        default=DEFAULT_JSONL,
        help="Path to news_scores.jsonl (active file; tail sample)",
    )
    parser.add_argument(
        "--audit-jsonl",
        default=DEFAULT_AUDIT_JSONL,
        help="Liveness audit trail (kind=run_marker per cycle)",
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC)
    parser.add_argument("--once", action="store_true", help="Single report then exit")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--log-file",
        default="",
        help="Optional log file (default: stderr only unless set)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        filename=args.log_file or None,
    )

    jsonl_path = Path(args.jsonl)
    audit_path = Path(args.audit_jsonl)

    if args.once:
        return run_cycle(
            jsonl_path,
            audit_path,
            sample_size=args.sample_size,
            as_json=args.json,
            log_file=args.log_file,
        )

    while True:
        try:
            run_cycle(
                jsonl_path,
                audit_path,
                sample_size=args.sample_size,
                as_json=args.json,
                log_file=args.log_file,
            )
            time.sleep(max(60, args.interval))
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
