"""Oracle Anomaly Swarm — P5 sandbox Sub-Swarm (simulation only).

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
Interface: initialize_scenario · run_oracle_attack_scenario · report_scenario
"""

from plugins.oracle_anomaly_swarm.scenario_runner import (
    initialize_scenario,
    report_scenario,
    run_oracle_attack_scenario,
)

__all__ = [
    "initialize_scenario",
    "run_oracle_attack_scenario",
    "report_scenario",
]
