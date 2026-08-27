"""MEV & Latency Red-Team plugin — sandbox-only Sub-Swarm.

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
No execute_*; scenarios only via run_attack_scenario / report_scenario.
D2: writes under data/raas/sandbox/ only; never sets gate/audit fields.
"""

from plugins.mev_latency_redteam.scenario_runner import (
    initialize_scenario,
    report_scenario,
    run_attack_scenario,
)

__all__ = [
    "initialize_scenario",
    "run_attack_scenario",
    "report_scenario",
]
