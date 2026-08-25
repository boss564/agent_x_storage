"""A2 — RPCHealthSentinel (Wave 40 Quadrant 1 / Infra).

Nine subagents: LatencyProbe → SLAEnforcer.
Multi-RPC failover; auto-switch when latency > RESILIENCE_RPC_SWITCH_MS.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agents_b2g.resilience.agents import make_response
from agents_b2g.resilience.config import ResilienceConfig
from agents_b2g.resilience.logging_utils import JSONLogger, _safe_call


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class LatencyProbe:
    """Probe endpoint latencies (ms)."""

    name = "LatencyProbe"

    def run(self, samples_ms: Sequence[float]) -> dict[str, Any]:
        vals = [float(x) for x in samples_ms] or [0.0]
        return {
            "n": len(vals),
            "mean_ms": round(statistics.fmean(vals), 3),
            "p99_ms": round(sorted(vals)[max(0, int(len(vals) * 0.99) - 1)], 3),
            "max_ms": round(max(vals), 3),
            "samples_ms": vals[:32],
        }


class HTTP429Backoff:
    """Compute backoff after HTTP 429 / rate-limit."""

    name = "HTTP429Backoff"

    def run(self, status_codes: Sequence[int], base_s: float = 0.5) -> dict[str, Any]:
        hits = sum(1 for c in status_codes if int(c) == 429)
        backoff_s = round(base_s * (2 ** min(hits, 6)), 3) if hits else 0.0
        return {"rate_limit_hits": hits, "backoff_s": backoff_s, "throttled": hits > 0}


class FallbackRouter:
    """Select fallback endpoint when primary unhealthy."""

    name = "FallbackRouter"

    def run(
        self,
        primary: str,
        candidates: Sequence[str],
        primary_healthy: bool,
    ) -> dict[str, Any]:
        pool = [c for c in candidates if c and c != primary]
        if primary_healthy:
            selected = primary
            reason = "primary_ok"
        elif pool:
            selected = pool[0]
            reason = "failover"
        else:
            selected = primary
            reason = "no_fallback"
        return {
            "selected": selected,
            "reason": reason,
            "failover": reason == "failover",
            "candidates": list(pool),
        }


class MultiRPCEndpointBalancer:
    """Round-robin / least-latency balancer across healthy endpoints."""

    name = "MultiRPCEndpointBalancer"

    def run(
        self,
        endpoints: Sequence[dict[str, Any]],
        prefer_private: bool = True,
    ) -> dict[str, Any]:
        healthy = [e for e in endpoints if e.get("healthy", True)]
        if prefer_private:
            private = [e for e in healthy if e.get("private")]
            pool = private or healthy
        else:
            pool = healthy
        if not pool:
            return {"selected": None, "balanced": False, "pool_size": 0}
        best = min(pool, key=lambda e: float(e.get("latency_ms", 1e9)))
        return {
            "selected": best.get("url"),
            "balanced": True,
            "pool_size": len(pool),
            "private": bool(best.get("private")),
            "latency_ms": float(best.get("latency_ms", 0)),
        }


class TimeoutCircuitBreaker:
    """Open circuit after consecutive timeouts."""

    name = "TimeoutCircuitBreaker"

    def run(self, consecutive_timeouts: int, open_after: int = 3) -> dict[str, Any]:
        open_ = consecutive_timeouts >= open_after
        return {
            "consecutive_timeouts": consecutive_timeouts,
            "open_after": open_after,
            "circuit_open": open_,
            "state": "OPEN" if open_ else "CLOSED",
        }


class EventLogDriftDetector:
    """Detect block/log cursor drift between endpoints."""

    name = "EventLogDriftDetector"

    def run(self, primary_block: int, secondary_block: int, max_drift: int = 2) -> dict[str, Any]:
        drift = abs(int(primary_block) - int(secondary_block))
        return {
            "drift": drift,
            "max_drift": max_drift,
            "drifted": drift > max_drift,
            "primary_block": primary_block,
            "secondary_block": secondary_block,
        }


class StalenessMonitor:
    """Flag stale tips older than max_age_s."""

    name = "StalenessMonitor"

    def run(self, tip_age_s: float, max_age_s: float = 30.0) -> dict[str, Any]:
        stale = float(tip_age_s) > float(max_age_s)
        return {"tip_age_s": tip_age_s, "max_age_s": max_age_s, "stale": stale}


class JitterFilter:
    """Filter outlier latency samples (simple MAD-free z-clip)."""

    name = "JitterFilter"

    def run(self, samples_ms: Sequence[float], z_clip: float = 3.0) -> dict[str, Any]:
        vals = [float(x) for x in samples_ms]
        if len(vals) < 2:
            return {"filtered": vals, "removed": 0, "jitter_ms": 0.0}
        mean = statistics.fmean(vals)
        stdev = statistics.pstdev(vals) or 1e-9
        kept = [v for v in vals if abs(v - mean) / stdev <= z_clip]
        jitter = round(statistics.pstdev(kept) if len(kept) > 1 else 0.0, 3)
        return {
            "filtered": kept,
            "removed": len(vals) - len(kept),
            "jitter_ms": jitter,
            "mean_ms": round(mean, 3),
        }


class SLAEnforcer:
    """Enforce switch threshold and optional P99 SLA reference."""

    name = "SLAEnforcer"

    def __init__(self, config: ResilienceConfig):
        self.config = config

    def run(self, latency_ms: float, p99_us: float | None = None) -> dict[str, Any]:
        switch = latency_ms > self.config.rpc_switch_ms
        p99 = float(p99_us) if p99_us is not None else None
        # Optional surface P99 (µs); primary RPC health uses ms switch threshold.
        sla_breach = bool(p99 is not None and p99 > self.config.rpc_p99_sla_us)
        return {
            "latency_ms": latency_ms,
            "switch_threshold_ms": self.config.rpc_switch_ms,
            "should_switch": switch,
            "p99_us": p99,
            "sla_reference_us": self.config.rpc_p99_sla_us,
            "sla_breach": sla_breach,
            "rpc_ok": not switch and not sla_breach,
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class RPCHealthResult:
    rpc_ok: bool
    selected_endpoint: str | None
    failover: bool
    circuit_open: bool
    stale: bool
    drifted: bool
    latency_ms: float
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rpc_ok": self.rpc_ok,
            "selected_endpoint": self.selected_endpoint,
            "failover": self.failover,
            "circuit_open": self.circuit_open,
            "stale": self.stale,
            "drifted": self.drifted,
            "latency_ms": self.latency_ms,
            "subagents": self.subagent_results,
        }


class RPCHealthSentinel:
    """A2 — multi-RPC health, failover, and SLA enforcement."""

    agent_name = "RPCHealthSentinel"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.latency = LatencyProbe()
        self.backoff = HTTP429Backoff()
        self.fallback = FallbackRouter()
        self.balancer = MultiRPCEndpointBalancer()
        self.circuit = TimeoutCircuitBreaker()
        self.drift = EventLogDriftDetector()
        self.staleness = StalenessMonitor()
        self.jitter = JitterFilter()
        self.sla = SLAEnforcer(self.config)

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> RPCHealthResult:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "blocked" if result.circuit_open or not result.rpc_ok else "completed"
        if result.failover and result.rpc_ok:
            status = "completed"
        artifact = {
            "type": "rpc_health_result",
            "path": str(self._tenant / f"rpc_{job_id}.json"),
            "metadata": result.to_dict(),
        }
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[artifact],
            logs=[
                f"rpc_ok={result.rpc_ok}",
                f"endpoint={result.selected_endpoint}",
                f"failover={result.failover}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> RPCHealthResult:
        samples = list(payload.get("latency_samples_ms", payload.get("samples_ms", [10.0])))
        primary = str(payload.get("primary_endpoint", "https://rpc.primary.local"))
        candidates = list(
            payload.get(
                "fallback_endpoints",
                ["https://rpc.fallback.local", "https://builder.private.local"],
            )
        )
        status_codes = list(payload.get("status_codes", [200]))
        consecutive_timeouts = int(payload.get("consecutive_timeouts", 0))
        tip_age_s = float(payload.get("tip_age_s", 1.0))
        primary_block = int(payload.get("primary_block", 100))
        secondary_block = int(payload.get("secondary_block", primary_block))
        endpoints = list(
            payload.get(
                "endpoints",
                [
                    {"url": primary, "latency_ms": samples[0] if samples else 10, "healthy": True, "private": False},
                    {
                        "url": candidates[0] if candidates else "https://rpc.fallback.local",
                        "latency_ms": float(payload.get("fallback_latency_ms", 50)),
                        "healthy": True,
                        "private": True,
                    },
                ],
            )
        )
        p99_us = payload.get("p99_us")

        lat_r = self.latency.run(samples)
        jit_r = self.jitter.run(samples)
        filtered = jit_r["filtered"] or samples
        mean_ms = float(statistics.fmean(filtered)) if filtered else float(lat_r["mean_ms"])
        back_r = self.backoff.run(status_codes)
        circuit_r = self.circuit.run(consecutive_timeouts)
        stale_r = self.staleness.run(tip_age_s)
        drift_r = self.drift.run(primary_block, secondary_block)
        sla_r = self.sla.run(mean_ms, p99_us=float(p99_us) if p99_us is not None else None)

        primary_healthy = (
            not circuit_r["circuit_open"]
            and not stale_r["stale"]
            and not sla_r["should_switch"]
            and not back_r["throttled"]
        )
        fb_r = self.fallback.run(primary, candidates, primary_healthy)
        # Prefer private builders only when failing over; keep primary when healthy.
        bal_r = self.balancer.run(endpoints, prefer_private=not primary_healthy)
        if primary_healthy:
            selected = primary
            failover = False
        else:
            selected = bal_r.get("selected") or fb_r["selected"]
            failover = bool(fb_r["failover"] or (selected and selected != primary))
        rpc_ok = (
            not circuit_r["circuit_open"]
            and not drift_r["drifted"]
            and not stale_r["stale"]
            and selected is not None
            and (sla_r["rpc_ok"] or failover)
        )
        if failover and not circuit_r["circuit_open"] and not stale_r["stale"]:
            rpc_ok = True

        return RPCHealthResult(
            rpc_ok=rpc_ok,
            selected_endpoint=selected,
            failover=failover,
            circuit_open=circuit_r["circuit_open"],
            stale=stale_r["stale"],
            drifted=drift_r["drifted"],
            latency_ms=mean_ms,
            subagent_results={
                LatencyProbe.name: lat_r,
                HTTP429Backoff.name: back_r,
                FallbackRouter.name: fb_r,
                MultiRPCEndpointBalancer.name: bal_r,
                TimeoutCircuitBreaker.name: circuit_r,
                EventLogDriftDetector.name: drift_r,
                StalenessMonitor.name: stale_r,
                JitterFilter.name: jit_r,
                SLAEnforcer.name: sla_r,
            },
        )
