"""B8 — append-only sizing audit (separate from paper_trades WORM)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from prototypes.raas_paper_trading.position_sizing.types import (
    FORBIDDEN_EXPORT_KEYS,
    SCOPE,
    SIZING_SCHEMA,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SizingAuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = "0" * 64
        if self.path.is_file():
            lines = self.path.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                self._prev = str(last.get("hash") or self._prev)

    def append(self, event: Dict[str, Any]) -> Dict[str, Any]:
        leaked = FORBIDDEN_EXPORT_KEYS.intersection(event.keys())
        if leaked:
            raise RuntimeError(f"sizing_audit_forbidden_keys: {sorted(leaked)}")
        if event.get("live_execution") is True or event.get("order_send") is True:
            raise RuntimeError("sizing_audit: live_execution and order_send must be false")

        row = {
            **event,
            "schema": event.get("schema") or SIZING_SCHEMA,
            "action": event.get("action") or "SIZING_BOUNDARY",
            "ts": event.get("ts") or _now(),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
            "diagnostic_only": True,
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
