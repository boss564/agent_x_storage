#!/usr/bin/env python3
"""Supranode facade smoke — Ingress/Egress over TrustedCoreGateway.

Usage:
  PYTHONPATH=. python3 scripts/test_raas_supranode.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_hybrid_shell.supranode_facade import (
    ExternalRequest,
    SupranodeFacade,
)
from prototypes.raas_hybrid_shell.untrusted_shell import propose


def main() -> int:
    print("RaaS supranode facade")
    print("=" * 60)
    facade = SupranodeFacade(tenant_id="supranode-smoke")
    print(f"facade: {facade.health()}")

    mild = ExternalRequest(correlation_id="corr-mild", proposal=propose("mild"))
    agg = ExternalRequest(
        correlation_id="corr-agg", proposal=propose("aggressive")
    )

    r_mild = facade.handle_external_request(mild, n_scenarios=30)
    r_agg = facade.handle_external_request(agg, n_scenarios=30)

    print(
        f"egress mild: gate={r_mild.envelope.gate_verdict:<8} "
        f"seal={r_mild.egress_seal[:12]}… debt={r_mild.debt}"
    )
    print(
        f"egress agg:  gate={r_agg.envelope.gate_verdict:<8} "
        f"seal={r_agg.egress_seal[:12]}… live={r_agg.live_execution}"
    )

    ok = all(
        [
            r_mild.live_execution is False,
            r_agg.live_execution is False,
            r_mild.not_investment_advice is True,
            r_agg.envelope.gate_verdict == "BLOCKED",
            r_mild.egress_seal != r_agg.egress_seal,
            "D4_ingress_egress_only" in facade.health()["debt"],
            facade.health().get("microservices") == 0,
            facade.health().get("bus") is None,
            not any(
                "execute_" in c.lower()
                for c in r_agg.envelope.countermeasures
            ),
        ]
    )
    verdict = "SUPRANODE_FACADE_PASS" if ok else "SUPRANODE_FACADE_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    out = _ROOT / "data" / "raas" / "supranode_facade_last.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "verdict": verdict,
                "mild": r_mild.to_dict(),
                "aggressive": r_agg.to_dict(),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"artifact: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
