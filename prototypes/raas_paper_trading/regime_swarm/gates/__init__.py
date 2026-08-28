"""Infrastructure gates (A0 / A2.5) — fail-closed via gate_core.evaluate_gate()."""

from prototypes.raas_paper_trading.regime_swarm.gates.common import (
    INFRA_BLOCK_REASONS,
    InfraGateResult,
    infra_verdict_passed,
)
from prototypes.raas_paper_trading.regime_swarm.gates.config import InfraGatesConfig
from prototypes.raas_paper_trading.regime_swarm.gates.core_sanity_adapter import (
    CoreSanityAdapter,
)
from prototypes.raas_paper_trading.regime_swarm.gates.transport_boundary import (
    TransportBoundaryGate,
)

__all__ = [
    "CoreSanityAdapter",
    "TransportBoundaryGate",
    "InfraGatesConfig",
    "InfraGateResult",
    "INFRA_BLOCK_REASONS",
    "infra_verdict_passed",
]
