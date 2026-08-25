"""Wave 28 Threat Engine — thin data adapters (no decision logic).

Global swarm memory (Spec §1.1); raw vault is tenant-scoped.
"""

from agents_b2g.defense.threat_engine.censorship_adapters import (
    CensorshipBypassAdapter,
    RelayerHealthAdapter,
    SanctionsScreeningAdapter,
    detect_address_poisoning,
)
from agents_b2g.defense.threat_engine.classifier_adapter import ClassifierIncidentAdapter
from agents_b2g.defense.threat_engine.learning_adapter import LearningEmbeddingAdapter
from agents_b2g.defense.threat_engine.memory_backend import MemoryThreatBackend, make_memory_session
from agents_b2g.defense.threat_engine.pseudonym import eoa_pseudonym, put_raw_vault, resolve_raw
from agents_b2g.defense.threat_engine.radar_adapter import RadarThreatStoreAdapter
from agents_b2g.defense.threat_engine.sensitivity_lifecycle import SensitivityLifecycle
from agents_b2g.defense.threat_engine.session import ThreatEngineSession, connect_from_env

__all__ = [
    "ThreatEngineSession",
    "connect_from_env",
    "MemoryThreatBackend",
    "make_memory_session",
    "eoa_pseudonym",
    "put_raw_vault",
    "resolve_raw",
    "RadarThreatStoreAdapter",
    "LearningEmbeddingAdapter",
    "ClassifierIncidentAdapter",
    "SensitivityLifecycle",
    "SanctionsScreeningAdapter",
    "RelayerHealthAdapter",
    "CensorshipBypassAdapter",
    "detect_address_poisoning",
]
