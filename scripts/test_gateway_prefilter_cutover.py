#!/usr/bin/env python3
"""Gateway prefilter cutover — backlog priority without core skip.

Checks:
  GATEWAY_CUTOVER_PASS — enabled + backlog → priority order; all processed
  GATEWAY_FALLBACK_PASS — score failure → FIFO; all processed

Usage:
  PYTHONPATH=. python3 scripts/test_gateway_prefilter_cutover.py
  make raas-gateway-prefilter-cutover
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal  # noqa: E402
from prototypes.raas_hybrid_shell.supranode_facade import (  # noqa: E402
    ExternalRequest,
    SupranodeFacade,
)
from prototypes.raas_hybrid_shell.untrusted_shell import propose  # noqa: E402


def _req(cid: str, kind: str, *, slip: float, lat: float) -> ExternalRequest:
    base = propose(kind)
    prop = LLMStrategyProposal(
        **{
            **base.to_dict(),
            "proposal_id": cid,
            "max_slippage_pct": slip,
            "latency_budget_ms": lat,
        }
    )
    return ExternalRequest(correlation_id=cid, proposal=prop)


def main() -> int:
    print("Gateway prefilter cutover")
    print("=" * 60)
    failed = 0
    facade = SupranodeFacade(tenant_id="cutover-smoke")

    # Deterministic scores: higher slip → higher score
    def score_ok(features: dict) -> dict:
        return {
            "type": "prefilter_score",
            "prefilter_score": float(features.get("slippage_pct", 0.0)),
            "live_execution": False,
        }

    def score_fail(_features: dict) -> dict:
        raise RuntimeError("prefilter unreachable")

    batch = [
        _req("low", "mild", slip=0.2, lat=10.0),
        _req("mid", "mild", slip=0.8, lat=20.0),
        _req("high", "aggressive", slip=2.5, lat=50.0),
        _req("mid2", "mild", slip=1.0, lat=15.0),
    ]

    # --- CUTOVER: priority under backlog ---
    cut = facade.handle_external_batch(
        batch,
        n_scenarios=12,
        prefilter_enabled=True,
        backlog_threshold=3,
        score_fn=score_ok,
    )
    order = cut.order_correlation_ids
    # Expected: high (2.5), mid2 (1.0), mid (0.8), low (0.2)
    expected = ["high", "mid2", "mid", "low"]
    if cut.mode != "priority" or order != expected:
        print(f"  FAIL  cutover order mode={cut.mode} order={order} expected={expected}")
        failed += 1
    elif not cut.all_processed or len(cut.responses) != 4:
        print("  FAIL  cutover not all processed")
        failed += 1
    else:
        print(f"  PASS  GATEWAY_CUTOVER order={order}")

    # Default disabled → FIFO even with backlog size
    fifo = facade.handle_external_batch(
        batch,
        n_scenarios=12,
        prefilter_enabled=False,
        backlog_threshold=3,
        score_fn=score_ok,
    )
    if fifo.mode != "fifo" or fifo.order_correlation_ids != [r.correlation_id for r in batch]:
        print(f"  FAIL  disabled should be FIFO got {fifo.mode} {fifo.order_correlation_ids}")
        failed += 1
    else:
        print("  PASS  PREFILTER_ENABLED=false → FIFO")

    # --- FALLBACK: score failure → FIFO ---
    fb = facade.handle_external_batch(
        batch,
        n_scenarios=12,
        prefilter_enabled=True,
        backlog_threshold=3,
        score_fn=score_fail,
    )
    if fb.mode != "fifo" or not fb.all_processed:
        print(f"  FAIL  fallback mode={fb.mode} processed={fb.all_processed}")
        failed += 1
    elif fb.order_correlation_ids != [r.correlation_id for r in batch]:
        print(f"  FAIL  fallback order {fb.order_correlation_ids}")
        failed += 1
    else:
        print("  PASS  GATEWAY_FALLBACK (unreachable → FIFO, all processed)")

    # Health exposes flags; single-path still works
    h = facade.health()
    if h.get("prefilter_role") != "queue_priority_only":
        print("  FAIL  health prefilter_role")
        failed += 1
    else:
        print("  PASS  health exposes prefilter_role")

    single = facade.handle_external_request(batch[0], n_scenarios=12)
    if single.live_execution is not False:
        print("  FAIL  single path live_execution")
        failed += 1
    else:
        print("  PASS  single-request path unchanged")

    cut_ok = cut.mode == "priority" and cut.all_processed and order == expected
    fb_ok = fb.mode == "fifo" and fb.all_processed
    verdict_cut = "GATEWAY_CUTOVER_PASS" if cut_ok else "GATEWAY_CUTOVER_FAIL"
    verdict_fb = "GATEWAY_FALLBACK_PASS" if fb_ok else "GATEWAY_FALLBACK_FAIL"
    overall = failed == 0

    print("=" * 60)
    print(f"VERDICT: {'GATEWAY_PREFILTER_CUTOVER_PASS' if overall else 'GATEWAY_PREFILTER_CUTOVER_FAIL'}")
    print(f"  {verdict_cut}")
    print(f"  {verdict_fb}")

    out = _ROOT / "data" / "raas" / "gateway_prefilter_cutover_last.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "verdict_cutover": verdict_cut,
                    "verdict_fallback": verdict_fb,
                    "cutover": cut.to_dict(),
                    "fallback": fb.to_dict(),
                    "fifo_disabled": fifo.to_dict(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"artifact: {out}")
    except OSError as exc:
        print(f"artifact: skipped ({exc})")

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
