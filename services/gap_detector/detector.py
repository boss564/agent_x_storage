"""Price-anomaly & coverage-gap detector.

Rule A: |Δ1h| > 5% or |Δ24h| > 8% and zero matching news in that window
        → COVERAGE_GAP
Rule B: $TICKER cashtags not on WATCHLIST → UNTRACKED_ENTITY

ccxt Binance public endpoints only (no API key). Network failures
are logged per asset; they do not abort the run.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents_b2g.news.config import TOKEN_KEYWORDS
from services.news_agent.liveness import INVARIANT

LOGGER = logging.getLogger("gap_detector")

WATCHLIST: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "AVAX",
    "LINK",
    "SUI",
    "DOGE",
    "PEPE",
)
WATCH_SET = frozenset(WATCHLIST)

THRESHOLD_1H_PCT = 5.0
THRESHOLD_24H_PCT = 8.0
QUOTE = "USDT"
CASHTAG = re.compile(r"\$([A-Z]{2,10})\b")
SCHEMA = "swarm_gap/v1"
RUN_MARKER_KIND = "run_marker"
DEFAULT_NEWS = "data/news_scores.jsonl"
DEFAULT_EVENTS = "data/gap_reports.jsonl"
DEFAULT_MD = "docs/SWARM_GAP_ANALYSIS.md"

PriceFetcher = Callable[[str], Dict[str, Any]]


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


def pct_change(old: float, new: float) -> Optional[float]:
    if old is None or new is None or old == 0:
        return None
    return round((new - old) / old * 100.0, 4)


def public_binance():
    try:
        import ccxt  # type: ignore
    except ImportError:
        return None
    return ccxt.binance({"enableRateLimit": True, "timeout": 15000})


def fetch_price_move(asset: str, *, client=None) -> Dict[str, Any]:
    """1h from OHLCV, 24h from ticker.percentage. Never raises."""
    symbol = f"{asset}/{QUOTE}"
    out: Dict[str, Any] = {
        "asset": asset,
        "symbol": symbol,
        "pct_1h": None,
        "pct_24h": None,
        "last": None,
        "error": None,
    }
    exchange = client
    if exchange is None:
        exchange = public_binance()
    if exchange is None:
        out["error"] = "ccxt_not_installed"
        LOGGER.warning("ccxt not installed — skip price fetch for %s", asset)
        return out
    try:
        ticker = exchange.fetch_ticker(symbol)
        last = ticker.get("last")
        out["last"] = last
        pct24 = ticker.get("percentage")
        if pct24 is not None:
            out["pct_24h"] = round(float(pct24), 4)
    except Exception as exc:
        out["error"] = f"ticker:{type(exc).__name__}: {exc}"
        LOGGER.warning("price ticker failed %s: %s", symbol, exc)
        return out
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=3)
        if candles and len(candles) >= 2:
            prev_close = float(candles[-2][4])
            last_close = float(candles[-1][4])
            out["pct_1h"] = pct_change(prev_close, last_close)
    except Exception as exc:
        LOGGER.warning("ohlcv 1h failed %s: %s", symbol, exc)
        if not out["error"]:
            out["error"] = f"ohlcv:{type(exc).__name__}: {exc}"
    return out


def fetch_watchlist_prices(
    assets: Sequence[str] = WATCHLIST,
    *,
    client=None,
) -> List[Dict[str, Any]]:
    return [fetch_price_move(asset, client=client) for asset in assets]


def load_news(path: Path) -> List[dict]:
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
    return rows


def news_blob(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(row.get(k) or "")
        for k in ("title", "summary", "source_name")
    )


def row_assets(row: Mapping[str, Any]) -> Set[str]:
    found: Set[str] = set()
    for key in ("target_assets", "assets", "symbols"):
        for item in row.get(key) or []:
            token = str(item).upper()
            if token in ("MACRO", "GENERAL"):
                continue
            found.add(token)
    blob = news_blob(row).lower()
    for ticker, phrases in TOKEN_KEYWORDS.items():
        if ticker in found:
            continue
        if any(p.lower() in blob for p in phrases if len(p) > 3):
            found.add(ticker)
            continue
        if any(
            re.search(rf"\b{re.escape(p.lower())}\b", blob)
            for p in phrases
            if len(p) <= 3
        ):
            found.add(ticker)
    return found


def news_in_window(
    rows: Iterable[Mapping[str, Any]],
    asset: str,
    *,
    since: datetime,
    until: Optional[datetime] = None,
) -> List[dict]:
    end = until or utc_now()
    hits: List[dict] = []
    want = asset.upper()
    for row in rows:
        ts = parse_ts(row.get("timestamp") or row.get("ts"))
        if ts is None or ts < since or ts > end:
            continue
        if want in row_assets(row):
            hits.append(dict(row))
    return hits


def rule_a_coverage_gaps(
    prices: Sequence[Mapping[str, Any]],
    news: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> List[dict]:
    now = now or utc_now()
    events: List[dict] = []
    for move in prices:
        asset = str(move.get("asset") or "")
        if not asset or move.get("error") and move.get("pct_1h") is None and move.get("pct_24h") is None:
            if move.get("error"):
                events.append(
                    {
                        "kind": "PRICE_FEED_ERROR",
                        "asset": asset,
                        "error": move.get("error"),
                        "recommendation": (
                            f"Preisfeed für {asset}/USDT fehlgeschlagen "
                            f"({move.get('error')}) — Lauf fortgesetzt, kein Abbruch."
                        ),
                    }
                )
            continue
        pct_1h = move.get("pct_1h")
        pct_24h = move.get("pct_24h")
        triggers: List[str] = []
        if pct_1h is not None and abs(float(pct_1h)) > THRESHOLD_1H_PCT:
            hits = news_in_window(news, asset, since=now - timedelta(hours=1), until=now)
            if not hits:
                triggers.append("1h")
        if pct_24h is not None and abs(float(pct_24h)) > THRESHOLD_24H_PCT:
            hits = news_in_window(news, asset, since=now - timedelta(hours=24), until=now)
            if not hits:
                triggers.append("24h")
        if not triggers:
            continue
        window = "+".join(triggers)
        events.append(
            {
                "kind": "COVERAGE_GAP",
                "asset": asset,
                "pct_1h": move.get("pct_1h"),
                "pct_24h": move.get("pct_24h"),
                "last": move.get("last"),
                "window": window,
                "news_hits": 0,
                "recommendation": (
                    f"News-Abdeckung für {asset} fehlt trotz Bewegung "
                    f"(1h={move.get('pct_1h')}%, 24h={move.get('pct_24h')}%, Fenster {window}). "
                    "Keywords/Scraper prüfen oder Feed-Quellen erweitern."
                ),
            }
        )
    return events


def extract_cashtags(text: str) -> List[str]:
    return CASHTAG.findall(text or "")


def rule_b_untracked(news: Sequence[Mapping[str, Any]]) -> List[dict]:
    counts: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    for row in news:
        title = str(row.get("title") or "")
        blob = news_blob(row)
        for tag in extract_cashtags(blob):
            if tag in WATCH_SET:
                continue
            counts[tag] = counts.get(tag, 0) + 1
            bucket = samples.setdefault(tag, [])
            if title and title not in bucket and len(bucket) < 5:
                bucket.append(title)
    events: List[dict] = []
    for ticker, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        events.append(
            {
                "kind": "UNTRACKED_ENTITY",
                "asset": ticker,
                "count": count,
                "context": samples[ticker],
                "recommendation": (
                    f"Aufnahme von ${ticker} in die Preisbeobachtung empfohlen "
                    f"(WATCHLIST: {', '.join(WATCHLIST)})."
                ),
            }
        )
    return events


def repo_file(relative: str) -> Path:
    p = Path(relative)
    return p if p.is_absolute() else _ROOT / p


def load_run_markers(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("kind") == RUN_MARKER_KIND:
            rows.append(row)
    return rows


def last_run_marker(path: Path) -> Optional[dict]:
    rows = load_run_markers(path)
    return rows[-1] if rows else None


def stamp_event(kind_row: Mapping[str, Any], *, ts: Optional[datetime] = None) -> dict:
    row = {
        "schema": SCHEMA,
        "ts": (ts or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diagnostic_only": True,
        "live_execution": False,
        "order_send": False,
        "not_investment_advice": True,
        **dict(kind_row),
    }
    return row


def append_events(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, default=str) + "\n")


def render_markdown(events: Sequence[Mapping[str, Any]], *, prices: Sequence[Mapping[str, Any]], now: datetime) -> str:
    coverage = [e for e in events if e.get("kind") == "COVERAGE_GAP"]
    untracked = [e for e in events if e.get("kind") == "UNTRACKED_ENTITY"]
    errors = [e for e in events if e.get("kind") == "PRICE_FEED_ERROR"]
    lines = [
        "# Swarm gap analysis",
        "",
        f"- generated: `{now.strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- watchlist: {', '.join(WATCHLIST)}",
        f"- rule A: |Δ1h| > {THRESHOLD_1H_PCT}% or |Δ24h| > {THRESHOLD_24H_PCT}% and 0 matching news",
        "- rule B: `$TICKER` cashtags not on the price watchlist",
        "- source: public Binance via ccxt (no API key); news: `data/news_scores.jsonl`",
        "- diagnostic_only · live_execution=false · order_send=false",
        "- liveness: `kind=run_marker` every run (instance 4) — missing marker ≠ no gaps",
        "",
        "## Price snapshot",
        "",
        "| asset | Δ1h % | Δ24h % | last | error |",
        "|-------|-------|--------|------|-------|",
    ]
    for move in prices:
        lines.append(
            "| {asset} | {p1} | {p24} | {last} | {err} |".format(
                asset=move.get("asset"),
                p1=move.get("pct_1h") if move.get("pct_1h") is not None else "—",
                p24=move.get("pct_24h") if move.get("pct_24h") is not None else "—",
                last=move.get("last") if move.get("last") is not None else "—",
                err=move.get("error") or "",
            )
        )
    lines.extend(["", "## Rule A — COVERAGE_GAP", ""])
    if not coverage:
        lines.append("Keine Preis-Anomalie ohne News in diesem Lauf.")
    else:
        for event in coverage:
            lines.append(f"- **{event.get('asset')}** ({event.get('window')}): {event.get('recommendation')}")
    lines.extend(["", "## Rule B — UNTRACKED_ENTITY", ""])
    if not untracked:
        lines.append("Keine fremden `$TICKER`-Cashtags außerhalb der Watchlist.")
    else:
        for event in untracked:
            lines.append(f"- **${event.get('asset')}** (n={event.get('count')}): {event.get('recommendation')}")
    if errors:
        lines.extend(["", "## Price feed errors (non-fatal)", ""])
        for event in errors:
            lines.append(f"- {event.get('asset')}: {event.get('error')}")
    lines.extend(["", "## System recommendations", ""])
    recs = [
        e.get("recommendation")
        for e in events
        if e.get("recommendation") and e.get("kind") not in (RUN_MARKER_KIND, "RUN_SUMMARY")
    ]
    if not recs:
        lines.append("Keine Handlungsempfehlung — Watchlist und News-Abdeckung sind in diesem Fenster konsistent.")
    else:
        for rec in recs:
            lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_once(
    *,
    news_path: Optional[Path] = None,
    events_path: Optional[Path] = None,
    md_path: Optional[Path] = None,
    client=None,
    now: Optional[datetime] = None,
) -> dict:
    now = now or utc_now()
    news_file = news_path or repo_file(os.environ.get("NEWS_AGENT_MULTI_JSONL", DEFAULT_NEWS))
    events_file = events_path or repo_file(DEFAULT_EVENTS)
    md_file = md_path or repo_file(DEFAULT_MD)
    news = load_news(news_file)
    prices = fetch_watchlist_prices(client=client)
    events = rule_a_coverage_gaps(prices, news, now=now) + rule_b_untracked(news)
    stamped = [stamp_event(e, ts=now) for e in events]
    marker = stamp_event(
        {
            "kind": RUN_MARKER_KIND,
            "liveness_invariant": INVARIANT,
            "news_rows": len(news),
            "assets_priced": sum(
                1 for p in prices if p.get("pct_24h") is not None or p.get("pct_1h") is not None
            ),
            "coverage_gaps": sum(1 for e in stamped if e.get("kind") == "COVERAGE_GAP"),
            "untracked": sum(1 for e in stamped if e.get("kind") == "UNTRACKED_ENTITY"),
            "feed_errors": sum(1 for e in stamped if e.get("kind") == "PRICE_FEED_ERROR"),
            "recommendation": "Siehe docs/SWARM_GAP_ANALYSIS.md",
        },
        ts=now,
    )
    stamped.append(marker)
    append_events(events_file, stamped)
    write_markdown(md_file, render_markdown(stamped, prices=prices, now=now))
    return {
        "status": "ok",
        "events_path": str(events_file),
        "md_path": str(md_file),
        "news_rows": len(news),
        "coverage_gaps": marker["coverage_gaps"],
        "untracked": marker["untracked"],
        "feed_errors": marker["feed_errors"],
        "events": stamped,
        "prices": prices,
        "order_send": False,
        "diagnostic_only": True,
    }
