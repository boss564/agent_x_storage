"""AstroCore PhaseSource: price coverage gaps (v1).

Reads data/gap_reports.jsonl (Rule A COVERAGE_GAP), maps signed % moves
to PhaseSignal dicts. UNTRACKED_ENTITY is catalog noise — not sprayed
onto the watchlist. Diagnostic only. Does not send orders or touch the cluster.

Usage:
    python3 -m astrocore.sources.price_gap_source --lookback-hours 24
    python3 -m astrocore.sources.price_gap_source --asset BTC --lookback-hours 6
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from astrocore.sources.handoff import assert_diagnostic_rows, assert_handoff_output
from astrocore.sources.config import (
    DEFAULT_GAP_JSONL_PATH,
    DEFAULT_LOOKBACK_HOURS,
    GAP_ASSET_CONFIDENCE,
    GAP_OVERALL_CONFIDENCE,
    GAP_PROVIDER_ID,
    GAP_SCALE_1H,
    GAP_SCALE_24H,
)
from services.news_agent.liveness import INVARIANT

RUN_MARKER_KIND = "run_marker"
COVERAGE_KIND = "COVERAGE_GAP"
UNTRACKED_KIND = "UNTRACKED_ENTITY"
DEFAULT_PHASE_JSONL = _ROOT / "data" / "phase_signals" / "price_gap.jsonl"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clip_unit(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def window_triggers(window: Any) -> List[str]:
    return [part.strip() for part in str(window or "").split("+") if part.strip()]


def event_phase_bias(event: Mapping[str, Any]) -> float:
    """Signed unit bias. Prefer 1h when that window actually fired.

    '1h' must not be a substring test on '24h'.
    """
    triggers = window_triggers(event.get("window"))
    pct_1h = event.get("pct_1h")
    pct_24h = event.get("pct_24h")
    if "1h" in triggers and pct_1h is not None:
        return clip_unit(float(pct_1h) / GAP_SCALE_1H)
    if "24h" in triggers and pct_24h is not None:
        return clip_unit(float(pct_24h) / GAP_SCALE_24H)
    if pct_1h is not None:
        return clip_unit(float(pct_1h) / GAP_SCALE_1H)
    if pct_24h is not None:
        return clip_unit(float(pct_24h) / GAP_SCALE_24H)
    return 0.0


def load_recent_events(
    jsonl_path: Path,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    asset_filter: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """JSONL rows inside the lookback window (UTC). Skips run_marker."""
    cutoff = (now or utc_now()) - timedelta(hours=lookback_hours)
    entries: List[Dict[str, Any]] = []
    if not jsonl_path.is_file():
        return entries
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("kind") == RUN_MARKER_KIND or record.get("source_type") == RUN_MARKER_KIND:
                continue
            ts = parse_ts(record.get("ts") or record.get("timestamp"))
            if ts is None or ts < cutoff:
                continue
            if asset_filter and str(record.get("asset") or "") != asset_filter:
                continue
            entries.append(record)
    return entries


def compute_coverage_scores(entries: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """Mean signed bias per asset from COVERAGE_GAP only. No untracked spray."""
    buckets: Dict[str, List[float]] = {}
    for entry in entries:
        if entry.get("kind") != COVERAGE_KIND:
            continue
        asset = str(entry.get("asset") or "").strip()
        if not asset:
            continue
        buckets.setdefault(asset, []).append(event_phase_bias(entry))
    result: Dict[str, float] = {}
    for asset, scores in buckets.items():
        result[asset] = sum(scores) / len(scores) if scores else 0.0
    if result:
        result["_overall"] = sum(result.values()) / len(result)
    return result


def build_phase_signal(
    asset: str,
    score: float,
    confidence: float = GAP_ASSET_CONFIDENCE,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    meta = {
        "asset": asset,
        "source": "gap_reports",
        "lookback_hours": lookback_hours,
        **(metadata or {}),
    }
    return {
        "timestamp": (now or utc_now()).isoformat(),
        "provider": GAP_PROVIDER_ID,
        "phase_bias": round(clip_unit(score), 4),
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "metadata": meta,
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
    }


def collect_signals(
    scores: Mapping[str, float],
    *,
    n_coverage: int,
    n_untracked: int,
    lookback_hours: float,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    compact = {k: round(float(v), 6) for k, v in scores.items()}
    extra = {
        "n_coverage": n_coverage,
        "n_untracked": n_untracked,
        "score_detail": compact,
        "scale_1h": GAP_SCALE_1H,
        "scale_24h": GAP_SCALE_24H,
    }
    signals: List[Dict[str, Any]] = []
    for asset, score in scores.items():
        if asset.startswith("_"):
            continue
        signals.append(
            build_phase_signal(
                asset,
                score,
                confidence=GAP_ASSET_CONFIDENCE,
                metadata=extra,
                lookback_hours=lookback_hours,
                now=now,
            )
        )
    if "_overall" in scores:
        signals.append(
            build_phase_signal(
                "OVERALL",
                scores["_overall"],
                confidence=GAP_OVERALL_CONFIDENCE,
                metadata=extra,
                lookback_hours=lookback_hours,
                now=now,
            )
        )
    return signals


def append_phase_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    source: Path,
) -> None:
    assert_handoff_output(source, path)
    assert_diagnostic_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")


def run_marker_record(result: Mapping[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    return {
        "kind": RUN_MARKER_KIND,
        "provider": GAP_PROVIDER_ID,
        "timestamp": (now or utc_now()).isoformat(),
        "n_entries": result.get("n_entries", 0),
        "n_coverage": result.get("n_coverage", 0),
        "n_untracked": result.get("n_untracked", 0),
        "n_signals": len(list(result.get("signals") or [])),
        "status": result.get("status"),
        "liveness_invariant": INVARIANT,
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
    }


def run_once(
    *,
    jsonl_path: Optional[Path] = None,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    asset: Optional[str] = None,
    now: Optional[datetime] = None,
    output_jsonl: Optional[Path] = None,
) -> Dict[str, Any]:
    path = jsonl_path or DEFAULT_GAP_JSONL_PATH
    entries = load_recent_events(path, lookback_hours, asset, now=now)
    coverage = [e for e in entries if e.get("kind") == COVERAGE_KIND]
    untracked = [e for e in entries if e.get("kind") == UNTRACKED_KIND]
    scores = compute_coverage_scores(coverage)
    signals = collect_signals(
        scores,
        n_coverage=len(coverage),
        n_untracked=len(untracked),
        lookback_hours=lookback_hours,
        now=now,
    )
    if asset:
        signals = [s for s in signals if s["metadata"]["asset"] == asset]
    payload = {
        "status": "ok" if coverage else "empty",
        "n_entries": len(entries),
        "n_coverage": len(coverage),
        "n_untracked": len(untracked),
        "scores": scores,
        "signals": signals,
        "order_send": False,
        "diagnostic_only": True,
    }
    if output_jsonl is not None:
        marker = run_marker_record(payload, now=now)
        append_phase_jsonl(output_jsonl, list(signals) + [marker], source=path)
        payload["path"] = str(output_jsonl)
        payload["run_marker"] = True
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="AstroCore PhaseSource: price coverage gap")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--jsonl-path", type=Path, default=DEFAULT_GAP_JSONL_PATH)
    parser.add_argument(
        "--output-json",
        "--output-jsonl",
        dest="output_jsonl",
        default=None,
        help="append PhaseSignals + run_marker as JSONL (does not overwrite)",
    )
    args = parser.parse_args()
    jsonl_path = args.jsonl_path
    if not jsonl_path.is_absolute():
        jsonl_path = _ROOT / jsonl_path
    out = Path(args.output_jsonl) if args.output_jsonl else None
    if out is not None and not out.is_absolute():
        out = _ROOT / out
    result = run_once(
        jsonl_path=jsonl_path,
        lookback_hours=args.lookback_hours,
        asset=args.asset,
        output_jsonl=out,
    )
    signals = result["signals"]
    if out is not None:
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "path": str(out),
                    "n_signals": len(signals),
                    "n_coverage": result["n_coverage"],
                    "run_marker": True,
                }
            )
        )
    else:
        print(json.dumps(signals, indent=2, ensure_ascii=False))
    print("coverage_scores lookback_h={:.1f}".format(args.lookback_hours), file=sys.stderr)
    for name, score in sorted(result["scores"].items()):
        print(f"  {name}: {score:.4f}", file=sys.stderr)
    if result["status"] == "empty":
        print("no COVERAGE_GAP in lookback window", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
