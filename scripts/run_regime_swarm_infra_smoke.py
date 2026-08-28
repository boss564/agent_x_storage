#!/usr/bin/env python3
"""End-to-end infra-gate smoke: WORM → A0/A2.5 → block or drift pipeline.

Charter: DEFENSIVE_CAUSAL_GROUNDING · monitoring only · live_execution=false

Usage:
  PYTHONPATH=. python3 scripts/run_regime_swarm_infra_smoke.py
  docker compose -f docker-compose.regime-swarm-smoke.yml run --rm swarm-smoke
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_swarm.gates.config import InfraGatesConfig  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.orchestrator import RegimeSwarmOrchestrator  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.worm_fixtures import (  # noqa: E402
    ensure_smoke_worms,
    stable_prices,
    write_signal_worm,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_dir() -> Path:
    raw = os.environ.get("SWARM_SMOKE_AUDIT_DIR", str(_ROOT / "logs" / "worm" / "smoke_audit"))
    return Path(raw)


def _worm_root() -> Path:
    raw = os.environ.get("SWARM_SMOKE_WORM_DIR", str(_ROOT / "data" / "worm" / "smoke"))
    return Path(raw)


def _write_audit(name: str, payload: Dict[str, Any]) -> Path:
    out = _audit_dir()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _orch() -> RegimeSwarmOrchestrator:
    return RegimeSwarmOrchestrator(
        infra_gates=InfraGatesConfig.from_env(),
        audit_path=_audit_dir() / "regime_drift_audit.jsonl",
    )


def _assert_flash_block(result: Dict[str, Any]) -> Tuple[bool, str]:
    if result.get("status") != "INFRASTRUCTURE_BLOCKED":
        return False, f"status={result.get('status')}"
    if result.get("drift_summary") != "NOT_COMPUTED":
        return False, f"drift_summary={result.get('drift_summary')!r}"
    infra = result.get("infrastructure") or {}
    if infra.get("infrastructure_healthy") is not False:
        return False, f"infrastructure={infra}"
    g0 = str(infra.get("g0_core_sanity", ""))
    if "A0_BLOCKED" not in g0:
        return False, f"g0_core_sanity={g0!r}"
    if result.get("agents", {}).get("A5") is not None:
        return False, "A5 ran despite infra block"
    return True, g0


def _a0_passed(result: Dict[str, Any]) -> bool:
    a0 = (result.get("agents") or {}).get("A0")
    if isinstance(a0, dict):
        return bool(a0.get("passed"))
    infra = result.get("infrastructure") or {}
    g0 = str(infra.get("g0_core_sanity", ""))
    return g0 == "PASSED"


def _assert_valid_pass(result: Dict[str, Any]) -> Tuple[bool, str]:
    if result.get("status") == "INFRASTRUCTURE_BLOCKED":
        return False, f"blocked: {result.get('infrastructure')}"
    if not _a0_passed(result):
        return False, f"A0 not passed: {(result.get('agents') or {}).get('A0')}"
    status = result.get("status")
    if status not in ("COMPLETE", "INSUFFICIENT_WINDOWS", "INSUFFICIENT_DATA"):
        return False, f"unexpected status={status}"
    if result.get("agents", {}).get("A5") is not None and status == "INSUFFICIENT_WINDOWS":
        return False, "A5 ran despite INSUFFICIENT_WINDOWS"
    if isinstance(result.get("drift_summary"), dict):
        return True, f"status={status} drift_summary=present"
    if status in ("INSUFFICIENT_WINDOWS", "INSUFFICIENT_DATA"):
        infra = result.get("infrastructure") or {}
        healthy = infra.get("infrastructure_healthy", True)
        if healthy is False:
            return False, f"infrastructure_healthy={healthy}"
        return True, f"status={status} infra_ok pipeline_partial"
    return False, f"drift_summary missing for status={status}"


def run_smoke() -> int:
    worm_dir = _worm_root()
    paths = ensure_smoke_worms(worm_dir)
    orch = _orch()
    cfg = orch.infra_gates
    scenarios: List[Dict[str, Any]] = []
    failed = 0

    print(f"infra_gates enabled={cfg.enabled} G0={cfg.g0_max_price_change_pct}% G25={cfg.g25_max_latency_ms}ms")
    print(f"worm_dir={worm_dir} audit_dir={_audit_dir()}")

    crash_result = orch.run_cycle(
        worm_path=paths["flash_crash"],
        symbol="BTCUSDC",
        cycle_id="SMOKE-FLASH",
        write_audit=True,
    )
    crash_path = _write_audit("flash_crash", crash_result)
    ok, detail = _assert_flash_block(crash_result)
    scenarios.append(
        {
            "id": "flash_crash",
            "worm": str(paths["flash_crash"]),
            "passed": ok,
            "detail": detail,
            "audit_file": str(crash_path),
        }
    )
    print(f"{'PASS' if ok else 'FAIL'} flash_crash — {detail} (audit: {crash_path})")
    if not ok:
        failed += 1

    valid_result = orch.run_cycle(
        worm_path=paths["valid_ticks"],
        symbol="BTCUSDC",
        cycle_id="SMOKE-VALID",
        write_audit=False,
    )
    valid_path = _write_audit("valid_ticks", valid_result)
    ok, detail = _assert_valid_pass(valid_result)
    scenarios.append(
        {
            "id": "valid_ticks",
            "worm": str(paths["valid_ticks"]),
            "passed": ok,
            "detail": detail,
            "audit_file": str(valid_path),
        }
    )
    print(f"{'PASS' if ok else 'FAIL'} valid_ticks — {detail} (audit: {valid_path})")
    if not ok:
        failed += 1

    mode = os.environ.get("SWARM_SMOKE_MODE", "all").strip().lower()
    if mode in ("latency", "all"):
        lat_worm = worm_dir / "latency_spike.jsonl"
        write_signal_worm(
            lat_worm,
            stable_prices(70),
            transport_meta={"m7_latency_ms": 600, "seq_num": 1},
        )
        lat_result = orch.run_cycle(
            worm_path=lat_worm,
            symbol="BTCUSDC",
            cycle_id="SMOKE-LATENCY",
            write_audit=False,
        )
        lat_path = _write_audit("latency_spike", lat_result)
        lat_ok = (
            lat_result.get("status") == "INFRASTRUCTURE_BLOCKED"
            and "A25_BLOCKED" in str((lat_result.get("infrastructure") or {}).get("g25_transport_boundary", ""))
        )
        lat_detail = (lat_result.get("infrastructure") or {}).get("g25_transport_boundary", lat_result.get("status"))
        scenarios.append(
            {
                "id": "latency_spike",
                "worm": str(lat_worm),
                "passed": lat_ok,
                "detail": lat_detail,
                "audit_file": str(lat_path),
            }
        )
        print(f"{'PASS' if lat_ok else 'FAIL'} latency_spike — {lat_detail} (audit: {lat_path})")
        if not lat_ok:
            failed += 1

    report = {
        "schema": "regime_swarm_infra_smoke_v1",
        "ts": _now(),
        "charter": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
        "infra_gates": {
            "enabled": cfg.enabled,
            "g0_max_price_change_pct": cfg.g0_max_price_change_pct,
            "g25_max_latency_ms": cfg.g25_max_latency_ms,
        },
        "scenarios": scenarios,
        "passed": sum(1 for s in scenarios if s["passed"]),
        "failed": failed,
    }
    summary_path = _write_audit("summary", report)
    print(json.dumps(report, indent=2))
    print(f"summary: {summary_path}")

    if failed:
        print(f"VERDICT: REGIME_SWARM_INFRA_SMOKE_FAIL ({failed})")
        return 1
    print("VERDICT: REGIME_SWARM_INFRA_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
