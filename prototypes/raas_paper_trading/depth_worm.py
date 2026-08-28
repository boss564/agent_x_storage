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


def iter_depth_rows(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = depth_worm_path(path)
    if not p.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def latest_depth_row(
    symbol: str,
    *,
    fill_ts: Optional[str] = None,
    path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Latest DEPTH_SNAPSHOT for symbol with ts <= fill_ts (or latest if fill_ts empty)."""
    sym = symbol.upper()
    candidates: List[Dict[str, Any]] = []
    for row in iter_depth_rows(path):
        if row.get("action") != "DEPTH_SNAPSHOT":
            continue
        if str(row.get("symbol", "")).upper() != sym:
            continue
        candidates.append(row)
    if not candidates:
        return None
    if not fill_ts:
        return candidates[-1]
    fill_dt = _parse_iso(fill_ts)
    best: Optional[Dict[str, Any]] = None
    best_ts = None
    for row in candidates:
        row_ts = _parse_iso(str(row["ts"]))
        if row_ts <= fill_dt and (best_ts is None or row_ts > best_ts):
            best = row
            best_ts = row_ts
    return best if best is not None else candidates[-1]


def _parse_iso(ts: str) -> datetime:
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
