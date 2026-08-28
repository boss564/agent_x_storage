#!/usr/bin/env python3
"""Infrastructure gates (A0 / A2.5) — WORM flash-crash + transport latency."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

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


def main() -> int:
    failed = 0
    cfg = InfraGatesConfig(
        enabled=True,
        g0_max_price_change_pct=20.0,
        g0_max_spread_pct=5.0,
        g25_max_latency_ms=500.0,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        crash_path = root / "flash_crash.jsonl"
        crash_prices = stable_prices(69, 100.0) + [50.0]
        write_signal_worm(crash_path, crash_prices)
        crash_result = RegimeSwarmOrchestrator(infra_gates=cfg).run_cycle(
            worm_path=crash_path,
            symbol="BTCUSDC",
            write_audit=False,
        )
        if crash_result.get("status") != "INFRASTRUCTURE_BLOCKED":
            print(f"FAIL A0 flash crash: status={crash_result.get('status')}")
            failed += 1
        elif "drift_summary" in crash_result and crash_result["drift_summary"] != "NOT_COMPUTED":
            print("FAIL A0 flash crash: drift_summary computed")
            failed += 1
        elif crash_result.get("agents", {}).get("A5") is not None:
            print("FAIL A0 flash crash: A5 ran")
            failed += 1
        else:
            print("PASS A0 flash crash blocks before A3–A8")

        ok_path = root / "stable.jsonl"
        write_signal_worm(ok_path, stable_prices(70))
        ok_result = RegimeSwarmOrchestrator(infra_gates=cfg).run_cycle(
            worm_path=ok_path,
            symbol="BTCUSDC",
            write_audit=False,
        )
        if ok_result.get("status") == "INFRASTRUCTURE_BLOCKED":
            print(f"FAIL stable worm blocked: {ok_result.get('infrastructure')}")
            failed += 1
        elif ok_result.get("status") not in ("COMPLETE", "INSUFFICIENT_WINDOWS"):
            print(f"FAIL stable worm unexpected status: {ok_result.get('status')}")
            failed += 1
        else:
            print(f"PASS stable worm status={ok_result.get('status')}")

        lat_path = root / "latency.jsonl"
        write_signal_worm(
            lat_path,
            stable_prices(70),
            transport_meta={"m7_latency_ms": 600, "seq_num": 1},
        )
        lat_result = RegimeSwarmOrchestrator(infra_gates=cfg).run_cycle(
            worm_path=lat_path,
            symbol="BTCUSDC",
            write_audit=False,
        )
        if lat_result.get("status") != "INFRASTRUCTURE_BLOCKED":
            print(f"FAIL A2.5 latency: status={lat_result.get('status')}")
            failed += 1
        else:
            g25 = (lat_result.get("infrastructure") or {}).get("g25_transport_boundary", "")
            if "A25_BLOCKED" not in str(g25):
                print(f"FAIL A2.5 latency message: {g25}")
                failed += 1
            else:
                print("PASS A2.5 latency spike blocks cycle")

    if failed:
        print(f"INFRASTRUCTURE_GATES_FAIL ({failed})")
        return 1
    print("INFRASTRUCTURE_GATES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
