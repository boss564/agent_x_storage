"""Freeze Wave 38 live capture window before any RPC capture (§5).

Must run before Agents 1–5 touch the network. Window is never adjusted
post-hoc to fit observed data.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.live_prereg import load_wave38_thresholds
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ensure_live_directory,
)

# Bridge sealed window (docs/WAVE38_LIVE_PREREG.md §5) — must not be byte-identical
BRIDGE_WINDOW_START_UTC = datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
BRIDGE_WINDOW_END_UTC = datetime(2026, 8, 17, 23, 59, 59, tzinfo=timezone.utc)

WINDOW_FILENAME = "live_window.json"
MINUTES_PER_DAY = 24 * 60
ROLLING_DAYS = 90


@dataclass(frozen=True)
class FrozenLiveWindow:
    """Immutable live window — written once under wave38/live/."""

    t0_utc: str
    window_start_utc: str
    window_end_utc: str
    window_start_ts: int
    window_end_ts: int
    n_bins: int
    rolling_days: int
    seed: int
    prereg_version: str
    frozen_at_utc: str
    job_id: str
    user_id: str
    note: str = (
        "Frozen before capture (WAVE38_LIVE_PREREG §5). "
        "Not byte-identical to Bridge sealed window as sole data source."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_bridge_window_identical(start: datetime, end: datetime) -> bool:
    return start == BRIDGE_WINDOW_START_UTC and end == BRIDGE_WINDOW_END_UTC


def compute_window(
    *,
    t0: datetime | None = None,
    rolling_days: int = ROLLING_DAYS,
    seed: int | None = None,
    job_id: str = "live-first",
    user_id: str = "wave38",
) -> FrozenLiveWindow:
    """Compute [T0−rolling_days, T0] without writing."""
    th = load_wave38_thresholds()  # bindend gate
    t0 = t0 or datetime.now(timezone.utc).replace(microsecond=0)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    end = t0
    start = end - timedelta(days=rolling_days)
    if is_bridge_window_identical(start, end):
        # Shift end by 1s so we never freeze the sealed Bridge endpoints as-is
        end = end + timedelta(seconds=1)
        start = end - timedelta(days=rolling_days)
    n_bins = rolling_days * MINUTES_PER_DAY
    return FrozenLiveWindow(
        t0_utc=t0.isoformat(),
        window_start_utc=start.isoformat(),
        window_end_utc=end.isoformat(),
        window_start_ts=int(start.timestamp()),
        window_end_ts=int(end.timestamp()),
        n_bins=n_bins,
        rolling_days=rolling_days,
        seed=seed if seed is not None else th.seed_default,
        prereg_version="WAVE38_LIVE_PREREG.md",
        frozen_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        job_id=job_id,
        user_id=user_id,
    )


def freeze_live_window(
    *,
    user_id: str = "wave38",
    job_id: str = "live-first",
    t0: datetime | None = None,
    seed: int | None = None,
    force: bool = False,
) -> FrozenLiveWindow:
    """Write live_window.json under multi-tenant live root. Idempotent unless force."""
    live = ensure_live_directory(DiagnosticConfig.DATA_ROOT, user_id)
    ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT).assert_write_allowed(live)
    path = live / WINDOW_FILENAME
    if path.is_file() and not force:
        existing = load_frozen_window(user_id=user_id)
        return existing
    window = compute_window(t0=t0, seed=seed, job_id=job_id, user_id=user_id)
    if is_bridge_window_identical(
        _parse_iso(window.window_start_utc), _parse_iso(window.window_end_utc)
    ):
        raise RuntimeError(
            "Refuse to freeze Bridge sealed window endpoints as live window"
        )
    path.write_text(json.dumps(window.to_dict(), indent=2) + "\n", encoding="utf-8")
    return window


def load_frozen_window(*, user_id: str = "wave38") -> FrozenLiveWindow:
    path = DiagnosticConfig.wave38_live_root(user_id) / WINDOW_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"live window not frozen: {path}")
    body = json.loads(path.read_text(encoding="utf-8"))
    return FrozenLiveWindow(**{k: body[k] for k in FrozenLiveWindow.__dataclass_fields__})


def window_path(*, user_id: str = "wave38") -> Path:
    return DiagnosticConfig.wave38_live_root(user_id) / WINDOW_FILENAME


__all__ = [
    "BRIDGE_WINDOW_END_UTC",
    "BRIDGE_WINDOW_START_UTC",
    "FrozenLiveWindow",
    "WINDOW_FILENAME",
    "compute_window",
    "freeze_live_window",
    "is_bridge_window_identical",
    "load_frozen_window",
    "window_path",
]
