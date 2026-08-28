"""Append-only depth snapshot WORM — read-only market data, no order send."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from prototypes.raas_paper_trading.feed import OrderBook, orderbook_to_snapshot

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
DEFAULT_DEPTH_WORM = Path("logs/worm/depth_snapshots.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def depth_worm_path(explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("RAAS_DEPTH_WORM_PATH")
    if env:
        return Path(env)
    return DEFAULT_DEPTH_WORM


class DepthWormLog:
    """Global depth snapshot log (Phase B — passive observation)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = depth_worm_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = "0" * 64
        if self.path.is_file():
            lines = self.path.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                self._prev = str(last.get("hash") or self._prev)

    def append_snapshot(
        self,
        *,
        symbol: str,
        orderbook: OrderBook,
        source: str = "binance_rest_depth",
        ts: Optional[str] = None,
    ) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "action": "DEPTH_SNAPSHOT",
            "ts": ts or _now(),
            "symbol": symbol.upper(),
            "source": source,
            "orderbook_snapshot": orderbook_to_snapshot(orderbook),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
            "scope": SCOPE,
            "prev_hash": self._prev,
        }
        payload = json.dumps(row, sort_keys=True, default=str)
        digest = hashlib.sha256((self._prev + payload).encode("utf-8")).hexdigest()
        row["hash"] = digest
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._prev = digest
        return row
