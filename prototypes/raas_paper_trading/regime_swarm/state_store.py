"""Persistent swarm runtime state (cooling counters snapshot + soft-adapt multipliers)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SwarmStateStore:
    """JSON snapshot for cold-start recovery across container restarts."""

    path: Path
    soft_multipliers: Dict[str, float] = field(default_factory=dict)
    unreliable_started_at: Dict[str, Optional[str]] = field(default_factory=dict)

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.soft_multipliers = {
            str(k): float(v) for k, v in (data.get("soft_multipliers") or {}).items()
        }
        self.unreliable_started_at = {
            str(k): v for k, v in (data.get("unreliable_started_at") or {}).items()
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "raas_swarm_state_v1",
            "updated_at": _now(),
            "soft_multipliers": self.soft_multipliers,
            "unreliable_started_at": self.unreliable_started_at,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def apply_soft_state(self, soft: Any) -> None:
        for sym, mult in self.soft_multipliers.items():
            soft._current[sym] = mult

    def capture_soft_state(self, soft: Any) -> None:
        self.soft_multipliers = dict(soft._current)

    def apply_stuck_state(self, tracker: Any) -> None:
        for sym, iso in self.unreliable_started_at.items():
            if not iso:
                tracker._start[sym] = None
                continue
            try:
                tracker._start[sym] = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except ValueError:
                tracker._start[sym] = None

    def capture_stuck_state(self, tracker: Any) -> None:
        out: Dict[str, Optional[str]] = {}
        for sym, dt in tracker._start.items():
            out[sym] = dt.isoformat() if dt is not None else None
        self.unreliable_started_at = out
