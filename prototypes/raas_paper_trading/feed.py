"""Read-only market ticks for paper trading — never order endpoints."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, List, Optional, Sequence


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
