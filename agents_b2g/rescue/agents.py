"""The 9 rescue agents across 3 classes (civil protection).

Gewaltenteilung: class A detects (no response means), class B responds
(no command authority), class C commands/resupplies (no field action).
Each unit depends on P2P interaction to close the OODA loop.
"""
from __future__ import annotations

from agents_b2g.rescue.unit_base import RescueUnit


def build_rescue_swarm() -> dict:
    """Instantiate the 9-agent rescue swarm. Returns {unit_id: RescueUnit}."""
    specs = [
        # --- Class A: Lageerkundung (detect, no response means) ---
        ("damage_assess", "A", "damage_assessment", 30.0),
        ("survivor_detect", "A", "victim_detection", 15.0),
        ("aerial_map", "A", "aerial_mapping", 20.0),
        # --- Class B: Rettung & Versorgung (respond, no command authority) ---
        ("search_rescue", "B", "victim_rescue", 10.0),
        ("medical_resp", "B", "medical_care", 8.0),
        ("infra_repair", "B", "route_clearing", 25.0),
        # --- Class C: Führung & Unterstützung (command/resupply, no field action) ---
        ("incident_cmd", "C", "incident_command", 40.0),
        ("logistics", "C", "resupply", 35.0),
        ("coordination", "C", "comms_relay", 12.0),
    ]
    return {
        uid: RescueUnit(unit_id=uid, unit_class=cls, capability=cap, ooda_period_s=period)
        for uid, cls, cap, period in specs
    }
