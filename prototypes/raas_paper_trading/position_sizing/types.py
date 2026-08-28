"""Sizing sub-swarm types — charter-safe vocabulary only."""

from __future__ import annotations

SIZING_SCHEMA = "raas_position_sizing_v0"
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

STATUS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STATUS_COMPLETE = "COMPLETE"

GATE_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
GATE_LIMIT_OK = "LIMIT_OK"
GATE_LIMIT_EXCEEDED = "LIMIT_EXCEEDED"

FORBIDDEN_EXPORT_KEYS = frozenset(
    {
        "advisory_position_size",
        "recommended_units",
        "target_allocation",
        "should_trade",
    }
)
