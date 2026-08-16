"""The 9 CI agents across 3 classes (critical infrastructure protection).

Class A Sensorik (fast cycles), Class B Aktorik (mid), Class C Koordination (slow).
Cycle-time spread 1s..10s is deliberate: H0 tests whether phase-pull coupling
can produce coherence across this spread.
"""
from __future__ import annotations

from agents_b2g.ci.unit_base import CIUnit


def build_ci_swarm() -> dict:
    """Instantiate the 9-agent CI swarm. Returns {unit_id: CIUnit}."""
    specs = [
        # Class A — Sensorik & Fruehwarnung (fast)
        ("infra_sensor", "A", "infra_sensing", 1.0),
        ("cyber_monitor", "A", "cyber_monitoring", 2.0),
        ("env_sensor", "A", "environmental_sensing", 5.0),
        # Class B — Ausfuehrung & Regelung (mid)
        ("grid_controller", "B", "grid_control", 5.0),
        ("water_valve", "B", "water_control", 5.0),
        ("emerg_shutdown", "B", "emergency_shutdown", 5.0),
        # Class C — Koordination, Governance & Logistik (slow)
        ("central_command", "C", "incident_command", 10.0),
        ("resource_logistics", "C", "logistics", 10.0),
        ("maint_scheduler", "C", "maintenance", 10.0),
    ]
    return {uid: CIUnit(unit_id=uid, unit_class=cls, capability=cap,
                        cycle_period_s=period)
            for uid, cls, cap, period in specs}
