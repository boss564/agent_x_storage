"""
Post-MEV Diagnostic Extension (PM1–PM3).

Additive post-Gatekeeper stage after `mev_tail_completed`.
Not a main wave — submodule of Wave 38 diagnostic.
"""

from agents_b2g.diagnostic.post_mev.adversarial_signal_quarantiner import (
    AdversarialSignalQuarantiner,
)
from agents_b2g.diagnostic.post_mev.causal_graph_post_mev_reconciler import (
    CausalGraphPostMEVReconciler,
)
from agents_b2g.diagnostic.post_mev.config import PostMEVConfig, PostMEVConfigError
from agents_b2g.diagnostic.post_mev.post_mev_causal_consistency_validator import (
    PostMEVCausalConsistencyValidator,
)
from agents_b2g.diagnostic.post_mev.post_mev_orchestrator import (
    EVENT_SUBJECT,
    TRIGGER_EVENT,
    PostMEVOrchestrator,
    register_mev_tail_hook,
)
from agents_b2g.diagnostic.post_mev.types import (
    AmendmentEntry,
    PostMEVBlockCause,
    PostMEVDiagnosticEnvelope,
    PostMEVStatus,
    ReconcileVerdict,
)

__all__ = [
    "AdversarialSignalQuarantiner",
    "AmendmentEntry",
    "CausalGraphPostMEVReconciler",
    "EVENT_SUBJECT",
    "PostMEVBlockCause",
    "PostMEVConfig",
    "PostMEVConfigError",
    "PostMEVDiagnosticEnvelope",
    "PostMEVOrchestrator",
    "PostMEVStatus",
    "PostMEVCausalConsistencyValidator",
    "ReconcileVerdict",
    "TRIGGER_EVENT",
    "register_mev_tail_hook",
]
