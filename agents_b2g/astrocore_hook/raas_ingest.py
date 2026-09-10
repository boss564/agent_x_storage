"""P3: Read-only RaaS audit JSONL → Class-C timestamp arrays for AstroCore hook."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np

DEFAULT_AUDIT_DIR = os.getenv("RAAS_AUDIT_DIR", "/data/audit")
DEFAULT_LOOKBACK_DAYS = int(os.getenv("ASTROCORE_NEO4J_LOOKBACK_DAYS", "7"))
DEFAULT_FUNDING_PERIOD_S = float(os.getenv("ASTROCORE_FUNDING_PERIOD_S", "28800.0"))
DEFAULT_LIMIT = int(os.getenv("ASTROCORE_NEO4J_LIMIT", "10000"))
MAX_LOOKBACK_DAYS = 90

DEFAULT_AUDIT_FILES: Tuple[str, ...] = (
    "feed_gaps.jsonl",
    "cross_venue_gaps.jsonl",
    "paper_edges.jsonl",
)

_TS_FIELD_NAMES: Tuple[str, ...] = (
    "ts",
    "timestamp",
    "time",
    "gap_start_ts",
    "gap_end_ts",
    "gap_start_recv_ts",
    "gap_end_recv_ts",
    "entry_tick_ts",
    "exit_tick_ts",
)


def _parse_ts_value(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.replace(".", "", 1).isdigit():
            return float(text)
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    return None


def extract_timestamps_from_record(record: dict) -> List[float]:
    """Extract all usable Unix timestamps from one audit JSONL record."""
    out: List[float] = []
    for key in _TS_FIELD_NAMES:
        ts = _parse_ts_value(record.get(key))
        if ts is not None:
            out.append(ts)
    return out


def _read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def parse_gap_logs(
    audit_dir: Path,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    *,
    audit_files: Sequence[str] = DEFAULT_AUDIT_FILES,
    limit: int = DEFAULT_LIMIT,
    funding_period_s: float = DEFAULT_FUNDING_PERIOD_S,
    synthetic_fallback: Optional[Callable[..., np.ndarray]] = None,
) -> Tuple[np.ndarray, dict]:
    """Read audit JSONL files and return sorted Unix timestamps (read-only)."""
    if lookback_days < 1:
        raise ValueError("lookback_days must be >= 1")
    if lookback_days > MAX_LOOKBACK_DAYS:
        raise ValueError(f"lookback_days={lookback_days} exceeds {MAX_LOOKBACK_DAYS}")
    if limit < 1:
        raise ValueError("limit must be >= 1")

    cutoff_ts = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).timestamp()

    timestamps: List[float] = []
    source_files: List[str] = []

    if audit_dir.is_dir():
        for name in audit_files:
            path = audit_dir / name
            if not path.is_file():
                continue
            source_files.append(name)
            for record in _read_jsonl(path):
                for ts in extract_timestamps_from_record(record):
                    if ts >= cutoff_ts:
                        timestamps.append(ts)

    if timestamps:
        unique = sorted(set(timestamps))
        if len(unique) > limit:
            unique = unique[-limit:]
        return np.array(unique, dtype=np.float64), {
            "provenance": "worm",
            "warnings": [],
            "source_files": source_files,
            "n_events": len(unique),
            "lookback_days": lookback_days,
            "funding_period_s": funding_period_s,
            "source": str(audit_dir),
        }

    warnings = [
        f"Keine Gap-Events in den letzten {lookback_days} Tagen unter {audit_dir}."
    ]
    if synthetic_fallback is None:
        synthetic_fallback = _default_synthetic_fallback
    events = synthetic_fallback(funding_period_s=funding_period_s)
    if not audit_dir.is_dir():
        warnings.insert(0, f"Audit-Verzeichnis {audit_dir} nicht gefunden.")
    return events, {
        "provenance": "gap_synthetic",
        "warnings": warnings,
        "source_files": source_files,
        "n_events": len(events),
        "lookback_days": lookback_days,
        "funding_period_s": funding_period_s,
        "source": "generate_synthetic_liquidations()",
    }


def _default_synthetic_fallback(*, funding_period_s: float) -> np.ndarray:
    import sys

    cherry = Path(__file__).resolve().parents[2] / "imports" / "cherrystudio" / "astrocore"
    path = str(cherry)
    if path not in sys.path:
        sys.path.insert(0, path)
    from test_liquidation_coupling import generate_synthetic_liquidations  # noqa: WPS433

    return generate_synthetic_liquidations(
        n_events=1000,
        funding_period=funding_period_s,
        cluster_strength=0.3,
    )
