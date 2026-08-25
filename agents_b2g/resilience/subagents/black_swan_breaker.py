"""A6 — BlackSwanCircuitBreaker (Wave 40 Quadrant 3 / Model).

Nine subagents: RegimeChangeDetector → PostMortemGenerator.
Invariant: σ>black_swan_sigma or Vol>vol_spike_factor×30d → Auto-Halt.
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


class RegimeChangeDetector:
    """Detect regime shift via mean/vol break between windows."""

    name = "RegimeChangeDetector"

    def run(
        self,
        window_a: Sequence[float],
        window_b: Sequence[float],
        mean_shift_sigma: float = 2.0,
    ) -> dict[str, Any]:
        a = [float(x) for x in window_a] or [0.0]
        b = [float(x) for x in window_b] or [0.0]
        mean_a, mean_b = statistics.fmean(a), statistics.fmean(b)
        std_a = statistics.pstdev(a) or 1e-12
        shift = abs(mean_b - mean_a) / std_a
        changed = shift >= mean_shift_sigma
        return {
            "regime_change": changed,
            "mean_shift_sigma": round(shift, 6),
            "mean_a": round(mean_a, 6),
            "mean_b": round(mean_b, 6),
        }


class VolatilitySpikeMonitor:
    """Compare current vol to 30d baseline × spike factor."""

    name = "VolatilitySpikeMonitor"

    def run(
        self,
        current_vol: float,
        vol_30d: float,
        spike_factor: float,
    ) -> dict[str, Any]:
        baseline = float(vol_30d) if float(vol_30d) > 0 else 1e-12
        ratio = float(current_vol) / baseline
        spiked = ratio > float(spike_factor)
        return {
            "current_vol": current_vol,
            "vol_30d": vol_30d,
            "ratio": round(ratio, 6),
            "spike_factor": spike_factor,
            "vol_spike": spiked,
        }


class PanicSellIdentifier:
    """Identify panic-sell bursts (volume + negative return)."""

    name = "PanicSellIdentifier"

    def run(
        self,
        returns: Sequence[float],
        volumes: Sequence[float],
        ret_threshold: float = -0.05,
        vol_spike_mult: float = 3.0,
    ) -> dict[str, Any]:
        rets = [float(r) for r in returns]
        vols = [float(v) for v in volumes] or [0.0]
        med_vol = statistics.median(vols) if vols else 0.0
        floor = med_vol * vol_spike_mult if med_vol > 0 else 0.0
        panic_flags = [
            (r <= ret_threshold and v >= floor)
            for r, v in zip(rets, vols)
        ]
        # align lengths
        n = min(len(rets), len(vols))
        panic_flags = [
            rets[i] <= ret_threshold and vols[i] >= floor for i in range(n)
        ]
        return {
            "panic_detected": any(panic_flags),
            "panic_bars": sum(1 for p in panic_flags if p),
            "ret_threshold": ret_threshold,
        }


class LatencyOverlayAnalyzer:
    """Flag execution latency overlay coincident with stress."""

    name = "LatencyOverlayAnalyzer"

    def run(
        self,
        latency_ms: Sequence[float],
        baseline_p50_ms: float,
        stress_mult: float = 5.0,
    ) -> dict[str, Any]:
        vals = [float(x) for x in latency_ms] or [0.0]
        peak = max(vals)
        overlay = peak > float(baseline_p50_ms) * float(stress_mult)
        return {
            "latency_overlay": overlay,
            "peak_ms": round(peak, 3),
            "baseline_p50_ms": baseline_p50_ms,
            "stress_mult": stress_mult,
        }


class AutoHaltTrigger:
    """Auto-halt when sigma or vol spike (or panic + overlay)."""

    name = "AutoHaltTrigger"

    def run(
        self,
        *,
        abs_sigma: float,
        sigma_threshold: float,
        vol_spike: bool,
        panic: bool,
        latency_overlay: bool,
        regime_change: bool,
    ) -> dict[str, Any]:
        reasons = []
        if abs_sigma > sigma_threshold:
            reasons.append("sigma_breach")
        if vol_spike:
            reasons.append("vol_spike")
        if panic and latency_overlay:
            reasons.append("panic_latency")
        if regime_change and (abs_sigma > sigma_threshold * 0.8 or vol_spike):
            reasons.append("regime_stress")
        halt = len(reasons) > 0 and (
            "sigma_breach" in reasons
            or "vol_spike" in reasons
            or "panic_latency" in reasons
            or "regime_stress" in reasons
        )
        return {"auto_halt": halt, "reasons": reasons}


class ManualOverrideGate:
    """Human override may clear halt only with explicit token."""

    name = "ManualOverrideGate"

    def run(self, auto_halt: bool, override_token: str | None = None) -> dict[str, Any]:
        authorized = override_token == "AUTHORIZED_OVERRIDE"
        cleared = auto_halt and authorized
        still_halted = auto_halt and not authorized
        return {
            "override_applied": cleared,
            "still_halted": still_halted,
            "authorized": authorized,
        }


class RecoveryRampUp:
    """Ramp execution capacity after halt clears."""

    name = "RecoveryRampUp"

    def run(self, halted: bool, ramp_steps: int = 4) -> dict[str, Any]:
        if halted:
            return {"phase": "halted", "capacity_pct": 0, "ramp_steps": ramp_steps}
        return {
            "phase": "ramping",
            "capacity_pct": 25,  # first step after clear
            "ramp_steps": ramp_steps,
        }


class StressTestRunner:
    """Lightweight synthetic stress check (σ / vol scenarios)."""

    name = "StressTestRunner"

    def run(
        self,
        scenarios: Sequence[Mapping[str, Any]] | None = None,
        sigma_threshold: float = 5.0,
        vol_factor: float = 3.0,
    ) -> dict[str, Any]:
        scenarios = list(scenarios or [
            {"name": "sigma6", "sigma": 6.0, "vol_ratio": 1.0},
            {"name": "vol4x", "sigma": 1.0, "vol_ratio": 4.0},
            {"name": "calm", "sigma": 1.0, "vol_ratio": 1.0},
        ])
        fails = [
            s
            for s in scenarios
            if float(s.get("sigma", 0)) > sigma_threshold
            or float(s.get("vol_ratio", 0)) > vol_factor
        ]
        return {
            "scenario_count": len(scenarios),
            "fail_count": len(fails),
            "failed_scenarios": [str(s.get("name")) for s in fails],
            "stress_pass": len(fails) == 0,
        }


class PostMortemGenerator:
    """Compose post-mortem summary after halt."""

    name = "PostMortemGenerator"

    def run(
        self,
        *,
        halted: bool,
        reasons: Sequence[str],
        metrics: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not halted:
            return {"generated": False, "summary": None}
        return {
            "generated": True,
            "summary": {
                "reasons": list(reasons),
                "metrics": dict(metrics),
                "recommendation": "hold_execution_until_regime_stable",
            },
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class BlackSwanResult:
    blackswan_ok: bool
    halted: bool
    auto_halt: bool
    override_applied: bool
    abs_sigma: float
    vol_spike: bool
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blackswan_ok": self.blackswan_ok,
            "halted": self.halted,
            "auto_halt": self.auto_halt,
            "override_applied": self.override_applied,
            "abs_sigma": self.abs_sigma,
            "vol_spike": self.vol_spike,
            "subagents": self.subagent_results,
        }


class BlackSwanCircuitBreaker:
    """A6 — black-swan detection, auto-halt, recovery ramp."""

    agent_name = "BlackSwanCircuitBreaker"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.regime = RegimeChangeDetector()
        self.vol = VolatilitySpikeMonitor()
        self.panic = PanicSellIdentifier()
        self.latency = LatencyOverlayAnalyzer()
        self.halt = AutoHaltTrigger()
        self.override = ManualOverrideGate()
        self.ramp = RecoveryRampUp()
        self.stress = StressTestRunner()
        self.postmortem = PostMortemGenerator()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> BlackSwanResult:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "blocked" if result.halted else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "black_swan_result",
                    "path": str(self._tenant / f"blackswan_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            logs=[
                f"blackswan_ok={result.blackswan_ok}",
                f"halted={result.halted}",
                f"sigma={result.abs_sigma}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> BlackSwanResult:
        window_a = list(payload.get("window_a", [0.0, 0.1, -0.05, 0.02]))
        window_b = list(payload.get("window_b", window_a))
        current_vol = float(payload.get("current_vol", 0.1))
        vol_30d = float(payload.get("vol_30d", 0.1))
        returns = list(payload.get("returns", []))
        volumes = list(payload.get("volumes", []))
        latency_ms = list(payload.get("latency_ms", [10.0]))
        baseline_p50 = float(payload.get("baseline_p50_ms", 10.0))
        value = float(payload.get("z_value", payload.get("value", 0.0)))
        mean = float(payload.get("z_mean", 0.0))
        stdev = float(payload.get("z_stdev", 1.0))
        override_token = payload.get("override_token")
        scenarios = payload.get("stress_scenarios")

        abs_sigma = abs((value - mean) / (stdev if stdev > 1e-12 else 1e-12))
        # allow direct sigma override
        if "abs_sigma" in payload:
            abs_sigma = float(payload["abs_sigma"])

        reg_r = self.regime.run(window_a, window_b)
        vol_r = self.vol.run(current_vol, vol_30d, self.config.vol_spike_factor)
        pan_r = self.panic.run(returns, volumes)
        lat_r = self.latency.run(latency_ms, baseline_p50)
        halt_r = self.halt.run(
            abs_sigma=abs_sigma,
            sigma_threshold=self.config.black_swan_sigma,
            vol_spike=bool(vol_r["vol_spike"]),
            panic=bool(pan_r["panic_detected"]),
            latency_overlay=bool(lat_r["latency_overlay"]),
            regime_change=bool(reg_r["regime_change"]),
        )
        ov_r = self.override.run(bool(halt_r["auto_halt"]), override_token)
        still_halted = bool(ov_r["still_halted"])
        # If no auto-halt, not halted; if override applied, cleared
        halted = still_halted
        ramp_r = self.ramp.run(halted)
        stress_r = self.stress.run(
            scenarios,
            sigma_threshold=self.config.black_swan_sigma,
            vol_factor=self.config.vol_spike_factor,
        )
        pm_r = self.postmortem.run(
            halted=halted,
            reasons=halt_r["reasons"],
            metrics={
                "abs_sigma": round(abs_sigma, 6),
                "vol_ratio": vol_r["ratio"],
                "regime_change": reg_r["regime_change"],
            },
        )

        blackswan_ok = not halted

        return BlackSwanResult(
            blackswan_ok=blackswan_ok,
            halted=halted,
            auto_halt=bool(halt_r["auto_halt"]),
            override_applied=bool(ov_r["override_applied"]),
            abs_sigma=round(abs_sigma, 6),
            vol_spike=bool(vol_r["vol_spike"]),
            subagent_results={
                RegimeChangeDetector.name: reg_r,
                VolatilitySpikeMonitor.name: vol_r,
                PanicSellIdentifier.name: pan_r,
                LatencyOverlayAnalyzer.name: lat_r,
                AutoHaltTrigger.name: halt_r,
                ManualOverrideGate.name: ov_r,
                RecoveryRampUp.name: ramp_r,
                StressTestRunner.name: stress_r,
                PostMortemGenerator.name: pm_r,
            },
        )
