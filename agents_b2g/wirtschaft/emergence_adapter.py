"""Adapter: Wirtschafts-Simulation -> AstroCore KuramotoEvaluator (Baustein 5b).

Runs the 9-agent Wirtschafts-Schwarm simulation and evaluates whether the
Gewaltenteilung (Freigabe/delegation) interactions produce measurable phase
coupling. The verdict is an OPEN measurement — COUPLED and NO_COUPLING are
both valid outcomes and are reported as-is.

Optional P2: ``use_astrocore_hook`` attaches a read-only Class-C liquidation
signal (Rayleigh/PLV) without changing Kuramoto behaviour when disabled.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from astrocore.emergence_evaluator import KuramotoEvaluator
from agents_b2g.wirtschaft.simulation import WirtschaftsSimulation


@dataclass
class AstroCoreLiquidationSignal:
    """Class-C liquidation coupling metrics from astrocore_hook (P2)."""
    R: float
    rayleigh_p: float
    surrogate_p: float
    verdict: str
    data_provenance: str
    warnings: List[str] = field(default_factory=list)
    n_events: int = 0

    @classmethod
    def from_hook_dict(cls, data: Dict[str, Any]) -> "AstroCoreLiquidationSignal":
        return cls(
            R=float(data["R"]),
            rayleigh_p=float(data["rayleigh_p"]),
            surrogate_p=float(data["surrogate_p"]),
            verdict=str(data["verdict"]),
            data_provenance=str(data["data_provenance"]),
            warnings=list(data.get("warnings") or []),
            n_events=int(data.get("n_events", 0)),
        )


@dataclass
class EmergenceResult:
    """Result of the Kuramoto evaluation on the Wirtschafts-Schwarm."""
    mean_r: float
    p_value: float
    status: str          # EMERGENCE_PASSED / EMERGENCE_FAILED
    n_agents: int
    n_events: int
    verdict: str         # COUPLED / NO_COUPLING
    astrocore: Optional[AstroCoreLiquidationSignal] = None

    @property
    def coupled(self) -> bool:
        return self.status == "EMERGENCE_PASSED"

    def summary(self) -> str:
        if self.p_value > 0 and self.p_value <= 0.0020001:
            p_part = f"p<{self.p_value:.3f}"
        else:
            p_part = f"p={self.p_value:.4f}"
        base = (f"verdict={self.verdict}  mean_r={self.mean_r:.3f}  "
                f"{p_part}  agents={self.n_agents}  "
                f"events={self.n_events}  status={self.status}")
        if self.astrocore is None:
            return base
        ac = self.astrocore
        return (f"{base}  | astrocore={ac.verdict} "
                f"R={ac.R:.3f} prov={ac.data_provenance}")


def _fetch_astrocore_signal(
    *,
    use_astrocore_hook: bool,
    data_source: Optional[str] = None,
    audit_dir: Optional[str] = None,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
    lookback_days: Optional[int] = None,
    strict: Optional[bool] = None,
) -> Optional[AstroCoreLiquidationSignal]:
    if not use_astrocore_hook:
        return None
    from agents_b2g.astrocore_hook import AstrocoreHookClient

    client_kwargs: Dict[str, Any] = {
        "data_source": data_source or os.getenv("ASTROCORE_DATA_SOURCE", "synthetic"),
        "audit_dir": audit_dir or os.getenv("RAAS_AUDIT_DIR", "/data/audit"),
        "neo4j_uri": neo4j_uri,
        "neo4j_user": neo4j_user,
        "neo4j_password": neo4j_password,
        "lookback_days": lookback_days or int(os.getenv("ASTROCORE_NEO4J_LOOKBACK_DAYS", "7")),
    }
    if strict is not None:
        client_kwargs["strict"] = strict
    client = AstrocoreHookClient(**client_kwargs)
    return AstroCoreLiquidationSignal.from_hook_dict(client.to_evaluator_signal())


def run_simulation_logs(ticks: int = 200,
                        reset_freigaben_every: int = 10) -> Dict[str, List[float]]:
    """Run the Wirtschafts-Simulation; return {agent_id: [float timestamps]}."""
    sim = WirtschaftsSimulation(ticks=ticks,
                                reset_freigaben_every=reset_freigaben_every)
    events = sim.run()
    return {aid: [float(t) for t in ts]
            for aid, ts in events.items() if len(ts) >= 2}


def evaluate_emergence(
    ticks: int = 200,
    n_surrogates: int = 500,
    alpha: float = 0.01,
    reset_freigaben_every: int = 10,
    use_astrocore_hook: Optional[bool] = None,
    data_source: Optional[str] = None,
    audit_dir: Optional[str] = None,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
    lookback_days: Optional[int] = None,
    strict: Optional[bool] = None,
) -> EmergenceResult:
    """Run Kuramoto evaluation; optionally attach Class-C astrocore signal."""
    if use_astrocore_hook is None:
        use_astrocore_hook = os.getenv(
            "ASTROCORE_HOOK_ENABLED", "false"
        ).lower() in ("true", "1", "yes")

    logs = run_simulation_logs(ticks=ticks,
                               reset_freigaben_every=reset_freigaben_every)
    if not logs:
        raise ValueError("simulation produced no usable event logs")
    evaluator = KuramotoEvaluator(logs)
    mean_r = evaluator.compute_observed_mean_R()
    p_value, status = evaluator.run_significance_test(
        n_surrogates=n_surrogates, alpha=alpha)
    verdict = "COUPLED" if status == "EMERGENCE_PASSED" else "NO_COUPLING"

    astrocore = _fetch_astrocore_signal(
        use_astrocore_hook=use_astrocore_hook,
        data_source=data_source,
        audit_dir=audit_dir,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        lookback_days=lookback_days,
        strict=strict,
    )

    return EmergenceResult(
        mean_r=float(mean_r),
        p_value=float(p_value),
        status=str(status),
        n_agents=len(logs),
        n_events=sum(len(ts) for ts in logs.values()),
        verdict=verdict,
        astrocore=astrocore,
    )


if __name__ == "__main__":
    result = evaluate_emergence()
    print(result.summary())
