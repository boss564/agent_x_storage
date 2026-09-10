"""AstroCore PhaseSource: news sentiment (v1).

Reads data/news_scores.jsonl (multi-scraper or isolated agent), aggregates
weighted sentiment per asset, returns PhaseSignal dicts.

Diagnostic only. Does not send orders or touch the cluster.

Usage:
    python3 -m astrocore.sources.news_sentiment_source --lookback-hours 24
    python3 -m astrocore.sources.news_sentiment_source --asset BTC --lookback-hours 6
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
    ASSET_CONFIDENCE,
    ASSET_WEIGHT,
    DEFAULT_JSONL_PATH,
    DEFAULT_LOOKBACK_HOURS,
    GENERAL_WEIGHT,
    MACRO_WEIGHT,
    OVERALL_CONFIDENCE,
    PROVIDER_ID,
    UNKNOWN_ASSET_WEIGHT,
)
from services.news_agent.liveness import INVARIANT

SKIP_SOURCE_TYPES = frozenset({"run_marker"})
SKIP_ASSET_TAGS = frozenset({"MACRO", "GENERAL"})
RUN_MARKER_KIND = "run_marker"
DEFAULT_PHASE_JSONL = _ROOT / "data" / "phase_signals" / "news_sentiment.jsonl"


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


def row_assets(record: Mapping[str, Any]) -> List[str]:
    raw = record.get("assets")
    if not raw:
        raw = record.get("target_assets") or []
    return [str(a) for a in raw if a]


def row_sentiment(record: Mapping[str, Any]) -> float:
    if record.get("sentiment_score") is not None:
        try:
            return clip_unit(float(record["sentiment_score"]))
        except (TypeError, ValueError):
            pass
    if record.get("sentiment") is not None:
        try:
            return clip_unit(float(record["sentiment"]))
        except (TypeError, ValueError):
            pass
    return 0.0


def load_recent_entries(
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
            if record.get("source_type") in SKIP_SOURCE_TYPES or record.get("kind") == RUN_MARKER_KIND:
                continue
            ts = parse_ts(record.get("timestamp") or record.get("ts"))
            if ts is None or ts < cutoff:
                continue
            assets = row_assets(record)
            if asset_filter and asset_filter not in assets:
                continue
            entries.append(record)
    return entries


def compute_aggregated_sentiment(
    entries: Sequence[Mapping[str, Any]],
    asset_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Weighted mean sentiment per ticker plus _macro / _general / _overall.

    MACRO is not sprayed onto every watchlist ticker. A row tagged MACRO
    plus specific assets (e.g. BTC+MACRO) scores those tickers and _macro.
    MACRO-only rows only fill _macro.
    """
    weights = asset_weights if asset_weights is not None else ASSET_WEIGHT
    asset_scores: Dict[str, List[float]] = {}
    macro_scores: List[float] = []
    general_scores: List[float] = []

    for entry in entries:
        sentiment = row_sentiment(entry)
        assets = row_assets(entry)
        tickers = [a for a in assets if a not in SKIP_ASSET_TAGS]
        has_macro = "MACRO" in assets
        has_general = "GENERAL" in assets

        if has_macro:
            macro_scores.append(sentiment * MACRO_WEIGHT)
        if has_general and not tickers:
            general_scores.append(sentiment * GENERAL_WEIGHT)

        if tickers:
            for asset in tickers:
                weight = weights.get(asset, UNKNOWN_ASSET_WEIGHT)
                asset_scores.setdefault(asset, []).append(sentiment * weight)
        elif has_macro or has_general:
            continue

    result: Dict[str, float] = {}
    for asset, scores in asset_scores.items():
        result[asset] = sum(scores) / len(scores) if scores else 0.0
    if macro_scores:
        result["_macro"] = sum(macro_scores) / len(macro_scores)
    if general_scores:
        result["_general"] = sum(general_scores) / len(general_scores)
    all_scores = [v for k, v in result.items() if not k.startswith("_")]
    if all_scores:
        result["_overall"] = sum(all_scores) / len(all_scores)
    return result


def build_phase_signal(
    asset: str,
    score: float,
    confidence: float = ASSET_CONFIDENCE,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Standard AstroCore PhaseSignal dict. diagnostic_only."""
    meta = {
        "asset": asset,
        "source": "news_scores",
        "lookback_hours": lookback_hours,
        **(metadata or {}),
    }
    return {
        "timestamp": (now or utc_now()).isoformat(),
        "provider": PROVIDER_ID,
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
    n_entries: int,
    lookback_hours: float,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    compact = {k: round(float(v), 6) for k, v in scores.items()}
    signals: List[Dict[str, Any]] = []
    for asset, score in scores.items():
        if asset.startswith("_"):
            continue
        signals.append(
            build_phase_signal(
                asset,
                score,
                confidence=ASSET_CONFIDENCE,
                metadata={"n_entries": n_entries, "score_detail": compact},
                lookback_hours=lookback_hours,
                now=now,
            )
        )
    if "_overall" in scores:
        signals.append(
            build_phase_signal(
                "OVERALL",
                scores["_overall"],
                confidence=OVERALL_CONFIDENCE,
                metadata={"n_entries": n_entries, "score_detail": compact},
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
        "provider": PROVIDER_ID,
        "timestamp": (now or utc_now()).isoformat(),
        "n_entries": result.get("n_entries", 0),
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
    path = jsonl_path or DEFAULT_JSONL_PATH
    entries = load_recent_entries(
        path, lookback_hours, asset, now=now
    )
    scores = compute_aggregated_sentiment(entries)
    signals = collect_signals(
        scores,
        n_entries=len(entries),
        lookback_hours=lookback_hours,
        now=now,
    )
    if asset:
        signals = [s for s in signals if s["metadata"]["asset"] == asset]
    payload = {
        "status": "ok" if entries else "empty",
        "n_entries": len(entries),
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
    parser = argparse.ArgumentParser(description="AstroCore PhaseSource: news sentiment")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--jsonl-path", type=Path, default=DEFAULT_JSONL_PATH)
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
                    "run_marker": True,
                }
            )
        )
    else:
        print(json.dumps(signals, indent=2, ensure_ascii=False))
    print("aggregated_scores lookback_h={:.1f}".format(args.lookback_hours), file=sys.stderr)
    for name, score in sorted(result["scores"].items()):
        print(f"  {name}: {score:.4f}", file=sys.stderr)
    if result["status"] == "empty":
        print("no entries in lookback window", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
