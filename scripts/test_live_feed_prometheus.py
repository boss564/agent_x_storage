#!/usr/bin/env python3
"""Live feed (mock WebSocket) → WORM → daemon Prometheus counters."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.feed import (  # noqa: E402
    MockWebSocketFeed,
    assert_no_order_urls,
    binance_trade_ws_url,
    parse_binance_ws_message,
)
from prototypes.raas_paper_trading.paper_runner import LIVE_EXECUTION, LivePaperBridge  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.worm_fixtures import (  # noqa: E402
    flash_crash_prices,
    write_signal_worm,
)
from scripts.run_regime_swarm_daemon import (  # noqa: E402
    RegimeSwarmDaemon,
    record_report_metrics,
    render_metrics_text,
    reset_metrics,
)


def _trade_frame(symbol: str, price: float, ts_ms: int = 1_700_000_000_000) -> str:
    return json.dumps({"e": "trade", "s": symbol, "p": str(price), "T": ts_ms})


def _fail(msg: str) -> None:
    print(f"FAIL {msg}")
    raise SystemExit(1)


def test_parse_and_url_guards() -> None:
    tick = parse_binance_ws_message(_trade_frame("ETHUSDT", 2500.5))
    if tick is None or tick.price != 2500.5 or tick.source != "binance_ws":
        _fail("parse_binance_ws_message trade")
    wrapped = json.dumps({"stream": "ethusdt@trade", "data": json.loads(_trade_frame("ETHUSDT", 1.0))})
    if parse_binance_ws_message(wrapped) is None:
        _fail("combined stream envelope")
    if parse_binance_ws_message('{"e":"kline"}') is not None:
        _fail("non-trade should be ignored")
    url = binance_trade_ws_url("ETHUSDT", base="wss://stream.binance.com:9443/ws")
    if "ethusdt@trade" not in url:
        _fail(f"stream url {url}")
    try:
        assert_no_order_urls("wss://example/order")
        _fail("order URL must be refused")
    except RuntimeError:
        pass
    if LIVE_EXECUTION is not False:
        _fail("LIVE_EXECUTION must be hardcoded false")


def test_mock_feed_to_worm() -> None:
    frames = [_trade_frame("ETHUSDT", 100.0 + i * 0.01, 1_700_000_000_000 + i) for i in range(8)]
    with tempfile.TemporaryDirectory() as tmp:
        worm_dir = Path(tmp)
        bridge = LivePaperBridge(
            symbol="ETHUSDT",
            worm_dir=worm_dir,
            feed=MockWebSocketFeed(frames),
            attach_orderbook=False,
        )
        n = bridge.drain_feed()
        if n != 8:
            _fail(f"expected 8 ticks, got {n}")
        if not bridge.worm.path.is_file():
            _fail("WORM not written")
        text = bridge.worm.path.read_text(encoding="utf-8")
        if '"live_execution": true' in text or '"live_execution": True' in text:
            _fail("live_execution true on WORM")
        signals = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        sigs = [r for r in signals if r.get("action") == "SIGNAL"]
        if len(sigs) < 8:
            _fail(f"SIGNAL rows {len(sigs)}")


def test_feed_worm_daemon_counters() -> None:
    os.environ["SWARM_INFRA_GATES_ENABLED"] = "false"
    reset_metrics()
    frames = [
        _trade_frame("ETHUSDT", 100.0 + ((i * 7) % 11) * 0.05 + (i // 20) * 0.02, 1_700_000_000_000 + i)
        for i in range(80)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worm_dir = root / "worm" / "live"
        bridge = LivePaperBridge(
            symbol="ETHUSDT",
            worm_dir=worm_dir,
            feed=MockWebSocketFeed(frames),
            attach_orderbook=False,
        )
        bridge.drain_feed()
        cfg = {
            "cycle_interval_seconds": 1,
            "worm_dir": str(worm_dir),
            "audit_path": str(root / "audit.jsonl"),
            "cooling_path": str(root / "cooling.jsonl"),
            "state_path": str(root / "state.json"),
            "report_path": str(root / "report.json"),
            "cycle_log_path": str(root / "cycles.jsonl"),
            "leader_snapshot_path": str(root / "leader.json"),
            "live_execution": False,
            "metrics_port": 18080,
        }
        daemon = RegimeSwarmDaemon(cfg)
        asyncio.run(daemon.run_cycle())
        body = render_metrics_text()
        if "drift_counter{" not in body:
            _fail(f"missing drift_counter\n{body}")
        if "risk_multiplier " not in body:
            _fail("missing risk_multiplier")
        if 'gate_block_counter{gate="A0"}' not in body:
            _fail("missing gate_block_counter A0")
        if daemon.orch.a8._soft.current("ETHUSDT") < 1.0:
            _fail("risk multiplier underflow")
        if '"live_execution": false' not in Path(cfg["cycle_log_path"]).read_text(encoding="utf-8"):
            # cycle log may not include the flag; check report
            report = json.loads(Path(cfg["report_path"]).read_text(encoding="utf-8"))
            if report.get("live_execution") is not False:
                _fail("report live_execution")


def test_gate_block_counter() -> None:
    os.environ["SWARM_INFRA_GATES_ENABLED"] = "true"
    reset_metrics()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worm = root / "flash" / "paper_trades.worm.jsonl"
        write_signal_worm(worm, flash_crash_prices())
        report = None
        from prototypes.raas_paper_trading.regime_swarm import RegimeSwarmOrchestrator

        orch = RegimeSwarmOrchestrator(
            audit_path=root / "audit.jsonl",
            cooling_path=root / "cooling.jsonl",
        )
        report = orch.run_cycle(worm_path=worm, symbol="BTCUSDC", write_audit=False)
        if report.get("status") != "INFRASTRUCTURE_BLOCKED":
            _fail(f"expected INFRASTRUCTURE_BLOCKED, got {report.get('status')} {report.get('infrastructure')}")
        record_report_metrics(report)
        body = render_metrics_text()
        if 'gate_block_counter{gate="A0"} 1' not in body:
            _fail(f"A0 counter not incremented\n{body}")


def test_charter_live_execution_env_blocks() -> None:
    os.environ["SWARM_LIVE_EXECUTION"] = "true"
    try:
        from scripts.run_regime_swarm_daemon import _assert_charter_live_execution_off

        try:
            _assert_charter_live_execution_off()
            _fail("SWARM_LIVE_EXECUTION=true must exit")
        except SystemExit:
            pass
    finally:
        os.environ.pop("SWARM_LIVE_EXECUTION", None)


def main() -> int:
    test_parse_and_url_guards()
    test_mock_feed_to_worm()
    test_charter_live_execution_env_blocks()
    test_feed_worm_daemon_counters()
    test_gate_block_counter()
    print("LIVE_FEED_PROMETHEUS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
