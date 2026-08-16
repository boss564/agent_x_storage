"""Adapter: Wirtschafts-Simulation -> AstroCore KuramotoEvaluator (Baustein 5b).

Runs the 9-agent Wirtschafts-Schwarm simulation and evaluates whether the
Gewaltenteilung (Freigabe/delegation) interactions produce measurable phase
coupling. The verdict is an OPEN measurement — COUPLED and NO_COUPLING are
both valid outcomes and are reported as-is.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from astrocore.emergence_evaluator import KuramotoEvaluator
from agents_b2g.wirtschaft.simulation import WirtschaftsSimulation


@dataclass
class EmergenceResult:
    """Result of the Kuramoto evaluation on the Wirtschafts-Schwarm."""
    mean_r: float
    p_value: float
    status: str          # EMERGENCE_PASSED / EMERGENCE_FAILED
    n_agents: int
    n_events: int
    verdict: str         # COUPLED / NO_COUPLING

    @property
    def coupled(self) -> bool:
        return self.status == "EMERGENCE_PASSED"

    def summary(self) -> str:
        return (f"verdict={self.verdict}  mean_r={self.mean_r:.3f}  "
                f"p={self.p_value:.4f}  agents={self.n_agents}  "
                f"events={self.n_events}  status={self.status}")


def run_simulation_logs(ticks: int = 200,
                        reset_freigaben_every: int = 10) -> Dict[str, List[float]]:
    """Run the Wirtschafts-Simulation; return {agent_id: [float timestamps]}.

    Agents with fewer than 2 events are dropped (they cannot contribute a
    phase). Timestamps are the simulation's tick numbers as floats.
    """
    sim = WirtschaftsSimulation(ticks=ticks,
                                reset_freigaben_every=reset_freigaben_every)
    events = sim.run()
    return {aid: [float(t) for t in ts]
            for aid, ts in events.items() if len(ts) >= 2}


def evaluate_emergence(ticks: int = 200, n_surrogates: int = 500,
                       alpha: float = 0.01,
                       reset_freigaben_every: int = 10) -> EmergenceResult:
    """Run the simulation and evaluate Kuramoto coupling on the event logs."""
    logs = run_simulation_logs(ticks=ticks,
                               reset_freigaben_every=reset_freigaben_every)
    if not logs:
        raise ValueError("simulation produced no usable event logs")
    evaluator = KuramotoEvaluator(logs)
    mean_r = evaluator.compute_observed_mean_R()
    p_value, status = evaluator.run_significance_test(
        n_surrogates=n_surrogates, alpha=alpha)
    verdict = "COUPLED" if status == "EMERGENCE_PASSED" else "NO_COUPLING"
    return EmergenceResult(
        mean_r=float(mean_r),
        p_value=float(p_value),
        status=str(status),
        n_agents=len(logs),
        n_events=sum(len(ts) for ts in logs.values()),
        verdict=verdict,
    )


if __name__ == "__main__":
    result = evaluate_emergence()
    print(result.summary())
