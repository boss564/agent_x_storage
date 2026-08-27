#!/usr/bin/env python3
"""MEV/Latency Red-Team plugin smoke — D2 sandbox + optional NATS.

Checks:
  - run_attack_scenario / report_scenario (no execute_*)
  - sandbox write only under data/raas/sandbox/
  - path escape blocked
  - DSuiteEnforcer: Red cannot set gate_verdict; sandbox write OK
  - Dockerfile declares non-root USER + read-only runtime intent
  - Optional NATS Queue-Group roundtrip if NATS reachable

Usage:
  PYTHONPATH=. python3 scripts/test_mev_latency_redteam.py
  make raas-mev-redteam
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.mev_latency_redteam.sandbox_io import (  # noqa: E402
    SandboxPathError,
    resolve_sandbox_path,
    write_sandbox_json,
)
from plugins.mev_latency_redteam.scenario_runner import (  # noqa: E402
    initialize_scenario,
    report_scenario,
    run_attack_scenario,
)
from services.fail_closed_gate.d_suite_enforcer import (  # noqa: E402
    DSuiteEnforcer,
    DSuiteViolation,
    EnforcerContext,
    WormAnchorStore,
)


def _ok(name: str) -> None:
    print(f"  PASS  {name}")


def _fail(name: str) -> None:
    print(f"  FAIL  {name}")


def main() -> int:
    print("MEV/Latency Red-Team plugin smoke")
    print("=" * 60)
    failed = 0

    # 1) Scenario pipeline
    state = initialize_scenario(
        "LATENCY_SPIKE",
        scenario_id="smoke-latency",
        params={"base_latency_ms": 5.0},
        seed=20260827,
    )
    attack = run_attack_scenario(state)
    if attack.get("type") != "attack_result" or attack.get("live_execution") is not False:
        _fail("attack_result shape")
        failed += 1
    elif "gate_verdict" in attack or "audit_verdict" in attack:
        _fail("decision fields leaked in attack_result")
        failed += 1
    else:
        _ok("run_attack_scenario LATENCY_SPIKE")

    report = report_scenario(state, attack, repo_root=_ROOT)
    sp = Path(report["sandbox_path"])
    if not sp.exists() or "data/raas/sandbox" not in str(sp).replace("\\", "/"):
        _fail("report not under sandbox")
        failed += 1
    else:
        _ok("report_scenario writes under sandbox")

    # 2) Path escape
    try:
        resolve_sandbox_path("../worm/evil.json", repo_root=_ROOT)
        _fail("path escape should raise")
        failed += 1
    except SandboxPathError:
        _ok("sandbox path escape blocked")

    try:
        write_sandbox_json(
            "../../outside.json",
            {"x": 1},
            repo_root=_ROOT,
        )
        _fail("write escape should raise")
        failed += 1
    except SandboxPathError:
        _ok("sandbox write escape blocked")

    # 3) D2 via enforcer
    worm = _ROOT / "data" / "raas" / "worm" / "redteam_smoke_anchors.jsonl"
    if worm.exists():
        worm.unlink()
    enf = DSuiteEnforcer(worm=WormAnchorStore(worm))

    try:
        enf.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/mev_latency",
                write_path="data/raas/sandbox/mev_latency_redteam/smoke/",
                payload={"label": "LATENCY_SPIKE", "type": "attack_result"},
            )
        )
        _ok("D2 allows Red sandbox write")
    except DSuiteViolation as exc:
        _fail(f"D2 sandbox allow: {exc}")
        failed += 1

    try:
        enf.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/mev_latency",
                write_path="data/raas/sandbox/mev_latency_redteam/x/",
                payload={"gate_verdict": "RELEASED"},
            )
        )
        _fail("D2 should block Red gate_verdict")
        failed += 1
    except DSuiteViolation as exc:
        if exc.debt_id == "D2":
            _ok("D2 blocks Red gate_verdict")
        else:
            _fail(f"wrong debt {exc.debt_id}")
            failed += 1

    try:
        enf.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/mev_latency",
                write_path="data/raas/worm/evil/",
                payload={"type": "attack_result"},
            )
        )
        _fail("D2 should block write outside sandbox")
        failed += 1
    except DSuiteViolation as exc:
        if exc.debt_id == "D2":
            _ok("D2 blocks Red outside sandbox")
        else:
            _fail(f"wrong debt {exc.debt_id}")
            failed += 1

    # 4) Dockerfile OS-isolation intent
    df = (_ROOT / "plugins/mev_latency_redteam/Dockerfile").read_text(encoding="utf-8")
    checks = [
        ("USER redteam" in df, "Dockerfile USER redteam"),
        ("--read-only" in df, "Dockerfile documents --read-only"),
        ("--cap-drop ALL" in df or "cap-drop ALL" in df, "Dockerfile documents cap-drop ALL"),
        ("worm" not in df.lower() or "Does NOT mount" in df, "Dockerfile avoids worm mount"),
    ]
    for ok, name in checks:
        if ok:
            _ok(name)
        else:
            _fail(name)
            failed += 1

    # 5) Optional NATS
    nats_url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    nats_result = None
    try:
        from plugins.mev_latency_redteam.nats_bridge import run_nats_roundtrip

        nats_result = run_nats_roundtrip(
            {
                "kind": "LATENCY_SPIKE",
                "scenario_id": "smoke-nats",
                "seed": 20260827,
                "params": {"base_latency_ms": 5.0},
            },
            nats_url=nats_url,
            repo_root=str(_ROOT),
        )
        if (
            nats_result.get("via") == "nats_queue_group"
            and nats_result.get("attack", {}).get("type") == "attack_result"
            and "gate_verdict" not in nats_result.get("attack", {})
        ):
            _ok("NATS Queue-Group roundtrip")
        else:
            _fail("NATS roundtrip shape")
            failed += 1
    except Exception as exc:
        print(f"  SKIP  NATS ({exc})")

    verdict = "MEV_REDTEAM_PASS" if failed == 0 else "MEV_REDTEAM_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")

    out = _ROOT / "data" / "raas" / "mev_redteam_last.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "verdict": verdict,
                    "failed": failed,
                    "attack": attack,
                    "report": report,
                    "nats": nats_result,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"artifact: {out}")
    except OSError as exc:
        print(f"artifact: skipped ({exc})")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
