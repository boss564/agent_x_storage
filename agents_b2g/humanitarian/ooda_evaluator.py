"""Phase-offset-shuffle evaluator — single source of truth in the ci module.

The humanitarian study uses the identical null hypothesis (phase-offset-shuffle,
NOT IAAFT) as the CI study, for cross-study comparability of method. The
evaluator is generic over phase_trajectories, so it is re-exported here rather
than duplicated.
"""
from agents_b2g.ci.ooda_evaluator import evaluate_h0, order_parameter, r_over_time

__all__ = ["evaluate_h0", "order_parameter", "r_over_time"]
