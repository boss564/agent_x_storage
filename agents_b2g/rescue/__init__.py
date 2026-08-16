"""Rescue coordination module (civil protection)."""
from agents_b2g.rescue.unit_base import RescueUnit, UnitState
from agents_b2g.rescue.coordinator import IncidentCoordinator
from agents_b2g.rescue.agents import build_rescue_swarm
from agents_b2g.rescue.ooda_evaluator import evaluate_coordination, order_parameter
from agents_b2g.rescue.simulation import RescueSimulation, phase_pull

__all__ = [
    "RescueUnit",
    "UnitState",
    "IncidentCoordinator",
    "build_rescue_swarm",
    "evaluate_coordination",
    "order_parameter",
    "RescueSimulation",
    "phase_pull",
]
