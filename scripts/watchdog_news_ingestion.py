#!/usr/bin/env python3
"""Watchdog: News ingestion & pipeline health (read-only JSONL audit).

Cron-aligned thresholds (hourly :00 default):
  WARN     ≈ 1.5 × interval  (90 min — one missed run)
  CRITICAL ≈ 2.5 × interval  (150 min — two missed runs)
  run_marker: NEWS_MARKER_MAX_AGE_H (2 h = 2 × interval)

Content metrics (lag, published_at per RSS source) are **reported only** —
no exit-code WARN. Tag-7 ``--lag-report`` owns measurability; pooled lag /
pubdate gates fired on normal hourly operation.

Exit codes: 0 = OK, 1 = WARN, 2 = CRITICAL
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.news_agent.liveness import NEWS_MARKER_MAX_AGE_H, last_run_marker, parse_marker_ts
from src.ingestion.news_jsonl_loader import tail_jsonl_lines

RUN_MARKER_TYPE = "run_marker"

# Hourly host cron (:00) — thresholds scale with WATCHDOG_CRON_INTERVAL_MINUTES.
# WARN ≈ 1.5×, CRITICAL ≈ 2.5× interval (e.g. 60→90/150 min; 5→7.5/12.5 min post §11).
CRON_INTERVAL_MINUTES = 60
WARN_INTERVAL_MULT = 1.5
CRITICAL_INTERVAL_MULT = 2.5

# Per-source published_at: RSS only (announcements may lack field until v1.3 deploy).
MIN_PUBDATE_SAMPLES_PER_SOURCE = 3
MIN_PUBDATE_COVERAGE_RSS = 0.90

DEFAULT_CONFIG: Dict[str, Any] = {
    "JSONL_PATH": os.environ.get("NEWS_AGENT_MULTI_JSONL", "data/news_scores.jsonl"),
    "CRON_INTERVAL_MINUTES": CRON_INTERVAL_MINUTES,
    "WARN_STALE_MINUTES": int(CRON_INTERVAL_MINUTES * WARN_INTERVAL_MULT),
    "MAX_STALE_MINUTES": int(CRON_INTERVAL_MINUTES * CRITICAL_INTERVAL_MULT),
    "WARN_DATA_AGE_MINUTES": int(CRON_INTERVAL_MINUTES * WARN_INTERVAL_MULT),
    "MAX_DATA_AGE_MINUTES": int(CRON_INTERVAL_MINUTES * CRITICAL_INTERVAL_MULT),
    "REQUIRED_FIELDS": ["timestamp", "sentiment_score"],
    "SAMPLE_SIZE": 50,
    "OUTPUT_FORMAT": "text",
}


def derive_interval_thresholds(interval_min: int) -> Dict[str, int]:
    """WARN ≈ 1.5×, CRITICAL ≈ 2.5× cron interval (minutes)."""
    return {
        "WARN_STALE_MINUTES": int(interval_min * WARN_INTERVAL_MULT),
        "MAX_STALE_MINUTES": int(interval_min * CRITICAL_INTERVAL_MULT),
        "WARN_DATA_AGE_MINUTES": int(interval_min * WARN_INTERVAL_MULT),
        "MAX_DATA_AGE_MINUTES": int(interval_min * CRITICAL_INTERVAL_MULT),
    }


def get_config() -> Dict[str, Any]:
    """Load config with WATCHDOG_* env overrides; scale thresholds from interval."""
    cfg: Dict[str, Any] = {
        **DEFAULT_CONFIG,
        "REQUIRED_FIELDS": list(DEFAULT_CONFIG["REQUIRED_FIELDS"]),
    }
    for key in DEFAULT_CONFIG:
        env_key = f"WATCHDOG_{key}"
        if env_key not in os.environ:
            continue
        val = os.environ[env_key]
        default = DEFAULT_CONFIG[key]
        if isinstance(default, bool):
            cfg[key] = val.lower() in ("true", "1", "yes")
        elif isinstance(default, int):
            cfg[key] = int(val)
        elif isinstance(default, float):
            cfg[key] = float(val)
        elif isinstance(default, list):
            cfg[key] = [x.strip() for x in val.split(",") if x.strip()]
        else:
            cfg[key] = val

    interval = int(cfg.get("CRON_INTERVAL_MINUTES", CRON_INTERVAL_MINUTES))
    derived = derive_interval_thresholds(interval)
    for key, value in derived.items():
        if f"WATCHDOG_{key}" not in os.environ:
            cfg[key] = value
    cfg["thresholds_derived_from_minutes"] = interval
    return cfg


def tail_lines(file_path: Path, n: int) -> List[str]:
    """Last *n* non-empty lines (delegates to shared JSONL tail helper)."""
    return tail_jsonl_lines(file_path, n)


def parse_record(line: str) -> Optional[Dict[str, Any]]:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    return row if isinstance(row, dict) else None


def is_run_marker(record: Mapping[str, Any]) -> bool:
    return record.get("source_type") == RUN_MARKER_TYPE


def extract_lag(record: Mapping[str, Any]) -> Optional[float]:
    lag = record.get("detection_lag")
    if lag is None:
        lag = record.get("detection_lag_sec")
    if lag is None:
        return None
    try:
        return float(lag)
    except (TypeError, ValueError):
        return None


def parse_record_timestamp(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return parse_marker_ts(str(ts))
    except (ValueError, TypeError, OverflowError):
        return None


def compute_percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_vals):
        return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
    return sorted_vals[f]


def rss_pubdate_coverage(
    content_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Per RSS source_name: total / with published_at (announcements excluded)."""
    by_source: Dict[str, Dict[str, int]] = {}
    for rec in content_rows:
        if rec.get("source_type") != "rss":
            continue
        src = str(rec.get("source_name") or "unknown")
        bucket = by_source.setdefault(src, {"total": 0, "with_pub": 0})
        bucket["total"] += 1
        pub = rec.get("published_at")
        if pub not in (None, ""):
            bucket["with_pub"] += 1
    out: Dict[str, Dict[str, Any]] = {}
    for src, counts in by_source.items():
        total = counts["total"]
        with_pub = counts["with_pub"]
        out[src] = {
            "total": total,
            "with_published_at": with_pub,
            "coverage": round(with_pub / total, 4) if total else 0.0,
        }
    return out


