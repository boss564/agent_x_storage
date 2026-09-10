"""
Frozen M2a full-history methodology — do not change without new prereg amendment.

See docs/M2A_FUNDING_SQUEEZE_PREREG.md
"""
from __future__ import annotations

from datetime import datetime, timezone

# Planned contiguous perp window (Binance BTCUSDT/ETHUSDT from ~2019-09-01)
PERP_START = datetime(2019, 9, 1, tzinfo=timezone.utc)
PREREG_FREEZE = datetime(2026, 9, 2, tzinfo=timezone.utc)

# Chronological 60/40 split (M2 §5 analogue) — fixed before first full-history run
OOS_TRAIN_FRAC = 0.60
_oos_delta = PREREG_FREEZE - PERP_START
OOS_SPLIT_TS = PERP_START + _oos_delta * OOS_TRAIN_FRAC  # 2023-11-13T19:12:00+00:00

# Prereg funding thresholds (decimal per 8h) — grid unchanged; primary verdict on θ_primary only.
FUNDING_THRESHOLDS_PREREG = [0.0005, 0.001, 0.0015]
# Amendment A1 (2026-09-02): primary θ lowered 0.10% → 0.05% before any PnL (studiendesign).
PREREG_PRIMARY_THRESHOLD = 0.0005  # 0.05% / 8h — living regime post-2023; was 0.001
PREREG_SECONDARY_THRESHOLDS = [0.001, 0.0015]  # historical / descriptive only (OOS sparse)

# Friction (decimal round-trip). 19 bps = modern; early perp era wider spreads/fees.
FRICTION_MODERN = 0.0019  # 19 bps — from 2022-01-01
FRICTION_EARLY = 0.0035  # 35 bps — 2019-09-01 .. 2021-12-31 (conservative)
FRICTION_EARLY_START = datetime(2019, 9, 1, tzinfo=timezone.utc)
FRICTION_EARLY_END = datetime(2021, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
FRICTION_MODERN_START = datetime(2022, 1, 1, tzinfo=timezone.utc)

# Sensitivity bounds (report only — not primary verdict)
FRICTION_SENSITIVITY_LOW = 0.0019
FRICTION_SENSITIVITY_HIGH = 0.0035

# Inference unit
MIN_EPISODES_GRID = 10
MIN_EPISODES_OOS = 15  # minimum independent episodes in OOS 40% for verdict
MAX_TRADES_PER_EPISODE = 1  # analogue PAPER_MAX_OPEN_POSITIONS=1

# Grid (unchanged from 365d pilot)
K_TP_GRID = [1.0, 1.5, 2.0]
K_SL_GRID = [0.5, 1.0, 1.5]


def friction_for_timestamp(ts) -> float:
    """Period-dependent round-trip friction for entry timestamp."""
    import pandas as pd

    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    if FRICTION_EARLY_START <= t.to_pydatetime() <= FRICTION_EARLY_END:
        return FRICTION_EARLY
    return FRICTION_MODERN


def split_label(ts) -> str:
    import pandas as pd

    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return "train" if t.to_pydatetime() < OOS_SPLIT_TS else "oos"
