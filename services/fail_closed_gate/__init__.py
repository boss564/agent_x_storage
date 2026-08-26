"""Package marker for fail-closed gate service."""
from .gate_core import GateInput, GateVerdict, TradeSignal, evaluate_gate

__all__ = ["GateInput", "GateVerdict", "TradeSignal", "evaluate_gate"]