@dataclass
class WatchdogResult:
    status: str = "UNKNOWN"
    exit_code: int = 2
    checks: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "checks": self.checks,
            "metrics": self.metrics,
            "messages": self.messages,
        }


def analyze_jsonl(file_path: Path, config: Mapping[str, Any]) -> Tuple[int, WatchdogResult]:
    """Run transport/liveness checks; content lag/pubdate are metrics-only."""
    result = WatchdogResult()
    result.metrics["cron_interval_minutes"] = int(
        config.get("thresholds_derived_from_minutes", config.get("CRON_INTERVAL_MINUTES", 60))
    )
    result.metrics["warn_stale_minutes"] = int(config["WARN_STALE_MINUTES"])
    result.metrics["max_stale_minutes"] = int(config["MAX_STALE_MINUTES"])

    if not file_path.is_file():
        result.messages.append(f"CRITICAL: Datei nicht gefunden: {file_path}")
        result.checks["file_exists"] = False
        result.status = "CRITICAL"
        result.exit_code = 2
        return result.exit_code, result
    result.checks["file_exists"] = True

    now = datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    stale_min = (now - mtime).total_seconds() / 60.0
    result.metrics["file_age_minutes"] = stale_min
    warn_stale = float(config["WARN_STALE_MINUTES"])
    max_stale = float(config["MAX_STALE_MINUTES"])
    result.checks["file_freshness"] = stale_min <= max_stale
    if stale_min > max_stale:
        result.messages.append(
            f"CRITICAL: Keine Dateiänderung seit {stale_min:.1f} min (> {max_stale:.0f} min)"
        )
    elif stale_min > warn_stale:
        result.messages.append(
            f"WARN: Datei zuletzt vor {stale_min:.1f} min geändert (> {warn_stale:.0f} min)"
        )

    try:
        lines = tail_lines(file_path, int(config["SAMPLE_SIZE"]))
    except OSError as exc:
        result.messages.append(f"CRITICAL: Datei konnte nicht gelesen werden: {exc}")
        result.checks["readable"] = False
        result.status = "CRITICAL"
        result.exit_code = 2
        return result.exit_code, result

    if not lines:
        result.messages.append("CRITICAL: Datei ist leer oder enthält keine Zeilen.")
        result.checks["has_records"] = False
        result.status = "CRITICAL"
        result.exit_code = 2
        return result.exit_code, result
    result.checks["has_records"] = True

    required = set(config["REQUIRED_FIELDS"])
    parsed: List[Dict[str, Any]] = []
    corrupted = 0
    for line in lines:
        rec = parse_record(line)
        if rec is None:
            corrupted += 1
            continue
        if is_run_marker(rec):
            parsed.append(rec)
            continue
        if required - set(rec.keys()):
            corrupted += 1
            continue
        parsed.append(rec)

    result.metrics["lines_sampled"] = len(lines)
    result.metrics["corrupted_lines"] = corrupted
    result.metrics["total_parsed"] = len(parsed)

    if not parsed:
        result.messages.append("CRITICAL: Keine gültigen JSON-Datensätze in der Stichprobe.")
        result.checks["valid_records"] = False
        result.status = "CRITICAL"
        result.exit_code = 2
        return result.exit_code, result
    result.checks["valid_records"] = True

    content_rows = [r for r in parsed if not is_run_marker(r)]
    result.metrics["content_rows"] = len(content_rows)

    lags: List[float] = []
    timestamps: List[datetime] = []
    marker_timestamps: List[datetime] = []

    for rec in parsed:
        ts = parse_record_timestamp(rec.get("timestamp"))
        if ts is not None:
            timestamps.append(ts)
        if is_run_marker(rec):
            if ts is not None:
                marker_timestamps.append(ts)
            continue
        lag = extract_lag(rec)
        if lag is not None:
            lags.append(lag)

    coverage = rss_pubdate_coverage(content_rows)
    result.metrics["coverage_by_source"] = coverage
    result.checks["pubdate_complete"] = True
    low_sources: List[str] = []
    for src, stats in coverage.items():
        total = int(stats["total"])
        cov = float(stats["coverage"])
        if total >= MIN_PUBDATE_SAMPLES_PER_SOURCE and cov < MIN_PUBDATE_COVERAGE_RSS:
            low_sources.append(f"{src}={cov:.0%}")
    if low_sources:
        result.messages.append(
            "INFO: RSS published_at coverage low per source (metrics only, no WARN): "
            + ", ".join(sorted(low_sources))
        )

    if lags:
        result.metrics["avg_lag_sec"] = statistics.mean(lags)
        result.metrics["median_lag_sec"] = statistics.median(lags)
        result.metrics["p95_lag_sec"] = compute_percentile(lags, 95)
        result.metrics["max_lag_sec"] = max(lags)
        result.metrics["lag_samples"] = len(lags)
        result.messages.append(
            f"INFO: detection_lag median={result.metrics['median_lag_sec'] / 60:.1f} min "
            f"(n={len(lags)}) — use Tag-7 --lag-report for GO/NO-GO"
        )
    else:
        result.metrics.update(
            {
                "avg_lag_sec": None,
                "median_lag_sec": None,
                "p95_lag_sec": None,
                "max_lag_sec": None,
                "lag_samples": 0,
            }
        )
        if content_rows:
            result.messages.append(
                "INFO: Keine detection_lag-Werte in Content-Zeilen (Tag-7 Report nach v1.3-Deploy)"
            )

    warn_data = float(config["WARN_DATA_AGE_MINUTES"])
    max_data = float(config["MAX_DATA_AGE_MINUTES"])
    if timestamps:
        newest = max(timestamps)
        data_age_min = (now - newest).total_seconds() / 60.0
        result.metrics["newest_data_age_minutes"] = data_age_min
        result.checks["data_freshness"] = data_age_min <= max_data
        if data_age_min > max_data:
            result.messages.append(
                f"CRITICAL: Neuester Datensatz {data_age_min:.1f} min alt (> {max_data:.0f} min)"
            )
        elif data_age_min > warn_data:
            result.messages.append(
                f"WARN: Neuester Datensatz {data_age_min:.1f} min alt (> {warn_data:.0f} min)"
            )
    else:
        result.metrics["newest_data_age_minutes"] = None
        result.checks["data_freshness"] = None
        result.messages.append("WARN: Kein gültiger timestamp in der Stichprobe.")

    store_marker = last_run_marker(file_path)
    marker_ts = parse_marker_ts(str((store_marker or {}).get("ts") or ""))
    if marker_ts is None and marker_timestamps:
        marker_ts = max(marker_timestamps)
    if marker_ts is not None:
        marker_age_h = (now - marker_ts).total_seconds() / 3600.0
        result.metrics["newest_run_marker_age_hours"] = marker_age_h
        marker_ok = marker_age_h <= NEWS_MARKER_MAX_AGE_H
        result.checks["run_marker_fresh"] = marker_ok
        if not marker_ok:
            result.messages.append(
                f"CRITICAL: Neuester run_marker {marker_age_h:.1f} h alt "
                f"(> {NEWS_MARKER_MAX_AGE_H} h, NEWS_MARKER_MAX_AGE_H)"
            )
    else:
        result.metrics["newest_run_marker_age_hours"] = None
        result.checks["run_marker_fresh"] = None

    critical = [
        not result.checks.get("file_freshness", True),
        result.checks.get("data_freshness") is False,
        result.checks.get("run_marker_fresh") is False,
        not result.checks.get("valid_records", True),
    ]
    if any(critical):
        result.status = "CRITICAL"
        result.exit_code = 2
    else:
        warn = [
            stale_min > warn_stale,
            result.metrics.get("newest_data_age_minutes") is not None
            and float(result.metrics["newest_data_age_minutes"]) > warn_data,
        ]
        if any(warn):
            result.status = "WARNING"
            result.exit_code = 1
        else:
            result.status = "OK"
            result.exit_code = 0

    return result.exit_code, result


