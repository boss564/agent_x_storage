"""Read-only market ticks for paper trading — never order endpoints."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union

from prototypes.raas_paper_trading.slippage import OrderBook

Level = Tuple[Union[float, str], Union[float, str]]


@dataclass(frozen=True)
class PaperTick:
    symbol: str
    ts: str
    price: float
    source: str  # binance_rest | replay | pyth_stub

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "price": self.price,
            "source": self.source,
        }


class ReplayFeed:
    """Deterministic tick source for tests and offline paper runs."""

    def __init__(self, ticks: Sequence[PaperTick]) -> None:
        self._ticks = list(ticks)

    def __iter__(self) -> Iterator[PaperTick]:
        yield from self._ticks

    def __len__(self) -> int:
        return len(self._ticks)


def fetch_binance_rest_sample(
    symbol: str = "ETHUSDT",
    *,
    limit: int = 20,
    timeout_s: float = 10.0,
) -> List[PaperTick]:
    """Read-only public klines — no API key, no order path.

    Used for optional live smoke; CI uses ReplayFeed.
    """
    url = (
        f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}"
        f"&interval=1m&limit={int(limit)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "agent-x-paper/0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    out: List[PaperTick] = []
    for row in rows:
        # [open_time, open, high, low, close, ...]
        open_ms = int(row[0])
        close = float(row[4])
        ts = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc).isoformat()
        out.append(PaperTick(symbol=symbol.upper(), ts=ts, price=close, source="binance_rest"))
    return out


def assert_no_order_urls(url: str) -> None:
    """Fail-closed guard for any future feed wiring."""
    banned = ("/order", "/order/test", "orderId", "newOrder")
    low = url.lower()
    for b in banned:
        if b.lower() in low:
            raise RuntimeError(f"order_send_forbidden: refused URL containing {b!r}")


def parse_orderbook_snapshot(raw: object) -> OrderBook:
    """Normalize WORM/API depth into bids/asks float tuples."""
    if not isinstance(raw, dict):
        raise ValueError("orderbook_snapshot must be a dict")
    out: OrderBook = {"bids": [], "asks": []}
    for side in ("bids", "asks"):
        for item in raw.get(side) or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            price, qty = float(item[0]), float(item[1])
            if price > 0 and qty > 0:
                out[side].append((price, qty))
    if not out["bids"] or not out["asks"]:
        raise ValueError("orderbook_snapshot needs non-empty bids and asks")
    return out


def orderbook_to_snapshot(book: OrderBook) -> Dict[str, List[List[str]]]:
    """JSON-serializable depth for WORM lines."""
    return {
        "bids": [[str(p), str(q)] for p, q in book.get("bids") or []],
        "asks": [[str(p), str(q)] for p, q in book.get("asks") or []],
    }


def fetch_binance_ticker(
    symbol: str,
    *,
    timeout_s: float = 10.0,
) -> PaperTick:
    """Read-only last price — no API key, no order path."""
    sym = symbol.upper()
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
    assert_no_order_urls(url)
    req = urllib.request.Request(url, headers={"User-Agent": "agent-x-paper/0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    price = float(raw["price"])
    ts = datetime.now(timezone.utc).isoformat()
    return PaperTick(symbol=sym, ts=ts, price=price, source="binance_rest_ticker")


def fetch_binance_depth(
    symbol: str,
    *,
    limit: int = 10,
    timeout_s: float = 10.0,
) -> OrderBook:
    """Read-only public depth — no API key, no order path (Paket 2 / Phase B)."""
    sym = symbol.upper()
    url = f"https://api.binance.com/api/v3/depth?symbol={sym}&limit={int(limit)}"
    assert_no_order_urls(url)
    req = urllib.request.Request(url, headers={"User-Agent": "agent-x-paper/0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return parse_orderbook_snapshot(raw)
