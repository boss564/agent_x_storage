#!/usr/bin/env python3
"""Helm pod smoke — infra gates E2E inside cluster (ConfigMap env + audit).

Runs in the regime-swarm image (Job / helm test hook). Wraps
scripts/run_regime_swarm_infra_smoke.run_smoke() and verifies ConfigMap G0
propagation: −15% borderline tick must block or pass per infra_gates.g0_max_price_change_pct.

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_swarm.gates.config import InfraGatesConfig  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.orchestrator import RegimeSwarmOrchestrator  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.worm_fixtures import (  # noqa: E402
    borderline_flash_prices,
    write_signal_worm,
)

sys.path.insert(0, str(_ROOT / "scripts"))
import run_regime_swarm_infra_smoke as _infra_smoke  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _config_snapshot() -> Dict[str, Any]:
    cfg = InfraGatesConfig.from_env()
    return {
        "from_infra_gates_config": {
            "enabled": cfg.enabled,
            "g0_max_price_change_pct": cfg.g0_max_price_change_pct,
            "g0_max_spread_pct": cfg.g0_max_spread_pct,
            "g25_max_latency_ms": cfg.g25_max_latency_ms,
        },
        "raw_env": {
            "SWARM_INFRA_GATES_ENABLED": os.environ.get("SWARM_INFRA_GATES_ENABLED"),
            "SWARM_G0_MAX_PRICE_CHANGE_PCT": os.environ.get("SWARM_G0_MAX_PRICE_CHANGE_PCT"),
            "SWARM_G0_MAX_SPREAD_PCT": os.environ.get("SWARM_G0_MAX_SPREAD_PCT"),
            "SWARM_G25_MAX_LATENCY_MS": os.environ.get("SWARM_G25_MAX_LATENCY_MS"),
            "POD_NAME": os.environ.get("POD_NAME"),
            "POD_NAMESPACE": os.environ.get("POD_NAMESPACE"),
        },
    }


def _prepare_paths() -> Tuple[Path, Path]:
    worm_dir = Path(os.environ.get("SWARM_SMOKE_WORM_DIR", "/data/worm/smoke"))
    audit_dir = Path(os.environ.get("SWARM_SMOKE_AUDIT_DIR", "/data/audit/smoke"))
    worm_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SWARM_SMOKE_WORM_DIR"] = str(worm_dir)
    os.environ["SWARM_SMOKE_AUDIT_DIR"] = str(audit_dir)
    return worm_dir, audit_dir


_BORDERLINE_DROP_PCT = 0.15


def _run_configmap_propagation(worm_dir: Path) -> Tuple[bool, str, Dict[str, Any]]:
    """−15% tick enforced via ConfigMap G0 (no internal threshold override)."""
    cfg = InfraGatesConfig.from_env()
    g0 = cfg.g0_max_price_change_pct
    drop_pct = _BORDERLINE_DROP_PCT
    expect_block = drop_pct * 100.0 > g0

    borderline = worm_dir / "borderline_15pct.jsonl"
    write_signal_worm(borderline, borderline_flash_prices(drop_pct=drop_pct))

    orch = RegimeSwarmOrchestrator(infra_gates=cfg)
    result = orch.run_cycle(
        worm_path=borderline,
        symbol="BTCUSDC",
        cycle_id="POD-SMOKE-G0-PROP",
        write_audit=False,
    )
    status = result.get("status")
    infra = result.get("infrastructure") or {}
    infra_ok = bool(infra.get("infrastructure_healthy"))
    blocked = status == "INFRASTRUCTURE_BLOCKED"

    meta: Dict[str, Any] = {
        "g0_max_price_change_pct": g0,
        "borderline_drop_pct": drop_pct * 100.0,
        "expect_infra_block": expect_block,
        "status": status,
        "infrastructure_healthy": infra_ok,
        "g0_core_sanity": infra.get("g0_core_sanity"),
    }

    if expect_block:
        if not blocked:
            return False, f"G0={g0}: expected INFRASTRUCTURE_BLOCKED for -{drop_pct*100:.0f}%", meta
        detail = f"propagation: G0={g0} -{drop_pct*100:.0f}% → BLOCK (enforced)"
    else:
        if blocked:
            return False, f"G0={g0}: unexpected INFRASTRUCTURE_BLOCKED for -{drop_pct*100:.0f}%", meta
        detail = f"propagation: G0={g0} -{drop_pct*100:.0f}% → infra_ok (enforced)"

    return True, detail, meta


def main() -> int:
    worm_dir, audit_dir = _prepare_paths()
    config = _config_snapshot()
    print(f"helm_pod_smoke start ts={_now()}")
    print(json.dumps(config, indent=2))

    failed = 0
    smoke_code = _infra_smoke.run_smoke()
    if smoke_code != 0:
        failed += 1

    smoke_summary_path = audit_dir / "summary.json"
    smoke_summary: Dict[str, Any] = {}
    if smoke_summary_path.is_file():
        smoke_summary = json.loads(smoke_summary_path.read_text(encoding="utf-8"))

    propagation: Dict[str, Any] = {"skipped": True}
    if _env_bool("HELM_POD_SMOKE_PROPAGATION_TEST", _env_bool("HELM_POD_SMOKE_THRESHOLD_TEST", True)):
        ok, detail, meta = _run_configmap_propagation(worm_dir)
        propagation = {"skipped": False, "passed": ok, "detail": detail, **meta}
        print(f"{'PASS' if ok else 'FAIL'} configmap_propagation — {detail}")
        if not ok:
            failed += 1

    pod_summary = {
        "schema": "regime_swarm_helm_pod_smoke_v1",
        "ts": _now(),
        "charter": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
        "config": config,
        "smoke_summary": smoke_summary,
        "propagation_test": propagation,
        "threshold_test": propagation,  # legacy alias
        "failed": failed,
        "status": "PASS" if failed == 0 else "FAIL",
    }
    out_path = Path(os.environ.get("HELM_POD_SMOKE_SUMMARY", "/data/audit/pod_smoke_summary.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pod_summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(pod_summary, indent=2))
    print(f"pod_smoke_summary: {out_path}")

    if failed:
        print(f"VERDICT: HELM_POD_SMOKE_FAIL ({failed})")
        return 1
    print("VERDICT: HELM_POD_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
