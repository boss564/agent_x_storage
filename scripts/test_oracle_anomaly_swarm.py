#!/usr/bin/env python3
"""Oracle Anomaly Swarm smoke — D2 sandbox + optional NATS.

Checks:
  - run_oracle_attack_scenario / report_scenario (STALE_PRICE, FAT_FINGER, FLASH_CRASH)
  - sandbox write only under data/raas/sandbox/oracle_anomaly_swarm/
  - path escape blocked
  - DSuiteEnforcer: Red cannot set gate_verdict
  - Dockerfile non-root + read-only / cap-drop intent
  - Optional NATS Queue-Group on edge.P5.oracle.sandbox

Usage:
  PYTHONPATH=. python3 scripts/test_oracle_anomaly_swarm.py
  make raas-oracle-anomaly
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.oracle_anomaly_swarm.sandbox_io import (  # noqa: E402
    SandboxPathError,
    resolve_sandbox_path,
)
from plugins.oracle_anomaly_swarm.scenario_runner import (  # noqa: E402
    initialize_scenario,
    report_scenario,
    run_oracle_attack_scenario,
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
    print("Oracle Anomaly Swarm smoke")
    print("=" * 60)
    failed = 0
    attacks = {}

    for kind in ("STALE_PRICE", "FAT_FINGER", "FLASH_CRASH", "DEPEG_SIM"):
        state = initialize_scenario(
            kind,
            scenario_id=f"smoke-{kind.lower()}",
            params=(
                {"fair_price": 1.0, "peg_price": 1.0, "break_pct": 25.0, "feed_id": "SYNTHETIC_ORACLE_A"}
                if kind == "DEPEG_SIM"
                else {"fair_price": 100.0, "feed_id": "SYNTHETIC_ORACLE_A"}
            ),
            seed=20260827,
        )
        attack = run_oracle_attack_scenario(state)
        attacks[kind] = attack
        if (
            attack.get("type") != "attack_result"
            or attack.get("live_execution") is not False
            or "gate_verdict" in attack
            or attack.get("artifact", {}).get("scenario_kind") != kind
        ):
            _fail(f"run_oracle_attack_scenario {kind}")
            failed += 1
        else:
            _ok(f"run_oracle_attack_scenario {kind}")

    report = report_scenario(
        initialize_scenario("STALE_PRICE", scenario_id="smoke-stale_price", seed=20260827),
        attacks["STALE_PRICE"],
        repo_root=_ROOT,
    )
    if "oracle_anomaly_swarm" not in report["sandbox_path"].replace("\\", "/"):
        _fail("report not under oracle sandbox")
        failed += 1
    else:
        _ok("report_scenario writes under oracle sandbox")

    try:
        resolve_sandbox_path("../worm/evil.json", repo_root=_ROOT)
        _fail("path escape should raise")
        failed += 1
    except SandboxPathError:
        _ok("sandbox path escape blocked")

    worm = _ROOT / "data" / "raas" / "worm" / "oracle_smoke_anchors.jsonl"
    if worm.exists():
        worm.unlink()
    enf = DSuiteEnforcer(worm=WormAnchorStore(worm))

    try:
        enf.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/oracle_anomaly",
                write_path="data/raas/sandbox/oracle_anomaly_swarm/smoke/",
                payload={"type": "attack_result", "label": "STALE_PRICE"},
            )
        )
        _ok("D2 allows Red oracle sandbox write")
    except DSuiteViolation as exc:
        _fail(f"D2 sandbox allow: {exc}")
        failed += 1

    try:
        enf.enforce_all(
            EnforcerContext(
                caller_role="RED_TEAM",
                target_path="internal://plugin/oracle_anomaly",
                write_path="data/raas/sandbox/oracle_anomaly_swarm/x/",
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

    df = (_ROOT / "plugins/oracle_anomaly_swarm/Dockerfile").read_text(encoding="utf-8")
    for ok, name in [
        ("USER redteam" in df, "Dockerfile USER redteam"),
        ("--read-only" in df, "Dockerfile documents --read-only"),
        ("cap-drop ALL" in df, "Dockerfile documents cap-drop ALL"),
        ("Does NOT mount" in df, "Dockerfile avoids worm/core mount"),
    ]:
        if ok:
            _ok(name)
        else:
            _fail(name)
            failed += 1

    nats_result = None
    try:
        from plugins.oracle_anomaly_swarm.nats_bridge import run_nats_roundtrip

        nats_result = run_nats_roundtrip(
            {
                "kind": "FLASH_CRASH",
                "scenario_id": "smoke-nats-flash",
                "seed": 20260827,
                "params": {"fair_price": 100.0},
            },
            nats_url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"),
            repo_root=str(_ROOT),
        )
        if (
            nats_result.get("via") == "nats_queue_group"
            and nats_result.get("subject") == "edge.P5.oracle.sandbox"
            and nats_result.get("attack", {}).get("artifact", {}).get("scenario_kind")
            == "FLASH_CRASH"
        ):
            _ok("NATS Queue-Group roundtrip P5")
        else:
            _fail("NATS roundtrip shape")
            failed += 1
    except Exception as exc:
        print(f"  SKIP  NATS ({exc})")

    verdict = "ORACLE_ANOMALY_PASS" if failed == 0 else "ORACLE_ANOMALY_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")

    out = _ROOT / "data" / "raas" / "oracle_anomaly_last.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "verdict": verdict,
                    "failed": failed,
                    "attacks": attacks,
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
