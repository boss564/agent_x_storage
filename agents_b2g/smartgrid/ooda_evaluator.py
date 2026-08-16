"""Phase-offset-shuffle evaluator for R_grid — re-exported from the ci module.

Same null hypothesis (phase-offset-shuffle, NOT IAAFT) as CI/Rescue/Humanitarian
studies, for cross-study comparability. R_grid is computed over the generator
(Class A) phase trajectories only.
"""

from agents_b2g.ci.ooda_evaluator import evaluate_h0, order_parameter, r_over_time

__all__ = ["evaluate_h0", "order_parameter", "r_over_time"]
