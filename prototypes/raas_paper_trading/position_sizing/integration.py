"""Optional hook from regime daemon — gated by POSITION_SIZING_ENABLED."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from prototypes.raas_paper_trading.ledger import PaperLedger
from prototypes.raas_paper_trading.position_sizing.config import (
    audit_path_default,
    load_gamma_map,
    min_regime_flag_trigger,
    position_sizing_enabled,
    risk_limit_fraction,
    stats_window_size,
)
from prototypes.raas_paper_trading.position_sizing.orchestrator import (
    PositionSizingOrchestrator,
)


def should_run_sizing(*, regime_flag: Optional[int]) -> bool:
    """Trigger T2: regime_flag >= POSITION_SIZING_MIN_REGIME_FLAG (default 1)."""
    if regime_flag is None:
        return False
    return int(regime_flag) >= min_regime_flag_trigger()


def run_sizing_if_enabled(
    *,
    symbol: str,
    mark_price: float,
    ledger: Optional[PaperLedger] = None,
    data_root: Optional[Path] = None,
    classified_regime: Optional[str] = None,
    regime_flag: Optional[int] = None,
    swarm_cycle_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not position_sizing_enabled():
        return None
    if not should_run_sizing(regime_flag=regime_flag):
        return {
            "skipped": True,
            "reason": "regime_flag_below_threshold",
            "regime_flag": regime_flag,
            "min_regime_flag": min_regime_flag_trigger(),
            "classified_regime": classified_regime,
        }
    root = data_root or Path(os.environ.get("SWARM_DATA_ROOT", "/data"))
    gamma_map = load_gamma_map()
    orch = PositionSizingOrchestrator(
        audit_path=Path(audit_path_default(str(root))),
        gamma_map=gamma_map,
        window_size=stats_window_size(),
        risk_limit_fraction=risk_limit_fraction(),
    )
    led = ledger or PaperLedger()
    return orch.run_cycle(
        ledger=led,
        mark_price=Decimal(str(mark_price)),
        symbol=symbol,
        classified_regime=classified_regime,
        regime_flag=regime_flag,
        swarm_cycle_id=swarm_cycle_id,
    )
