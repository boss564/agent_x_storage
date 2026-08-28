#!/usr/bin/env python3
"""P6 smoke — regime-swarm leader FSM Z3 proofs (Infra-Guardian gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_swarm.leader_fsm_z3 import (  # noqa: E402
    prove_regime_leader_invariant,
)


def main() -> int:
    report = prove_regime_leader_invariant(mode="all", max_replicas=2, max_depth=14)
    print(json.dumps(report, indent=2))
    if report["gate"] != "PASS":
        print("VERDICT: REGIME_LEADER_Z3_FAIL")
        return 1
    print("VERDICT: REGIME_LEADER_Z3_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
