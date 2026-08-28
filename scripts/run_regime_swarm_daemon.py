#!/usr/bin/env python3
"""Production daemon — 9-agent regime drift swarm (monitoring only, no order send).

Reads paper WORMs from a mounted volume, runs A1→A9 per symbol on a fixed interval,
writes audit JSON to stdout + file, optional webhook alerts, Prometheus /metrics.

Charter: live_execution=false · DEFENSIVE_CAUSAL_GROUNDING
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_drift import definition_hash, discover_worm_files  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm import RegimeSwarmOrchestrator  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.state_store import SwarmStateStore  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.leader import (  # noqa: E402
    KubernetesLeaseLeader,
    resolve_leader_with_lease,
)
from prototypes.raas_paper_trading.regime_swarm.types import SWARM_SCHEMA  # noqa: E402

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
HEARTBEAT = Path(os.environ.get("SWARM_HEARTBEAT_PATH", "/tmp/swarm_heartbeat"))

_metrics: Dict[str, Any] = {
    "cycles_total": 0,
    "errors_total": 0,
    "last_cycle_ts": "",
    "symbols_processed": 0,
    "last_alert_level": "OK",
    "is_leader": 1,
    "pod_name": "local",
    "pod_ordinal": 0,
    "drift_counter": {},  # (regime, type) -> int
    "gate_block_counter": {"A0": 0, "A2.5": 0},
    "risk_multiplier": 1.0,
}


def reset_metrics() -> None:
    """Test helper — clear labeled counters and gauges."""
    _metrics["cycles_total"] = 0
    _metrics["errors_total"] = 0
    _metrics["last_cycle_ts"] = ""
    _metrics["symbols_processed"] = 0
    _metrics["last_alert_level"] = "OK"
    _metrics["drift_counter"] = {}
    _metrics["gate_block_counter"] = {"A0": 0, "A2.5": 0}
    _metrics["risk_multiplier"] = 1.0


def _prom_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def record_report_metrics(report: Dict[str, Any]) -> None:
    """Update drift / gate / risk gauges from one orchestrator report."""
    status = str(report.get("status") or "")
    infra = report.get("infrastructure") or {}
    if status == "INFRASTRUCTURE_BLOCKED" or infra.get("infrastructure_healthy") is False:
        g0 = str(infra.get("g0_core_sanity") or "")
        g25 = str(infra.get("g25_transport_boundary") or "")
        if "A0_BLOCKED" in g0 or (g0.startswith("A0") and "BLOCKED" in g0):
            _metrics["gate_block_counter"]["A0"] = int(_metrics["gate_block_counter"].get("A0", 0)) + 1
        if "A25_BLOCKED" in g25 or "A2.5" in g25 and "BLOCKED" in g25:
            _metrics["gate_block_counter"]["A2.5"] = int(_metrics["gate_block_counter"].get("A2.5", 0)) + 1
        if "A0_BLOCKED" not in g0 and "A25_BLOCKED" not in g25:
            # fail-closed: count A0 if message mentions block without prefix
            if "BLOCKED" in g0:
                _metrics["gate_block_counter"]["A0"] = int(_metrics["gate_block_counter"].get("A0", 0)) + 1
        return

    summary = report.get("drift_summary")
    if not isinstance(summary, dict):
        return
    regime = str(summary.get("classified_regime") or "UNKNOWN")
    drift_type = str(summary.get("drift_type") or "unknown")
    key = (regime, drift_type)
    counters: Dict[Any, int] = _metrics["drift_counter"]
    counters[key] = int(counters.get(key, 0)) + 1

    swarm = report.get("swarm_message") or {}
    state = swarm.get("strategy_state") or {}
    if "risk_multiplier" in state:
        _metrics["risk_multiplier"] = float(state["risk_multiplier"])


def render_metrics_text() -> str:
    drift_lines = [
        "# HELP drift_counter A7 classified-regime observations",
        "# TYPE drift_counter counter",
    ]
    for (regime, drift_type), count in sorted(_metrics["drift_counter"].items()):
        drift_lines.append(
            f'drift_counter{{regime="{_prom_label(regime)}",type="{_prom_label(drift_type)}"}} {int(count)}'
        )
    if len(drift_lines) == 2:
        drift_lines.append('drift_counter{regime="none",type="none"} 0')

    gate_lines = [
        "# HELP gate_block_counter Infrastructure gate blocks (A0 / A2.5)",
        "# TYPE gate_block_counter counter",
    ]
    for gate, count in sorted(_metrics["gate_block_counter"].items()):
        gate_lines.append(f'gate_block_counter{{gate="{_prom_label(str(gate))}"}} {int(count)}')

    lines = [
        "# HELP swarm_cycles_total Completed daemon cycles",
        "# TYPE swarm_cycles_total counter",
        f"swarm_cycles_total {_metrics['cycles_total']}",
        "# HELP swarm_cycle_errors_total Cycle exceptions",
        "# TYPE swarm_cycle_errors_total counter",
        f"swarm_cycle_errors_total {_metrics['errors_total']}",
        "# HELP swarm_symbols_processed Last cycle symbol count",
        "# TYPE swarm_symbols_processed gauge",
        f"swarm_symbols_processed {_metrics['symbols_processed']}",
        "# HELP swarm_up Daemon heartbeat",
        "# TYPE swarm_up gauge",
        f"swarm_up {1 if HEARTBEAT.is_file() else 0}",
        "# HELP swarm_is_leader 1 if this pod runs the active decision cycle",
        "# TYPE swarm_is_leader gauge",
        f"swarm_is_leader {_metrics['is_leader']}",
        "# HELP swarm_pod_ordinal StatefulSet ordinal",
        "# TYPE swarm_pod_ordinal gauge",
        f"swarm_pod_ordinal {_metrics['pod_ordinal']}",
        *drift_lines,
        "# HELP risk_multiplier A8 current advisory risk multiplier",
        "# TYPE risk_multiplier gauge",
        f"risk_multiplier {float(_metrics['risk_multiplier'])}",
        *gate_lines,
    ]
    return "\n".join(lines) + "\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _data_root() -> Path:
    return Path(os.environ.get("SWARM_DATA_ROOT", "/data"))


def _assert_charter_live_execution_off() -> None:
    """Ebene 1 (ConfigMap) + Ebene 2 (Code): monitoring-only, no order send."""
    if _env_bool("SWARM_LIVE_EXECUTION", False):
        raise SystemExit("SWARM_LIVE_EXECUTION must be false (monitoring-only charter)")


def _load_config(path: Optional[Path]) -> Dict[str, Any]:
    root = _data_root()
    defaults: Dict[str, Any] = {
        "cycle_interval_seconds": int(os.environ.get("CYCLE_INTERVAL_SECONDS", "60")),
        "worm_dir": str(root / "worm" / "paper_runs"),
        "audit_path": str(root / "audit" / "regime_drift_audit.jsonl"),
        "cooling_path": str(root / "state" / "regime_swarm_cooling.jsonl"),
        "state_path": str(root / "state" / "swarm_state.json"),
        "report_path": str(root / "reports" / "regime_drift_latest.json"),
        "cycle_log_path": str(root / "audit" / "regime_swarm_cycles.jsonl"),
        "leader_snapshot_path": str(root / "state" / "leader_snapshot.json"),
        "live_execution": False,
        "metrics_port": int(os.environ.get("SWARM_METRICS_PORT", "8080")),
        "live_feed_enabled": _env_bool("LIVE_FEED_ENABLED", False),
    }
    if defaults["live_feed_enabled"]:
        live_worm = os.environ.get("LIVE_FEED_WORM_DIR", str(root / "worm" / "live"))
        defaults["worm_dir"] = live_worm
    if path and path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in ("cycle_interval_seconds", "live_execution", "metrics_port"):
                    if key in loaded:
                        defaults[key] = loaded[key]
        except (json.JSONDecodeError, OSError):
            pass
    defaults["metrics_port"] = int(os.environ.get("SWARM_METRICS_PORT", defaults["metrics_port"]))
    defaults["live_execution"] = False
    return defaults


def _symbol_from_path(path: Path) -> str:
    joined = path.as_posix().lower()
    for suffix in ("btcusdc", "ethusdc", "solusdc", "ethusdt", "btcusdt"):
        if suffix in joined:
            return suffix.upper()
    if path.name == "paper_trades.worm.jsonl" and path.parent.name:
        return path.parent.name.upper()[:16]
    return path.stem.upper()[:16]


def _emit_stdout_audit(entry: Dict[str, Any]) -> None:
    row = {
        **entry,
        "log_type": "regime_swarm_audit",
        "scope": SCOPE,
        "live_execution": False,
    }
    print(json.dumps(row, default=str), flush=True)


def _post_webhook(url: str, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(json.dumps({"webhook_error": str(exc), "ts": _now()}), flush=True)


class _MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path not in ("/metrics", "/health"):
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        lines = render_metrics_text().rstrip("\n").split("\n")
        body = "\n".join(lines) + "\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _start_metrics_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _MetricsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class RegimeSwarmDaemon:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.interval = float(config["cycle_interval_seconds"])
        self.worm_dir = Path(config["worm_dir"])
        self.report_path = Path(config["report_path"])
        self.cycle_log_path = Path(config["cycle_log_path"])
        self.leader_snapshot_path = Path(config["leader_snapshot_path"])
        self.state_store = SwarmStateStore(Path(config["state_path"]))
        self.orch = RegimeSwarmOrchestrator(
            audit_path=Path(config["audit_path"]),
            cooling_path=Path(config["cooling_path"]),
            seed=int(os.environ.get("SWARM_SEED", "42")),
        )
        self.slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
        self.pagerduty_key = os.environ.get("PAGERDUTY_INTEGRATION_KEY", "").strip()
        self._shutdown = asyncio.Event()
        self._leader_identity, self._lease_leader = resolve_leader_with_lease()
        self.pod_name = self._leader_identity.pod_name
        self.pod_ordinal = self._leader_identity.pod_ordinal
        self.is_leader = self._leader_identity.is_leader
        self.leader_mode = self._leader_identity.mode
        self._lease_renew_interval = float(
            os.environ.get("SWARM_LEASE_RENEW_INTERVAL_SECONDS", "5")
        )
        self._lease_release_done = False
        _metrics["pod_name"] = self.pod_name
        _metrics["pod_ordinal"] = self.pod_ordinal
        _metrics["is_leader"] = 1 if self.is_leader else 0

    def _restore_state(self) -> None:
        self.state_store.load()
        self.state_store.apply_soft_state(self.orch.a8._soft)
        self.state_store.apply_stuck_state(self.orch._stuck)

    def _persist_state(self) -> None:
        if not self.is_leader:
            return
        self.state_store.capture_soft_state(self.orch.a8._soft)
        self.state_store.capture_stuck_state(self.orch._stuck)
        self.state_store.save()

    def _append_cycle_log(self, report: Dict[str, Any]) -> None:
        self.cycle_log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {**report, "logged_at": _now(), "daemon": "regime_swarm"}
        with self.cycle_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def _maybe_alert(self, report: Dict[str, Any]) -> None:
        if not self.is_leader:
            return
        level = str(report.get("alert_level", "OK"))
        if level in ("OK",):
            compliance = (report.get("swarm_message") or {}).get("compliance") or report.get(
                "compliance", {}
            )
            if compliance.get("compliance_alert") != "REVIEW_REQUIRED":
                return
            level = "REVIEW_REQUIRED"
        compliance = (report.get("swarm_message") or {}).get("compliance") or report.get(
            "compliance", {}
        )
        if compliance.get("compliance_alert") == "REVIEW_REQUIRED":
            level = "REVIEW_REQUIRED"
        payload = {
            "text": (
                f"[Regime Swarm] {report.get('symbol')} {level} "
                f"regime={report.get('drift_summary', {}).get('classified_regime')} "
                f"(schema={SWARM_SCHEMA})"
            ),
            "report": {
                "cycle_id": report.get("cycle_id"),
                "alert_level": level,
                "allow_amendment": report.get("drift_summary", {}).get("allow_amendment"),
            },
        }
        if self.slack_url:
            _post_webhook(self.slack_url, payload)
        if self.pagerduty_key and level in ("CRITICAL", "REVIEW_REQUIRED"):
            _post_webhook(
                "https://events.pagerduty.com/v2/enqueue",
                {
                    "routing_key": self.pagerduty_key,
                    "event_action": "trigger",
                    "payload": {
                        "summary": payload["text"],
                        "severity": "critical" if level == "CRITICAL" else "warning",
                        "source": "regime-swarm-daemon",
                    },
                },
            )

    def _write_leader_snapshot(self) -> None:
        if not self.is_leader:
            return
        cooling = self.orch._cooling
        payload = {
            "schema": "raas_leader_snapshot_v1",
            "updated_at": _now(),
            "pod_name": self.pod_name,
            "soft_multipliers": dict(self.orch.a8._soft._current),
            "unreliable_counters": dict(cooling._unreliable) if cooling else {},
            "real_drift_counters": dict(cooling._real) if cooling else {},
        }
        self.leader_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.leader_snapshot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.leader_snapshot_path)

    def _sync_from_leader_snapshot(self) -> None:
        if self.is_leader or not self.leader_snapshot_path.is_file():
            return
        try:
            data = json.loads(self.leader_snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for sym, mult in (data.get("soft_multipliers") or {}).items():
            self.orch.a8._soft._current[str(sym)] = float(mult)

    async def run_standby_tick(self) -> None:
        """Standby pod — heartbeat + metrics only; no A1/A7/A8 mutations."""
        self._sync_from_leader_snapshot()
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(_now(), encoding="utf-8")
        row = {
            "event": "standby_tick",
            "schema": SWARM_SCHEMA,
            "pod_name": self.pod_name,
            "pod_ordinal": self.pod_ordinal,
            "is_leader": False,
            "role": "STANDBY_OBSERVER",
            "ts": _now(),
            "scope": SCOPE,
            "live_execution": False,
        }
        print(json.dumps(row), flush=True)
        _metrics["cycles_total"] += 1
        _metrics["last_cycle_ts"] = _now()
        _metrics["symbols_processed"] = 0
        _metrics["is_leader"] = 0

    async def run_cycle(self) -> None:
        if not self.is_leader:
            await self.run_standby_tick()
            return
        worms = discover_worm_files(self.worm_dir) if self.worm_dir.is_dir() else []
        reports: List[Dict[str, Any]] = []
        for worm in worms:
            sym = _symbol_from_path(worm)
            report = await asyncio.to_thread(
                self.orch.run_cycle,
                worm_path=worm,
                symbol=sym,
                write_audit=True,
            )
            reports.append(report)
            record_report_metrics(report)
            _emit_stdout_audit(report)
            self._append_cycle_log(report)
            self._maybe_alert(report)

        summary = {
            "schema": SWARM_SCHEMA,
            "verdict": "RAAS_REGIME_DRIFT_EMPTY" if not reports else "RAAS_REGIME_DRIFT_PASS",
            "worm_count": len(reports),
            "definition_hash": definition_hash(),
            "diagnostic_only": True,
            "live_execution": False,
            "scope": SCOPE,
            "reports": reports,
            "ts": _now(),
        }
        critical = [r for r in reports if r.get("alert_level", "").startswith("CRITICAL")]
        if critical:
            summary["verdict"] = "RAAS_REGIME_DRIFT_CRITICAL"
        elif any(r.get("alert_level") not in ("OK", None) for r in reports):
            summary["verdict"] = "RAAS_REGIME_DRIFT_WARN"

        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self.report_path.write_text,
            json.dumps(summary, indent=2) + "\n",
            "utf-8",
        )
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(_now(), encoding="utf-8")
        self._persist_state()
        self._write_leader_snapshot()

        _metrics["cycles_total"] += 1
        _metrics["symbols_processed"] = len(reports)
        _metrics["last_cycle_ts"] = _now()
        _metrics["is_leader"] = 1
        if reports:
            _metrics["last_alert_level"] = max(
                reports, key=lambda r: {"OK": 0, "WARNING": 1, "WARNING_PENDING_COOLDOWN": 2, "CRITICAL": 3}.get(
                    str(r.get("alert_level", "OK")), 1
                )
            ).get("alert_level", "OK")

    async def _lease_renewal_loop(self) -> None:
        while not self._shutdown.is_set():
            if self._lease_leader is not None:
                self.is_leader = self._lease_leader.renew()
                _metrics["is_leader"] = 1 if self.is_leader else 0
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=self._lease_renew_interval,
                )
                break
            except asyncio.TimeoutError:
                continue

    async def main_loop(self) -> None:
        self._restore_state()
        lease_task: Optional[asyncio.Task[None]] = None
        if self._lease_leader is not None:
            lease_task = asyncio.create_task(self._lease_renewal_loop())
        print(
            json.dumps(
                {
                    "event": "swarm_daemon_start",
                    "schema": SWARM_SCHEMA,
                    "interval_s": self.interval,
                    "worm_dir": str(self.worm_dir),
                    "definition_hash": definition_hash(),
                    "live_execution": False,
                    "swarm_live_execution_env": os.environ.get("SWARM_LIVE_EXECUTION", ""),
                    "pod_name": self.pod_name,
                    "pod_ordinal": self.pod_ordinal,
                    "is_leader": self.is_leader,
                    "leader_mode": self.leader_mode,
                }
            ),
            flush=True,
        )
        try:
            while not self._shutdown.is_set():
                started = time.perf_counter()
                try:
                    await self.run_cycle()
                except Exception as exc:
                    _metrics["errors_total"] += 1
                    print(
                        json.dumps({"event": "cycle_error", "error": str(exc), "ts": _now()}),
                        flush=True,
                    )
                elapsed = time.perf_counter() - started
                sleep_s = max(0.0, self.interval - elapsed)
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=sleep_s)
                except asyncio.TimeoutError:
                    continue
        finally:
            if lease_task is not None:
                lease_task.cancel()
                try:
                    await lease_task
                except asyncio.CancelledError:
                    pass
            self._release_lease_if_holder()
        self._persist_state()
        print(json.dumps({"event": "swarm_daemon_shutdown", "ts": _now()}), flush=True)

    def _release_lease_if_holder(self) -> None:
        """Release Lease immediately on SIGTERM — do not wait for main_loop finally."""
        if self._lease_release_done or self._lease_leader is None:
            return
        if self._lease_leader.is_holder:
            self._lease_leader.release()
            self.is_leader = False
            _metrics["is_leader"] = 0
        self._lease_release_done = True

    def request_shutdown(self) -> None:
        self._release_lease_if_holder()
        self._shutdown.set()


def _start_live_feed_thread(cfg: Dict[str, Any], stop: asyncio.Event) -> Optional[threading.Thread]:
    if not cfg.get("live_feed_enabled"):
        return None
    from prototypes.raas_paper_trading.paper_runner import LivePaperBridge

    bridge = LivePaperBridge.from_env(worm_dir=Path(cfg["worm_dir"]))
    stop_flag = threading.Event()

    def _watch() -> None:
        while not stop.is_set() and not stop_flag.is_set():
            time.sleep(0.2)
        stop_flag.set()

    threading.Thread(target=_watch, name="live-feed-stop-watch", daemon=True).start()
    return bridge.start_background(stop=stop_flag)


async def _amain(config_path: Optional[Path]) -> int:
    _assert_charter_live_execution_off()
    cfg = _load_config(config_path)
    if cfg.get("live_execution") is True:
        raise SystemExit("live_execution must be false")
    if _env_bool("SWARM_METRICS_ENABLED", True):
        _start_metrics_server(int(cfg.get("metrics_port", 8080)))

    daemon = RegimeSwarmDaemon(cfg)
    loop = asyncio.get_running_loop()
    _start_live_feed_thread(cfg, daemon._shutdown)

    def _on_signal(signum: int) -> None:
        print(json.dumps({"event": "signal", "signum": signum, "ts": _now()}), flush=True)
        daemon.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal, sig)

    await daemon.main_loop()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regime drift swarm production daemon")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("SWARM_CONFIG", "/app/config/regime_swarm.json")),
    )
    args = parser.parse_args(argv)
    config_path = args.config if args.config.is_file() else None
    return asyncio.run(_amain(config_path))


if __name__ == "__main__":
    raise SystemExit(main())
