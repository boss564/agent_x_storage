#!/usr/bin/env python3
"""
M2 ingest progress report — no backtest, read-only JSONL audit.

Gate-close anchor: NEWS_SCHEDULER_GATE_CLOSE_TS (liveness.py).
90-day target: H1_M2_EVENT_DRIVEN_SPEC §4.2 / shadow_lag MIN_CALENDAR_DAYS.

Usage:
  PYTHONPATH=. python3 scripts/m2_ingest_status.py
  PYTHONPATH=. python3 scripts/m2_ingest_status.py --data /opt/agent-x/data/news_scores.jsonl
  PYTHONPATH=. python3 scripts/m2_ingest_status.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.backtest_h1_news_m2_shadow_lag import (  # noqa: E402
    LAG_BUCKETS_SEC,
    MIN_CALENDAR_DAYS,
    MIN_GATED_EVENTS,
    assign_lag_bucket,
)
from services.news_agent.liveness import (  # noqa: E402
    NEWS_SCHEDULER_GATE_CLOSE_TS,
    parse_marker_ts,
)
from src.ingestion.news_jsonl_loader import tail_jsonl_lines  # noqa: E402

RUN_MARKER_TYPE = "run_marker"
REQUIRED_SCHEMA = "news_agent_multi/v1.3"
LAG_GO_THRESHOLD_MINUTES = 15
LAG_MIN_OBSERVATIONS = 100
DEFAULT_DATA_FILE = Path("data/news_scores.jsonl")
TAIL_SAMPLE = 100


@dataclass(frozen=True)
class M2IngestStatus:
    gate_close: str
    now_utc: str
    days_since_gate: float
    days_until_target: float
    target_days: int
    data_path: str
    file_exists: bool
    size_bytes: int
    mtime_utc: Optional[str]
    mtime_age_minutes: Optional[float]
    line_count: Optional[int]
    newest_record_utc: Optional[str]
    newest_record_age_minutes: Optional[float]
    tail_news_rows: int
    tail_lag_count: int
    tail_lag_buckets: dict[str, int]
    tail_lag_median_sec: Optional[float]
    tail_lag_max_sec: Optional[float]
    ingest_rate_per_day: Optional[float]
    lag_report_verdict: Optional[str]
    lag_report_measurability: Optional[str]
    lag_report_median_min: Optional[float]
    recommendation: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def count_lines(filepath: Path) -> int:
    try:
        result = subprocess.run(
            ["wc", "-l", str(filepath)],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.split()[0])
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        with filepath.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)


def _parse_record_ts(rec: dict[str, Any]) -> Optional[datetime]:
    for key in ("published_at", "timestamp", "ts"):
        raw = rec.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        dt = parse_marker_ts(str(raw))
        if dt is not None:
            return dt
    return None


def _extract_lag_seconds(rec: dict[str, Any]) -> Optional[float]:
    lag = rec.get("detection_lag")
    if lag is None:
        lag = rec.get("detection_lag_sec")
    if lag is None:
        return None
    try:
        return float(lag)
    except (TypeError, ValueError):
        return None


def _is_news_row(rec: dict[str, Any]) -> bool:
    if rec.get("source_type") == RUN_MARKER_TYPE:
        return False
    schema = rec.get("schema")
    if schema is not None and schema != REQUIRED_SCHEMA:
        return False
    return True


def _full_lag_report(data_path: Path) -> dict[str, Any]:
    """Lazy import — skeleton pulls ccxt via backtest_h1_price."""
    try:
        from scripts.backtest_h1_news_m2_skeleton import report_detection_lag
    except ImportError:
        return {
            "measurability": "UNAVAILABLE",
            "verdict": None,
            "note": "report_detection_lag unavailable (missing optional deps)",
        }
    return report_detection_lag(data_path)


def collect_status(data_path: Path, *, tail_n: int = TAIL_SAMPLE) -> M2IngestStatus:
    gate_close = parse_marker_ts(NEWS_SCHEDULER_GATE_CLOSE_TS)
    if gate_close is None:
        raise RuntimeError(f"invalid gate close: {NEWS_SCHEDULER_GATE_CLOSE_TS}")

    now = _utc_now()
    days_since = (now - gate_close).total_seconds() / 86400.0
    days_until = max(0.0, MIN_CALENDAR_DAYS - days_since)

    if not data_path.is_file():
        return M2IngestStatus(
            gate_close=gate_close.isoformat(),
            now_utc=now.isoformat(),
            days_since_gate=days_since,
            days_until_target=days_until,
            target_days=MIN_CALENDAR_DAYS,
            data_path=str(data_path),
            file_exists=False,
            size_bytes=0,
            mtime_utc=None,
            mtime_age_minutes=None,
            line_count=None,
            newest_record_utc=None,
            newest_record_age_minutes=None,
            tail_news_rows=0,
            tail_lag_count=0,
            tail_lag_buckets={name: 0 for name in LAG_BUCKETS_SEC},
            tail_lag_median_sec=None,
            tail_lag_max_sec=None,
            ingest_rate_per_day=None,
            lag_report_verdict=None,
            lag_report_measurability=None,
            lag_report_median_min=None,
            recommendation=f"Datei fehlt: {data_path}",
        )

    stat = data_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    mtime_age_min = (now - mtime).total_seconds() / 60.0
    line_count = count_lines(data_path)

    lines = tail_jsonl_lines(data_path, tail_n)
    records: list[dict[str, Any]] = []
    lags: list[float] = []
    timestamps: list[datetime] = []
    buckets = {name: 0 for name in LAG_BUCKETS_SEC}

    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or not _is_news_row(rec):
            continue
        records.append(rec)
        lag = _extract_lag_seconds(rec)
        if lag is not None:
            lags.append(lag)
            bucket = assign_lag_bucket(lag)
            if bucket is not None:
                buckets[bucket] += 1
        ts = _parse_record_ts(rec)
        if ts is not None:
            timestamps.append(ts)

    newest = max(timestamps) if timestamps else None
    newest_age_min = (
        (now - newest).total_seconds() / 60.0 if newest is not None else None
    )
    ingest_rate = line_count / max(days_since, 1e-9) if line_count else None

    lag_report = _full_lag_report(data_path)
    lag_verdict = lag_report.get("verdict")
    lag_meas = lag_report.get("measurability")
    lag_median = lag_report.get("median_lag_min")

    recommendation = _recommendation(
        days_since=days_since,
        days_until=days_until,
        line_count=line_count,
        mtime_age_min=mtime_age_min,
        newest_age_min=newest_age_min,
        tail_buckets=buckets,
        tail_lag_count=len(lags),
        lag_report=lag_report,
    )

    return M2IngestStatus(
        gate_close=gate_close.isoformat(),
        now_utc=now.isoformat(),
        days_since_gate=round(days_since, 2),
        days_until_target=round(days_until, 2),
        target_days=MIN_CALENDAR_DAYS,
        data_path=str(data_path),
        file_exists=True,
        size_bytes=stat.st_size,
        mtime_utc=mtime.isoformat(),
        mtime_age_minutes=round(mtime_age_min, 1),
        line_count=line_count,
        newest_record_utc=newest.isoformat() if newest else None,
        newest_record_age_minutes=round(newest_age_min, 1) if newest_age_min is not None else None,
        tail_news_rows=len(records),
        tail_lag_count=len(lags),
        tail_lag_buckets=buckets,
        tail_lag_median_sec=round(statistics.median(lags), 1) if lags else None,
        tail_lag_max_sec=round(max(lags), 1) if lags else None,
        ingest_rate_per_day=round(ingest_rate, 1) if ingest_rate is not None else None,
        lag_report_verdict=lag_verdict,
        lag_report_measurability=lag_meas,
        lag_report_median_min=lag_median,
        recommendation=recommendation,
    )


def _recommendation(
    *,
    days_since: float,
    days_until: float,
    line_count: Optional[int],
    mtime_age_min: float,
    newest_age_min: Optional[float],
    tail_buckets: dict[str, int],
    tail_lag_count: int,
    lag_report: dict[str, Any],
) -> str:
    parts: list[str] = []

    if days_until <= 0:
        parts.append(
            f"{MIN_CALENDAR_DAYS} Tage seit Gate-Close erreicht — M2-OOS-Replay prüfbar "
            f"(≥{MIN_GATED_EVENTS} gated events, Spec §4.2)."
        )
    else:
        parts.append(
            f"Warten: noch {days_until:.1f} Tage bis {MIN_CALENDAR_DAYS}-Tage-Ziel."
        )

    if line_count is not None and days_since > 0:
        parts.append(f"Ingest ~{line_count / days_since:.0f} Zeilen/Tag ({line_count} gesamt).")

    if mtime_age_min > 150:
        parts.append(f"WARN: Datei {mtime_age_min:.0f} min ohne Schreibzugriff (>150 min).")
    if newest_age_min is not None and newest_age_min > 150:
        parts.append(f"WARN: neuester News-Eintrag {newest_age_min:.0f} min alt.")

    if tail_lag_count > 0:
        gt60 = tail_buckets.get("GT_60", 0)
        if gt60 / tail_lag_count > 0.5:
            parts.append(
                f"WARN: >50 % Tail-Lag in GT_60 (>60 min) — Polling-Epoche (§11) prüfen."
            )

    meas = lag_report.get("measurability")
    if meas == "NO_GO_POLLING_EPOCH_FIRST":
        parts.append(
            f"Tag-7-Lag: Median {lag_report.get('median_lag_min', '?')} min "
            f"> {LAG_GO_THRESHOLD_MINUTES} min (vorreg NO-GO)."
        )
    elif meas == "GO_90D_PATH":
        parts.append("Tag-7-Lag: GO — 90d-Pfad methodisch offen.")
    elif meas == "INSUFFICIENT_DATA":
        n_lag = lag_report.get("n_with_lag", 0)
        parts.append(
            f"Tag-7-Lag: noch unzureichend (n_with_lag={n_lag}, "
            f"Schwelle {LAG_MIN_OBSERVATIONS})."
        )

    return " ".join(parts)


def _format_text(status: M2IngestStatus) -> str:
    lines = [
        "=== M2 INGEST STATUS ===",
        f"Gate-Close:      {status.gate_close}",
        f"Aktuell:         {status.now_utc}",
        f"Tage seit Gate:  {status.days_since_gate:.1f}",
        f"Tage bis Ziel:   {status.days_until_target:.1f} (von {status.target_days})",
    ]
    if not status.file_exists:
        lines.append(f"\nDatei fehlt:     {status.data_path}")
        lines.append(f"\n--- EMPFEHLUNG ---\n{status.recommendation}")
        return "\n".join(lines)

    size_mb = status.size_bytes / (1024 * 1024)
    lines.extend(
        [
            "",
            f"Datei:           {status.data_path}",
            f"Größe:           {size_mb:.2f} MB",
            f"Letzte Änderung: {status.mtime_utc}",
            f"Alter (mtime):   {status.mtime_age_minutes:.1f} min",
            f"Zeilen gesamt:   {status.line_count}",
        ]
    )
    if status.newest_record_utc:
        lines.append(
            f"Neuester Eintrag: {status.newest_record_utc} "
            f"({status.newest_record_age_minutes:.1f} min alt)"
        )
    if status.tail_lag_count:
        lines.append(f"\nLag-Buckets (letzte {status.tail_lag_count}, Spec §2.2.1):")
        for name, (lo, hi) in LAG_BUCKETS_SEC.items():
            n = status.tail_lag_buckets.get(name, 0)
            pct = 100.0 * n / status.tail_lag_count
            hi_label = "∞" if hi == float("inf") else f"{int(hi)}s"
            lines.append(f"  {name} ({int(lo)}–{hi_label}): {n} ({pct:.1f}%)")
        lines.append(
            f"  Median: {status.tail_lag_median_sec:.1f}s, "
            f"Max: {status.tail_lag_max_sec:.1f}s"
        )
    else:
        lines.append("\nKeine detection_lag in den letzten News-Zeilen.")

    if status.lag_report_median_min is not None:
        lines.append(
            f"\nVollständiger Lag-Report: median={status.lag_report_median_min:.1f} min, "
            f"verdict={status.lag_report_verdict}, measurability={status.lag_report_measurability}"
        )

    lines.append(f"\n--- EMPFEHLUNG ---\n{status.recommendation}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="M2 ingest status (no backtest)")
    parser.add_argument(
        "--data",
        default=os.environ.get("NEWS_AGENT_MULTI_JSONL", str(DEFAULT_DATA_FILE)),
        help="Path to news_scores.jsonl",
    )
    parser.add_argument("--tail", type=int, default=TAIL_SAMPLE, help="Tail sample size")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    status = collect_status(Path(args.data), tail_n=args.tail)

    if args.json:
        print(json.dumps(asdict(status), indent=2))
    else:
        print(_format_text(status))

    return 1 if not status.file_exists else 0


if __name__ == "__main__":
    raise SystemExit(main())
