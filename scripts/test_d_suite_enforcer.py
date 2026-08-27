#!/usr/bin/env python3
"""D1–D4 suite enforcer barriers.

Usage:
  PYTHONPATH=. python3 scripts/test_d_suite_enforcer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    DSuiteViolation,
    EnforcerContext,
    WormAnchorStore,
)


def _ok(name: str) -> None:
    print(f"  PASS  {name}")


def main() -> int:
    print("D-suite enforcer")
    print("=" * 60)
    worm_path = _ROOT / "data" / "raas" / "worm" / "d_suite_test_anchors.jsonl"
    if worm_path.exists():
        worm_path.unlink()
    enforcer = DSuiteEnforcer(worm=WormAnchorStore(worm_path))
    failed = 0

    # Positive: structured shell proposal
    try:
        out = enforcer.enforce_all(
            EnforcerContext(
                caller_role="UNTRUSTED_SHELL",
                target_path="/api/v1/raas/evaluate",
                payload={
                    "label": "SYNTHETIC_MILD",
                    "max_slippage_pct": 0.5,
                    "profile_hint": "default",
                    "free_text": "rebalance portfolio to target weights",
                },
            )
        )
        assert out["not_investment_advice"] is True
        assert out["live_execution"] is False
        assert "_worm_anchor_sha256" in out
        _ok("D1/D3/D4 valid structured payload")
    except Exception as exc:
        print(f"  FAIL  valid payload: {exc}")
        failed += 1

    # D1 negative: advisory free-text
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="UNTRUSTED_SHELL",
                target_path="/api/v1/raas/evaluate",
                payload={"advice": "you should buy more AGX now"},
            )
        )
        print("  FAIL  D1 should block advisory advice")
        failed += 1
    except DSuiteViolation as v:
        assert v.debt_id == "D1"
        _ok("D1 blocks advisory free-text")

    # D2 negative: Red writes outside sandbox
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="RED",
                target_path="internal://scenario",
                write_path="/etc/passwd",
                payload={"scenario": "mev"},
            )
        )
        print("  FAIL  D2 should block non-sandbox write")
        failed += 1
    except DSuiteViolation as v:
        assert v.debt_id == "D2"
        _ok("D2 blocks Red outside sandbox")

    # D2 negative: Red sets gate_verdict
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://scenario",
                write_path="data/raas/sandbox/run1/",
                payload={"gate_verdict": "RELEASED"},
            )
        )
        print("  FAIL  D2 should block Red decision fields")
        failed += 1
    except DSuiteViolation as v:
        assert v.debt_id == "D2"
        _ok("D2 blocks Red decision fields")

    # D3 negative: shell hits core-internal path
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="UNTRUSTED_SHELL",
                target_path="/internal/kernel/state",
                payload={"label": "x"},
            )
        )
        print("  FAIL  D3 should block shell→kernel")
        failed += 1
    except DSuiteViolation as v:
        assert v.debt_id == "D3"
        _ok("D3 quarantines shell targets")

    # D4 negative: exterior bypasses facade
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="EXTERNAL",
                target_path="/admin/raw_runner",
                payload={"label": "x"},
            )
        )
        print("  FAIL  D4 should block exterior bypass")
        failed += 1
    except DSuiteViolation as v:
        assert v.debt_id == "D4"
        _ok("D4 blocks exterior bypass")

    # D2 positive: Red in sandbox
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="RED",
                target_path="internal://scenario",
                write_path="data/raas/sandbox/attack1/",
                payload={"scenario_id": "s1"},
            )
        )
        _ok("D2 allows Red sandbox write")
    except Exception as exc:
        print(f"  FAIL  D2 sandbox allow: {exc}")
        failed += 1

    # D2: Red-Team plugin must not sign envelopes / set gate
    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/mev_latency",
                write_path="data/raas/sandbox/mev_latency_redteam/",
                payload={"type": "attack_result", "envelope_id": "ENV-1"},
            )
        )
        print("  FAIL  D2 should block Red-Team envelope_id")
        failed += 1
    except DSuiteViolation as v:
        assert v.debt_id == "D2"
        _ok("D2 blocks Red-Team envelope_id")

    try:
        enforcer.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/mev_latency",
                write_path="data/raas/sandbox/mev_latency_redteam/ok/",
                payload={"type": "attack_result", "label": "LATENCY_SPIKE"},
            )
        )
        _ok("D2 allows Red-Team plugin sandbox write")
    except Exception as exc:
        print(f"  FAIL  D2 Red-Team sandbox allow: {exc}")
        failed += 1

    verdict = "D_SUITE_PASS" if failed == 0 else "D_SUITE_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}  failures={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
