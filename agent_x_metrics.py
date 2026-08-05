"""
Agent X — Prometheus Metrics Exporter.

Exportiert alle 36 Agenten-Metriken als Prometheus-Gauges.
HTTP-Endpoint /metrics für Prometheus-Scraping.

Metriken sind in 5 Gruppen organisiert:
  agent_x_consensus_*     Klasse A — Konsensus & Determinismus
  agent_x_pressure_*      Klasse B — Druckventile (MEV, Gas)
  agent_x_lending_*       Klasse C — Lending & Risiko
  agent_x_defi_*          Klasse D — DeFi-Events
  agent_x_orchestrator_*  Global State + Decision Matrix

Usage:
  python3 agent_x_metrics.py [--port 9090] [--interval 12]

Integriert mit SymbolicsAgent für Echtzeit-Metrik-Collection.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

logger = logging.getLogger("agent_x_metrics")

# ─── Prometheus-Client (embedded — keine externen Abhängigkeiten) ────

class PrometheusRegistry:
    """Minimaler Prometheus-Registry ohne prometheus_client-Abhängigkeit."""

    def __init__(self):
        self._gauges: dict[str, "Gauge"] = {}
        self._counters: dict[str, "Counter"] = {}
        self._histograms: dict[str, "Histogram"] = {}

    def gauge(self, name: str, help_text: str, labels: list[str] | None = None) -> "Gauge":
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, help_text, labels or [])
        return self._gauges[name]

    def counter(self, name: str, help_text: str, labels: list[str] | None = None) -> "Counter":
        if name not in self._counters:
            self._counters[name] = Counter(name, help_text, labels or [])
        return self._counters[name]

    def histogram(self, name: str, help_text: str, labels: list[str] | None = None,
                  buckets: list[float] | None = None) -> "Histogram":
        if name not in self._histograms:
            self._histograms[name] = Histogram(name, help_text, labels or [], buckets)
        return self._histograms[name]

    def render(self) -> str:
        lines = []
        for g in self._gauges.values():
            lines.append(g.render())
        for c in self._counters.values():
            lines.append(c.render())
        for h in self._histograms.values():
            lines.append(h.render())
        return "\n".join(lines) + "\n"


class Gauge:
    def __init__(self, name, help_text, labels):
        self.name = name
        self.help_text = help_text
        self._values: dict[tuple, float] = {}  # label_tuple → value

    def set(self, value: float, label_values: dict | None = None):
        key = tuple(sorted((label_values or {}).items()))
        self._values[key] = value

    def labels(self, **kwargs) -> "GaugeChild":
        return GaugeChild(self, kwargs)

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        for label_tuple, value in self._values.items():
            if label_tuple:
                label_str = ",".join(f'{k}="{v}"' for k, v in label_tuple)
                lines.append(f"{self.name}{{{label_str}}} {value}")
            else:
                lines.append(f"{self.name} {value}")
        return "\n".join(lines)


class GaugeChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def set(self, value: float):
        self.parent.set(value, self.labels)

    def inc(self, amount: float = 1.0):
        key = tuple(sorted(self.labels.items()))
        self.parent._values[key] = self.parent._values.get(key, 0) + amount

    def dec(self, amount: float = 1.0):
        self.inc(-amount)


class Counter:
    def __init__(self, name, help_text, labels):
        self.name = name
        self.help_text = help_text
        self._values: dict[tuple, float] = {}

    def inc(self, amount: float = 1.0, label_values: dict | None = None):
        key = tuple(sorted((label_values or {}).items()))
        self._values[key] = self._values.get(key, 0) + amount

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        for label_tuple, value in self._values.items():
            if label_tuple:
                label_str = ",".join(f'{k}="{v}"' for k, v in label_tuple)
                lines.append(f"{self.name}{{{label_str}}} {value}")
            else:
                lines.append(f"{self.name} {value}")
        return "\n".join(lines)


class Histogram:
    def __init__(self, name, help_text, labels, buckets=None):
        self.name = name
        self.help_text = help_text
        self._buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        self._observations: list[float] = []
        self._sum = 0.0
        self._count = 0

    def observe(self, value: float):
        self._observations.append(value)
        self._sum += value
        self._count += 1

    def render(self) -> str:
        if not self._observations:
            return f"# HELP {self.name} {self.help_text}\n# TYPE {self.name} histogram"
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]

        # Bucket counts
        for b in self._buckets:
            count = sum(1 for o in self._observations if o <= b)
            lines.append(f'{self.name}_bucket{{le="{b}"}} {count}')
        lines.append(f'{self.name}_bucket{{le="+Inf"}} {self._count}')
        lines.append(f"{self.name}_sum {self._sum}")
        lines.append(f"{self.name}_count {self._count}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# AGENT X METRICS
# ═══════════════════════════════════════════════════════════════════════

class AgentXMetrics:
    """Sammelt und exportiert alle Agent-X-Metriken.

    Usage:
        metrics = AgentXMetrics()
        metrics.collect_from_orchestrator(decision)
        print(metrics.registry.render())
    """

    def __init__(self):
        self.registry = PrometheusRegistry()
        self._register_all_metrics()

    def _register_all_metrics(self):
        r = self.registry

        # ─── Klasse A: Konsensus ─────────────────────────────────────
        r.gauge("agent_x_consensus_health_index", "Consensus Health Index (0-100)", ["network"])
        r.gauge("agent_x_consensus_participation_rate", "Network participation rate (0-1)")
        r.gauge("agent_x_consensus_exit_queue_length", "Validator exit queue length")
        r.gauge("agent_x_consensus_reorg_depth", "Current reorg depth in slots")
        r.gauge("agent_x_consensus_finality_status", "Finality status (0=delayed, 1=on_time)")
        r.gauge("agent_x_consensus_trusted_validators", "Number of trusted validators available")

        # ─── Klasse B: Druckventile ──────────────────────────────────
        r.gauge("agent_x_pressure_gas_index", "Gas Stress Index (0-100)")
        r.gauge("agent_x_pressure_mev_index", "MEV Pressure Index (0-100)")
        r.gauge("agent_x_pressure_block_index", "Block Pressure Index (0-100)")
        r.gauge("agent_x_pressure_combined", "Combined Pressure Index (0-100)")
        r.gauge("agent_x_pressure_basefee_gwei", "Current basefee in gwei")
        r.gauge("agent_x_pressure_priority_fee_p95", "Priority Fee P95 in gwei")
        r.gauge("agent_x_pressure_mev_spike", "MEV Spike detected (0/1)")
        r.gauge("agent_x_pressure_level", "Pressure level (0=low to 4=extreme)")

        # ─── Klasse C: Lending ───────────────────────────────────────
        r.gauge("agent_x_lending_users_tracked", "Users tracked by position ledger")
        r.gauge("agent_x_lending_positions_at_risk", "Positions at risk (HF 1.0-1.5)")
        r.gauge("agent_x_lending_positions_liquidatable", "Positions liquidatable (HF <= 1.0)")
        r.gauge("agent_x_lending_worst_health_factor", "Worst health factor across all users")
        r.gauge("agent_x_lending_critical_hf_threshold", "Effective critical HF threshold")

        # ─── Klasse D: DeFi ──────────────────────────────────────────
        r.gauge("agent_x_defi_flash_loan_opportunities", "Flash loan opportunities detected")
        r.gauge("agent_x_defi_flash_loan_profitable", "Profitable flash loan opportunities")
        r.gauge("agent_x_defi_cross_pool_opportunities", "Cross-pool arbitrage opportunities")
        r.gauge("agent_x_defi_cross_chain_opportunities", "Cross-chain arbitrage opportunities")
        r.gauge("agent_x_defi_total_potential_profit_usd", "Total potential profit in USD")
        r.gauge("agent_x_defi_mempool_bots", "MEV bots detected in mempool")

        # ─── Orchestrator ────────────────────────────────────────────
        r.gauge("agent_x_orchestrator_global_state_score", "Global state score (0-100)")
        r.gauge("agent_x_orchestrator_all_clear", "All-clear signal (0/1)")
        r.gauge("agent_x_orchestrator_capital_usd", "Available capital in USD")
        r.counter("agent_x_orchestrator_decisions_total", "Total decisions made")
        r.counter("agent_x_orchestrator_errors_total", "Total orchestrator errors")

        # ─── Klasse E: Governance & Timelocks ──────────────────────
        r.gauge("agent_x_governance_timelock_pending", "Pending timelock actions", ["protocol"])
        r.gauge("agent_x_governance_vesting_unlock_usd", "Expected token unlock volume USD (24h)")
        r.gauge("agent_x_governance_active_proposals", "Active governance proposals")
        r.gauge("agent_x_governance_high_impact_count", "High-impact pending actions")

        # ─── Klasse F: Sentiment & Whales ───────────────────────────
        r.gauge("agent_x_sentiment_score", "Aggregated sentiment score (-100..+100)", ["source"])
        r.gauge("agent_x_sentiment_market_mood", "Market mood (0=capitulation..4=euphoric)")
        r.gauge("agent_x_whale_netflow_usd", "Net exchange flow USD (positive=accumulation)")
        r.gauge("agent_x_whale_movements_24h", "Large whale movements in 24h")

        # ─── Histograms ───────────────────────────────────────────────
        r.histogram("agent_x_pressure_gas_history", "Gas pressure history",
                    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        r.histogram("agent_x_pressure_mev_history", "MEV pressure history",
                    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        r.histogram("agent_x_lending_hf_distribution", "Health factor distribution",
                    buckets=[0.5, 0.75, 1.0, 1.05, 1.1, 1.25, 1.5, 2.0, 5.0])
        r.histogram("agent_x_defi_profit_distribution", "Profit distribution per opportunity",
                    buckets=[10, 50, 100, 250, 500, 1000, 5000])

    # ─── Collect ─────────────────────────────────────────────────────

    def collect_from_orchestrator(self, decision: dict):
        """Extrahiert Metriken aus einer Orchestrator-Entscheidung."""
        r = self.registry
        sig = decision.get("class_signals", {})
        ud = decision.get("unified_decision", {})

        # Klasse A
        a = sig.get("klasse_a_consensus", {}).get("health_detail", {})
        if a:
            r.gauge("agent_x_consensus_health_index", "").set(a.get("chi", 0))
            r.gauge("agent_x_consensus_participation_rate", "").set(a.get("participation", 0))
            r.gauge("agent_x_consensus_exit_queue_length", "").set(
                sig.get("klasse_a_consensus", {}).get("exit_queue_stress", False) and 1000 or 50)
            r.gauge("agent_x_consensus_reorg_depth", "").set(a.get("reorg_depth", 0))
            r.gauge("agent_x_consensus_finality_status", "").set(
                1.0 if a.get("finality") == "on_time" else 0.0)

        # Klasse B: Druckventile
        b = sig.get("klasse_b_druckventile", {})
        if b:
            r.gauge("agent_x_pressure_gas_index", "").set(b.get("gas_pressure_index", 0))
            r.gauge("agent_x_pressure_mev_index", "").set(b.get("mev_pressure_index", 0))
            r.gauge("agent_x_pressure_block_index", "").set(b.get("block_pressure_index", 0))
            r.gauge("agent_x_pressure_combined", "").set(b.get("combined_pressure_index", 0))
            r.gauge("agent_x_pressure_basefee_gwei", "").set(b.get("basefee_current_gwei", 0))
            r.gauge("agent_x_pressure_priority_fee_p95", "").set(b.get("priority_fee_p95_gwei", 0))
            r.gauge("agent_x_pressure_mev_spike", "").set(1.0 if b.get("mev_spike_detected") else 0.0)
            level_map = {"low": 0, "moderate": 1, "elevated": 2, "high": 3, "extreme": 4}
            r.gauge("agent_x_pressure_level", "").set(level_map.get(b.get("pressure_level", "low"), 0))

            # Histograms
            r.histogram("agent_x_pressure_gas_history", "").observe(b.get("gas_pressure_index", 0))
            r.histogram("agent_x_pressure_mev_history", "").observe(b.get("mev_pressure_index", 0))

        # Klasse C: Lending
        c = sig.get("klasse_c_lending", {})
        if c:
            r.gauge("agent_x_lending_users_tracked", "").set(c.get("users_tracked", 0))
            r.gauge("agent_x_lending_positions_at_risk", "").set(c.get("at_risk", 0))
            r.gauge("agent_x_lending_positions_liquidatable", "").set(c.get("liquidatable", 0))
            w = c.get("worst_hf", float("inf"))
            r.gauge("agent_x_lending_worst_health_factor", "").set(
                w if w != float("inf") else 999.0)
            r.gauge("agent_x_lending_critical_hf_threshold", "").set(
                c.get("critical_hf_adjusted", 1.05))
            if w != float("inf"):
                r.histogram("agent_x_lending_hf_distribution", "").observe(w)

        # Klasse D: DeFi
        d = sig.get("klasse_d_defi", {})
        if d:
            r.gauge("agent_x_defi_flash_loan_opportunities", "").set(
                d.get("flash_loan_opportunities", 0))
            r.gauge("agent_x_defi_flash_loan_profitable", "").set(
                d.get("flash_loan_profitable", 0))
            r.gauge("agent_x_defi_cross_pool_opportunities", "").set(
                d.get("cross_pool_opportunities", 0))
            r.gauge("agent_x_defi_cross_chain_opportunities", "").set(
                d.get("cross_chain_opportunities", 0))
            profit = d.get("total_potential_profit_usd", 0)
            r.gauge("agent_x_defi_total_potential_profit_usd", "").set(profit)
            r.gauge("agent_x_defi_mempool_bots", "").set(d.get("mempool_bots", 0))
            if profit > 0:
                r.histogram("agent_x_defi_profit_distribution", "").observe(profit)

        # Klasse E: Governance & Timelocks
        e = sig.get("klasse_e_longterm", {})
        if e:
            r.gauge("agent_x_governance_timelock_pending", "").set(
                e.get("pending_timelocks", 0))
            r.gauge("agent_x_governance_vesting_unlock_usd", "").set(
                e.get("total_unlock_volume_usd", 0))
            r.gauge("agent_x_governance_active_proposals", "").set(
                e.get("active_proposals", 0))
            r.gauge("agent_x_governance_high_impact_count", "").set(
                e.get("high_impact_timelocks", 0))

        # Klasse F: Sentiment & Whales
        f_sig = sig.get("klasse_f_sentiment_whale", {})
        if f_sig:
            # Sentiment ist embedded in F2-1 Aggregator — hier Default-Werte
            r.gauge("agent_x_sentiment_score", "").set(0)  # Default, wird extern gefüllt
            r.gauge("agent_x_whale_movements_24h", "").set(0)

        # Orchestrator
        r.gauge("agent_x_orchestrator_global_state_score", "").set(
            ud.get("global_state_score", 0))
        sc = ud.get("scenario", {})
        r.gauge("agent_x_orchestrator_all_clear", "").set(
            1.0 if sc.get("all_clear") else 0.0)
        r.gauge("agent_x_orchestrator_capital_usd", "").set(
            decision.get("capital", 0))
        r.counter("agent_x_orchestrator_decisions_total", "").inc()

    def collect_error(self):
        self.registry.counter("agent_x_orchestrator_errors_total", "").inc()

    def render(self) -> str:
        return self.registry.render()


# ═══════════════════════════════════════════════════════════════════════
# PROMETHEUS HTTP ENDPOINT
# ═══════════════════════════════════════════════════════════════════════

class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP Handler für /metrics Endpoint."""
    metrics_instance: Optional[AgentXMetrics] = None

    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            if MetricsHandler.metrics_instance:
                self.wfile.write(MetricsHandler.metrics_instance.render().encode())
            else:
                self.wfile.write(b"# Agent X Metrics not initialized\n")
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_html_index().encode())
        else:
            self.send_response(404)
            self.end_headers()


