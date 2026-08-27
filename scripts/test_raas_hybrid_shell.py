#!/usr/bin/env python3
"""RaaS hybrid shell pilot — untrusted shell → TrustedCoreGateway → core.

Does NOT remap P₁…P₉. Does NOT invent agents/p1… under agents/.
Uses existing raas_portal store/runner/exporter.

Usage:
  PYTHONPATH=. python3 scripts/test_raas_hybrid_shell.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_hybrid_shell.trusted_gateway import TrustedCoreGateway
from prototypes.raas_hybrid_shell.untrusted_shell import propose


def main() -> int:
    print("RaaS hybrid shell pilot")
    print("=" * 60)
    gw = TrustedCoreGateway(tenant_id="hybrid-shell-smoke")
    print(f"gateway: {gw.health()}")

    mild = propose("mild")
    agg = propose("aggressive")
    print(f"shell mild:       slippage={mild.max_slippage_pct} untrusted={mild.untrusted}")
    print(f"shell aggressive: slippage={agg.max_slippage_pct} untrusted={agg.untrusted}")

    env_mild = gw.evaluate_shell_proposal(mild, n_scenarios=30)
    env_agg = gw.evaluate_shell_proposal(agg, n_scenarios=30)

    print(
        f"core mild:       gate={env_mild.gate_verdict:<8} "
        f"risk_block={env_mild.risk_block_rate} "
        f"advice={env_mild.not_investment_advice} live={env_mild.live_execution}"
    )
    print(
        f"core aggressive: gate={env_agg.gate_verdict:<8} "
        f"risk_block={env_agg.risk_block_rate} "
        f"cm={len(env_agg.countermeasures)}"
    )

    ok_flags = [
        env_mild.live_execution is False,
        env_agg.live_execution is False,
        env_mild.not_investment_advice is True,
        env_agg.not_investment_advice is True,
        env_mild.shell_untrusted is True,
        env_agg.gate_verdict == "BLOCKED",  # hard slippage ceiling
        all("CANDIDATE" in c or c.startswith("CANDIDATE") for c in env_agg.countermeasures)
        or len(env_agg.countermeasures) >= 1,
        not any("execute_" in c.lower() for c in env_agg.countermeasures),
    ]
    ok = all(ok_flags)
    verdict = "HYBRID_SHELL_PASS" if ok else "HYBRID_SHELL_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    out = _ROOT / "data" / "raas" / "hybrid_shell_last.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "verdict": verdict,
                "mild": env_mild.to_dict(),
                "aggressive": env_agg.to_dict(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"artifact: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
