"""Entity-gap detector — unknown tickers/names in recent JSONL.

Phase 1: catalog coverage only. Price-anomaly detection is deferred.
Does not send orders or touch the cluster.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.news.config import (
    BRIDGE_KEYWORDS,
    CHAIN_KEYWORDS,
    GENERAL_KEYWORDS,
    MACRO_KEYWORDS,
    PERSON_KEYWORDS,
    PROTOCOL_KEYWORDS,
    TOKEN_KEYWORDS,
)

DEFAULT_JSONL = "data/news_scores.jsonl"
DEFAULT_OUTPUT = "exports/reports/gap_analysis.json"
DEFAULT_MD = "exports/reports/gap_analysis.md"
DEFAULT_LAST_N = 100
# User spec: report candidates with more than 3 mentions.
DEFAULT_MIN_COUNT = 4

QUOTED = re.compile(r'["“”\']([^"“”\']{2,40})["“”\']')
TICKER = re.compile(r"\b[A-Z]{2,6}\b")
PROPER = re.compile(r"\b[A-Z][a-z]{2,29}\b")

STOPWORDS = {
    "the",
    "this",
    "that",
    "with",
    "from",
    "after",
    "before",
    "over",
    "under",
    "into",
    "will",
    "would",
    "could",
    "should",
    "about",
    "into",
    "news",
    "update",
    "report",
    "says",
    "said",
    "new",
    "first",
    "week",
    "month",
    "year",
    "today",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "coindesk",
    "cointelegraph",
    "binance",
    "exchange",
    "market",
    "crypto",
    "blockchain",
    "token",
    "network",
    "protocol",
    "bridge",
    "layer",
    "mainnet",
    "testnet",
    "usd",
    "usa",
    "ceo",
    "etf",
    "sec",
    "fed",
    "http",
    "https",
    "www",
    "com",
    "html",
    "json",
    "rss",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def known_surface() -> Set[str]:
    """Lowercase ids and phrases from every keyword catalog."""
    found: Set[str] = {"macro", "general"}
    catalogs: Sequence[Mapping[str, Tuple[str, ...]]] = (
        TOKEN_KEYWORDS,
        CHAIN_KEYWORDS,
        BRIDGE_KEYWORDS,
        PROTOCOL_KEYWORDS,
        PERSON_KEYWORDS,
    )
    for catalog in catalogs:
        for key, phrases in catalog.items():
            found.add(str(key).lower())
            for phrase in phrases:
                found.add(phrase.lower())
                for part in phrase.split():
                    found.add(part.lower())
    for extra in MACRO_KEYWORDS + GENERAL_KEYWORDS:
        found.add(extra.lower())
        for part in extra.split():
            found.add(part.lower())
    return found


def is_known(token: str, known: Set[str]) -> bool:
    return token.lower() in known


def extract_candidates(text: str) -> List[str]:
    """Quoted spans, ALLCAPS tickers, Titlecase names — not stopwords."""
    if not text:
        return []
    out: List[str] = []
    for match in QUOTED.finditer(text):
        span = match.group(1).strip()
        if span:
            out.append(span)
            out.extend(TICKER.findall(span))
            out.extend(PROPER.findall(span))
    out.extend(TICKER.findall(text))
    out.extend(PROPER.findall(text))
    return out


def load_articles(path: Path, *, last_n: int) -> List[dict]:
    rows: List[dict] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("source_type") == "run_marker":
                continue
            rows.append(row)
    if last_n > 0:
        return rows[-last_n:]
    return rows


def article_text(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "summary", "source_name")
        if row.get(key)
    )


def suggest(entity: str) -> str:
    if re.fullmatch(r"[A-Z]{2,6}", entity):
        return f"Add {entity} to TOKEN_KEYWORDS or monitor if it's a new asset."
    lower = entity.lower()
    if lower not in {k.lower() for k in CHAIN_KEYWORDS}:
        return (
            f"Add {entity} to CHAIN_KEYWORDS, PROTOCOL_KEYWORDS, or PERSON_KEYWORDS "
            "as appropriate."
        )
    return f"Monitor {entity} — not in keyword catalogs."


def detect_gaps(
    articles: Iterable[Mapping[str, Any]],
    *,
    min_count: int = DEFAULT_MIN_COUNT,
    known: Optional[Set[str]] = None,
) -> List[dict]:
    known = known if known is not None else known_surface()
    counts: Dict[str, int] = defaultdict(int)
    contexts: Dict[str, List[str]] = defaultdict(list)
    seen_ctx: Dict[str, Set[str]] = defaultdict(set)
    for row in articles:
        title = str(row.get("title") or "")
        blob = article_text(row)
        for raw in extract_candidates(blob):
            token = raw.strip()
            if not token or is_known(token, known):
                continue
            if token.lower() in STOPWORDS:
                continue
            if token.isdigit():
                continue
            key = token.upper() if re.fullmatch(r"[A-Z]{2,6}", token) else token
            if is_known(key, known):
                continue
            counts[key] += 1
            snippet = title.strip() or blob[:80]
            if snippet and snippet not in seen_ctx[key]:
                seen_ctx[key].add(snippet)
                if len(contexts[key]) < 5:
                    contexts[key].append(snippet)
    gaps = []
    for entity, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < min_count:
            continue
        gaps.append(
            {
                "entity": entity,
                "count": count,
                "context": contexts[entity],
                "suggestion": suggest(entity),
            }
        )
    return gaps


def build_report(
    articles: Sequence[Mapping[str, Any]],
    *,
    min_count: int = DEFAULT_MIN_COUNT,
    scanned: Optional[int] = None,
) -> dict:
    gaps = detect_gaps(articles, min_count=min_count)
    return {
        "timestamp": utc_now(),
        "scanned_articles": scanned if scanned is not None else len(list(articles)),
        "min_count": min_count,
        "price_anomaly": None,
        "price_anomaly_note": "deferred until a price feed is wired",
        "detected_gaps": gaps,
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# News-Agent gap analysis",
        "",
        f"- timestamp: `{report.get('timestamp')}`",
        f"- scanned_articles: {report.get('scanned_articles')}",
        f"- min_count: {report.get('min_count')}",
        f"- price_anomaly: {report.get('price_anomaly_note')}",
        "",
        "## detected_gaps",
        "",
    ]
    gaps = list(report.get("detected_gaps") or [])
    if not gaps:
        lines.append("None above threshold.")
        return "\n".join(lines) + "\n"
    for gap in gaps:
        lines.append(f"### {gap.get('entity')} ({gap.get('count')})")
        lines.append(f"- suggestion: {gap.get('suggestion')}")
        for ctx in gap.get("context") or []:
            lines.append(f"- context: {ctx}")
        lines.append("")
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], json_path: Path, *, md_path: Optional[Path] = None) -> dict:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if md_path is not None:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "status": "ok",
        "path": str(json_path),
        "md": None if md_path is None else str(md_path),
        "gaps": len(list(report.get("detected_gaps") or [])),
        "order_send": False,
    }


def run_gap_report(
    *,
    jsonl: Optional[Path] = None,
    output: Optional[Path] = None,
    md: Optional[Path] = None,
    last_n: int = DEFAULT_LAST_N,
    min_count: int = DEFAULT_MIN_COUNT,
) -> dict:
    jsonl_path = jsonl or Path(os.environ.get("NEWS_AGENT_MULTI_JSONL", DEFAULT_JSONL))
    articles = load_articles(jsonl_path, last_n=last_n)
    report = build_report(articles, min_count=min_count, scanned=len(articles))
    out = output or Path(DEFAULT_OUTPUT)
    md_path = md
    return {**write_report(report, out, md_path=md_path), "report": report}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="News-Agent entity gap detector (diagnostic_only)")
    parser.add_argument("--jsonl", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--md", default=None, help="optional markdown path")
    parser.add_argument("--last", type=int, default=DEFAULT_LAST_N)
    parser.add_argument("--min-count", type=int, default=DEFAULT_MIN_COUNT)
    args = parser.parse_args()
    md_path = Path(args.md) if args.md else None
    result = run_gap_report(
        jsonl=Path(args.jsonl) if args.jsonl else None,
        output=Path(args.output),
        md=md_path,
        last_n=args.last,
        min_count=args.min_count,
    )
    printable = {k: v for k, v in result.items() if k != "report"}
    print(json.dumps(printable, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
