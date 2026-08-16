"""The 9 humanitarian logistics agents across 3 classes.

Calibrated cycle times (3:1 spread) per CI lesson. Natural 12:1 spread
(SAR ~5min ... customs ~60min) is documented as a limitation in the prereg,
not used here.
"""
from __future__ import annotations

from agents_b2g.humanitarian.unit_base import HumanitarianUnit

# Calibrated cycle times in sim-minutes. Spread 10 -> 30 = 3:1 (CI Option A analog).
HUM_CYCLE_TIMES = {
    # Class A — Sensorik & Bedarf
    "sar_agent": 10,             # Golden Hour, zeitkritisch
    "ngo_response_agent": 12,    # Lagebericht-Zyklus
    "uav_agent": 12,             # Ueberflug-Zyklus
    # Class B — Transport & Logistik
    "forward_hub_agent": 15,     # Lokale Verteilung
    "thw_agent": 18,             # Fahrzyklus
    "unhas_agent": 25,           # Flugzyklus
    # Class C — Governance & Priorisierung
    "ocha_agent": 20,            # Priorisierungsliste
    "med_coordination_agent": 18,  # Triage-Zyklus
    "b2g_agent": 30,             # Zoll-Freigabe
}


def build_humanitarian_swarm() -> dict:
    """Instantiate the 9-agent humanitarian swarm. Returns {unit_id: HumanitarianUnit}."""
    specs = [
        # (unit_id, class, capability) — classes match HUMANITAERE_LOGISTIK_PREREG.md
        ("sar_agent", "A", "search_rescue"),
        ("ngo_response_agent", "A", "needs_assessment"),
        ("uav_agent", "A", "aerial_recon"),
        ("forward_hub_agent", "B", "distribution"),
        ("thw_agent", "B", "land_transport"),
        ("unhas_agent", "B", "air_transport"),
        ("ocha_agent", "C", "priority_allocation"),
        ("b2g_agent", "C", "customs_clearance"),
        ("med_coordination_agent", "C", "medical_coordination"),
    ]
    return {uid: HumanitarianUnit(unit_id=uid, unit_class=cls, capability=cap,
                                  cycle_period_s=HUM_CYCLE_TIMES[uid])
            for uid, cls, cap in specs}
