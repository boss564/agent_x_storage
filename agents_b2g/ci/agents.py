"""The 9 CI agents across 3 classes (critical infrastructure protection)."""
from __future__ import annotations

from agents_b2g.ci.unit_base import CIUnit

# Cycle-time configuration (Takt-Verhaeltnis) — Takt-/Kopplungs-Review.
# Option A (AKTUELL): 3/5/5/10 s. Koordination auf der Regel-/Entscheidungs-
#   Ebene, nicht auf der 1-s-Sensorik. Spreizung 3:10 statt 1:10.
# Vor Review (H0 FAILS, R=0.4711, p=0.012): 1/2/5/10 s (Spreizung 1:10).
# Option B waere: coupling erhoehen (run_ci_h0.py). Option C: Jitter (simulation.py).
CYCLE_TIMES = {
    # Class A — Sensorik & Fruehwarnung
    "infra_sensor": 3.0,       # Option A: war 1.0
    "cyber_monitor": 5.0,      # Option A: war 2.0
    "env_sensor": 5.0,         # unverändert
    # Class B — Ausfuehrung & Regelung
    "grid_controller": 5.0,
    "water_valve": 5.0,
    "emerg_shutdown": 5.0,
    # Class C — Koordination, Governance & Logistik
    "central_command": 10.0,
    "resource_logistics": 10.0,
    "maint_scheduler": 10.0,
}


def build_ci_swarm() -> dict:
    """Instantiate the 9-agent CI swarm. Returns {unit_id: CIUnit}."""
    specs = [
        # (unit_id, class, capability)
        ("infra_sensor", "A", "infra_sensing"),
        ("cyber_monitor", "A", "cyber_monitoring"),
        ("env_sensor", "A", "environmental_sensing"),
        ("grid_controller", "B", "grid_control"),
        ("water_valve", "B", "water_control"),
        ("emerg_shutdown", "B", "emergency_shutdown"),
        ("central_command", "C", "incident_command"),
        ("resource_logistics", "C", "logistics"),
        ("maint_scheduler", "C", "maintenance"),
    ]
    return {uid: CIUnit(unit_id=uid, unit_class=cls, capability=cap,
                        cycle_period_s=CYCLE_TIMES[uid])
            for uid, cls, cap in specs}
