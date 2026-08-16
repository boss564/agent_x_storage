"""Critical-infrastructure protection module (civilian simulation)."""
from agents_b2g.ci.unit_base import CIUnit, UnitState
from agents_b2g.ci.agents import build_ci_swarm
from agents_b2g.ci.simulation import CINormalSimulation
from agents_b2g.ci.ooda_evaluator import evaluate_h0, order_parameter

__all__ = ["CIUnit", "UnitState", "build_ci_swarm", "CINormalSimulation",
           "evaluate_h0", "order_parameter"]
