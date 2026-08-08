"""
Red Teaming & Chaos-Simulation — BSI-Proofing Framework.

Injiziert Fehler in Echtzeit, testet Recovery-Mechanismen,
generiert BSI-konforme Prüfprotokolle.
3 Szenarien: ELSTER-Down, nPA-Ablauf, Netzwerkausfall.

Usage:
    from agents_b2g.chaos import ChaosController
    chaos = ChaosController()
    chaos.run_full_chaos_demo()
"""
from agents_b2g.chaos.chaos_controller import (
    ChaosConfig, JSONLogger, ChaosController, ChaosScenario, ChaosIncident,
)
__all__ = ["ChaosConfig", "JSONLogger", "ChaosController", "ChaosScenario", "ChaosIncident"]
