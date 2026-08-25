"""Emergenz-Messung fuer Agentenschwaerme.

  measure.py         — Divergenz, Graphstruktur vs. Nullmodell, Kuramoto
  self_test.py       — 5 synthetische Faelle mit bekannter Grundwahrheit
  adapter_agentx.py  — schneidet einen Lauf des 27-Agenten-ABM mit
  partner_select.py  — Least-Loaded + crc32-Tie-Break (TIER 1 Topologie)
"""
from .measure import (
    SwarmTrace, assess, divergence, graph_structure, kuramoto, kuramoto_firing,
)
from .partner_select import StickySelector, select_partner, permute_sticky_map
from .coupling import backpressure_factor

__all__ = [
    "SwarmTrace", "assess", "divergence", "graph_structure", "kuramoto",
    "kuramoto_firing",
    "select_partner", "StickySelector", "permute_sticky_map", "backpressure_factor",
]
