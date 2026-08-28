"""Optional hook from regime daemon — gated by POSITION_SIZING_ENABLED."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.position_sizing.config import (
    audit_path_default,
    gamma_default,
    position_sizing_enabled,
    risk_limit_fraction,
    stats_window_size,
)
from prototypes.raas_paper_trading.position_sizing.orchestrator import (
    PositionSizingOrchestrator,
)


def run_sizing_if_enabled(
    *,
    symbol: str,
    mark_price: float,
    ledger: Optional[PaperLedger] = None,
    data_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    if not position_sizing_enabled():
        return None
    root = data_root or Path(os.environ.get("SWARM_DATA_ROOT", "/data"))
    orch = PositionSizingOrchestrator(
        audit_path=Path(audit_path_default(str(root))),
        gamma=gamma_default(),
        window_size=stats_window_size(),
        risk_limit_fraction=risk_limit_fraction(),
    )
    led = ledger or PaperLedger()
    return orch.run_cycle(
        ledger=led,
        mark_price=Decimal(str(mark_price)),
        symbol=symbol,
    )