def _html_index():
    return """<!DOCTYPE html>
<html><head><title>Agent X Metrics</title>
<meta charset="utf-8"><style>
body{font-family:monospace;background:#0a0a0a;color:#e0e0e0;padding:20px}
.metric{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1a1a1a}
.metric .value{color:#00ff88;font-weight:bold}
h2{color:#4488ff;margin-top:30px}
</style></head><body>
<h1>Agent X — Metrics Endpoint</h1>
<p><a href="/metrics">/metrics</a> — Prometheus Scrape Target</p>
<p><a href="/health">/health</a> — Health Check</p>
<p style="color:#888">Refresh for live metrics. Configure Prometheus to scrape every 12s.</p>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════
# METRIC COLLECTOR (Background Thread)
# ═══════════════════════════════════════════════════════════════════════

class MetricCollector:
    """Hintergrund-Thread: Sammelt periodisch Metriken vom Orchestrator."""

    def __init__(self, interval: int = 12, port: int = 9090):
        self.interval = interval
        self.port = port
        self.metrics = AgentXMetrics()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()

        # HTTP Server im Haupt-Thread
        MetricsHandler.metrics_instance = self.metrics
        server = HTTPServer(("0.0.0.0", self.port), MetricsHandler)
        logger.info(f"Prometheus /metrics auf Port {self.port} — http://localhost:{self.port}/metrics")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            self._running = False
            server.shutdown()

    def _collect_loop(self):
        while self._running:
            try:
                from agent_x_orchestrator import run_full_evaluation
                decision = run_full_evaluation()
                self.metrics.collect_from_orchestrator(decision)
                logger.debug("Metriken aktualisiert: %d Gauges, Score=%s",
                             len(self.metrics.registry._gauges),
                             decision.get("unified_decision", {}).get("global_state_score", "?"))
            except Exception as e:
                logger.error("Metric-Collection Fehler: %s", e)
                self.metrics.collect_error()
            time.sleep(self.interval)


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import argparse
    parser = argparse.ArgumentParser(description="Agent X — Prometheus Metrics Exporter")
    parser.add_argument("--port", type=int, default=9090, help="HTTP Port (default: 9090)")
    parser.add_argument("--interval", type=int, default=12, help="Collect interval in seconds (default: 12)")
    parser.add_argument("--once", action="store_true", help="Run once and print metrics")
    args = parser.parse_args()

    if args.once:
        # Einmalige Ausgabe
        metrics = AgentXMetrics()
        from agent_x_orchestrator import run_full_evaluation
        decision = run_full_evaluation()
        metrics.collect_from_orchestrator(decision)
        print(metrics.render())
    else:
        collector = MetricCollector(interval=args.interval, port=args.port)
        collector.start()