def print_text_report(file_path: Path, exit_code: int, result: WatchdogResult) -> None:
    m = result.metrics
    print("=== WATCHDOG INGESTION REPORT ===")
    print(f"File:            {file_path}")
    print(f"Status:          {result.status} (Exit {exit_code})")
    print(
        f"Thresholds:      WARN {m.get('warn_stale_minutes')} min / "
        f"CRITICAL {m.get('max_stale_minutes')} min "
        f"(cron {m.get('cron_interval_minutes')} min)"
    )
    print(f"File age:        {m.get('file_age_minutes', 0):.1f} min")
    if m.get("newest_data_age_minutes") is not None:
        print(f"Newest record:   {m['newest_data_age_minutes']:.1f} min old")
    if m.get("newest_run_marker_age_hours") is not None:
        print(f"Newest marker:   {m['newest_run_marker_age_hours']:.2f} h old")
    print(f"Lines sampled:   {m.get('lines_sampled', 0)}")
    print(f"Content rows:    {m.get('content_rows', 0)}")
    print(f"Corrupted lines: {m.get('corrupted_lines', 0)}")
    cov = m.get("coverage_by_source") or {}
    if cov:
        print("RSS pubDate coverage (per source, metrics only):")
        for src in sorted(cov):
            c = cov[src]
            print(f"  {src}: {c['with_published_at']}/{c['total']} ({c['coverage']:.0%})")
    if m.get("avg_lag_sec") is not None:
        print(f"Avg detection lag: {m['avg_lag_sec'] / 60:.2f} min (metrics only)")
        print(f"Median lag:        {m['median_lag_sec'] / 60:.2f} min")
        print(f"95th percentile:   {m['p95_lag_sec'] / 60:.2f} min")
        print(f"Lag samples:       {m['lag_samples']}")
    else:
        print("Detection lag:     keine Daten")
    if result.messages:
        print("\nMessages:")
        for msg in result.messages:
            print(f"  {msg}")
    print(f"\nExit code: {exit_code}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Watchdog für News-Ingestion-Pipeline")
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Pfad zur JSONL (überschreibt WATCHDOG_JSONL_PATH / NEWS_AGENT_MULTI_JSONL)",
    )
    parser.add_argument("--json", action="store_true", help="JSON-Ausgabe für Monitoring")
    parser.add_argument("--config", action="store_true", help="Konfiguration anzeigen")
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = get_config()
    if args.config:
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return 0

    file_path = Path(args.file or config["JSONL_PATH"])
    exit_code, result = analyze_jsonl(file_path, config)

    if args.json or config.get("OUTPUT_FORMAT") == "json":
        payload = result.to_dict()
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        payload["file_path"] = str(file_path)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_text_report(file_path, exit_code, result)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
