"""Append-only paper WORM log — order_send forbidden on every line."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_root() -> Path:
    return Path(os.environ.get("RAAS_DATA_ROOT", "data/raas"))


class PaperWormLog:
    def __init__(self, tenant_id: str, run_id: str, *, data_root: Optional[Path] = None) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id
        root = data_root if data_root is not None else _data_root()
        self.path = root / tenant_id / "paper" / "runs" / run_id / "paper_trades.worm.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = "0" * 64
        if self.path.is_file():
            from prototypes.raas_paper_trading.worm_io import last_jsonl_row

            last = last_jsonl_row(self.path)
            if last:
                self._prev = str(last.get("hash") or self._prev)

    def append(self, event: Dict[str, Any]) -> Dict[str, Any]:
        if event.get("action") == "ORDER_SENT":
            raise RuntimeError("order_send_forbidden: ORDER_SENT not allowed in paper WORM")
        if event.get("live_execution", False) is True:
            raise RuntimeError("live_execution must be false on every paper WORM line")
        row = {
            **event,
            "ts": event.get("ts") or _now(),
            "tenant_id": self.tenant_id,
            "run_id": self.run_id,
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
            "scope": SCOPE,
            "prev_hash": self._prev,
        }
        # strip any accidental send flags
        row.pop("order_id", None)
        payload = json.dumps(row, sort_keys=True, default=str)
        digest = hashlib.sha256((self._prev + payload).encode("utf-8")).hexdigest()
        row["hash"] = digest
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._prev = digest
        return row
