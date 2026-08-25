"""A5 — ConfounderDetector (Wave 40 Quadrant 3 / Model).

Nine subagents: ExogenousSignalScanner → SignalQuarantineManager.
Invariants: Novel-Faktor → quarantine + 24h cooldown; Pre-Reg gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agents_b2g.resilience.agents import make_response
from agents_b2g.resilience.config import ResilienceConfig
from agents_b2g.resilience.logging_utils import JSONLogger, _safe_call


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class ExogenousSignalScanner:
    """Scan for exogenous drivers not in the causal model."""

    name = "ExogenousSignalScanner"

    def run(self, signals: Sequence[Mapping[str, Any]], known_factors: Sequence[str]) -> dict[str, Any]:
        known = {k.lower() for k in known_factors}
        exogenous = [
            s
            for s in signals
            if str(s.get("factor", s.get("id", ""))).lower() not in known
            or bool(s.get("exogenous"))
        ]
        return {
            "exogenous_count": len(exogenous),
            "exogenous_ids": [str(s.get("id", s.get("factor"))) for s in exogenous][:16],
            "detected": len(exogenous) > 0,
        }


class CEXShockDetector:
    """Detect CEX price shocks (|return| above threshold)."""

    name = "CEXShockDetector"

    def run(self, returns: Sequence[float], shock_threshold: float = 0.08) -> dict[str, Any]:
        vals = [float(r) for r in returns]
        shocks = [r for r in vals if abs(r) >= shock_threshold]
        return {
            "shock_detected": len(shocks) > 0,
            "shock_count": len(shocks),
            "max_abs_return": round(max((abs(r) for r in vals), default=0.0), 6),
            "threshold": shock_threshold,
        }


class ThirdChainHackMonitor:
    """Flag third-chain exploit / bridge-hack markers."""

    name = "ThirdChainHackMonitor"

    def run(self, incidents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        hacks = [
            i
            for i in incidents
            if str(i.get("kind", "")).upper() in {"HACK", "BRIDGE_EXPLOIT", "THIRD_CHAIN_HACK"}
            or bool(i.get("is_hack"))
        ]
        return {
            "hack_detected": len(hacks) > 0,
            "hack_count": len(hacks),
            "chains": sorted({str(h.get("chain", "unknown")) for h in hacks})[:8],
        }


class NovelFactorClassifier:
    """Classify factors as known / novel relative to pre-reg registry."""

    name = "NovelFactorClassifier"

    def run(
        self,
        candidate_factors: Sequence[str],
        registered_factors: Sequence[str],
    ) -> dict[str, Any]:
        registered = {f.lower() for f in registered_factors}
        novel = [f for f in candidate_factors if f.lower() not in registered]
        return {
            "novel_factors": novel,
            "novel_count": len(novel),
            "has_novel": len(novel) > 0,
        }


class PreRegistrationValidator:
    """Only registered factors may generate executable signals."""

    name = "PreRegistrationValidator"

    def run(
        self,
        signal_factors: Sequence[str],
        registered_factors: Sequence[str],
    ) -> dict[str, Any]:
        registered = {f.lower() for f in registered_factors}
        unregistered = [f for f in signal_factors if f.lower() not in registered]
        return {
            "ok": len(unregistered) == 0,
            "unregistered": unregistered,
            "registered_count": len(registered),
            "reason": None if not unregistered else "unregistered_factor",
        }


class SpuriousCorrelationFilter:
    """Drop pairs with high correlation but no causal edge."""

    name = "SpuriousCorrelationFilter"

    def run(
        self,
        pairs: Sequence[Mapping[str, Any]],
        corr_threshold: float = 0.9,
    ) -> dict[str, Any]:
        spurious = [
            p
            for p in pairs
            if float(p.get("correlation", 0)) >= corr_threshold
            and not bool(p.get("causal_edge", False))
        ]
        return {
            "spurious_count": len(spurious),
            "filtered_ids": [str(p.get("id", "")) for p in spurious][:16],
            "has_spurious": len(spurious) > 0,
        }


class CausalGraphUpdater:
    """Propose graph updates; quarantine novel nodes until approved."""

    name = "CausalGraphUpdater"

    def run(
        self,
        novel_factors: Sequence[str],
        approved_edges: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        pending = list(novel_factors)
        applied = [e for e in (approved_edges or []) if e.get("from") and e.get("to")]
        return {
            "pending_nodes": pending,
            "applied_edges": len(applied),
            "graph_frozen_for_novel": len(pending) > 0,
        }


class AnomalyZScorer:
    """Z-score anomaly vs baseline series."""

    name = "AnomalyZScorer"

    def run(self, value: float, mean: float, stdev: float) -> dict[str, Any]:
        sigma = float(stdev) if float(stdev) > 1e-12 else 1e-12
        z = (float(value) - float(mean)) / sigma
        return {
            "z": round(z, 6),
            "abs_z": round(abs(z), 6),
            "anomalous": abs(z) >= 3.0,
        }


class SignalQuarantineManager:
    """Quarantine signals for cooldown_h when novel/exogenous/unregistered."""

    name = "SignalQuarantineManager"

    def run(
        self,
        *,
        signal_ids: Sequence[str],
        quarantine: bool,
        cooldown_h: float,
        reasons: Sequence[str],
    ) -> dict[str, Any]:
        ids = list(signal_ids) if quarantine else []
        return {
            "quarantined": quarantine,
            "quarantined_signals": ids,
            "cooldown_h": cooldown_h,
            "reasons": list(reasons),
            "count": len(ids),
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class ConfounderDetectorResult:
    confounder_ok: bool
    quarantined: bool
    cooldown_h: float
    novel_count: int
    prereg_ok: bool
    exogenous_detected: bool
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confounder_ok": self.confounder_ok,
            "quarantined": self.quarantined,
            "cooldown_h": self.cooldown_h,
            "novel_count": self.novel_count,
            "prereg_ok": self.prereg_ok,
            "exogenous_detected": self.exogenous_detected,
            "subagents": self.subagent_results,
        }


class ConfounderDetector:
    """A5 — exogenous/novel factor quarantine and pre-reg gate."""

    agent_name = "ConfounderDetector"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.exo = ExogenousSignalScanner()
        self.cex = CEXShockDetector()
        self.hack = ThirdChainHackMonitor()
        self.novel = NovelFactorClassifier()
        self.prereg = PreRegistrationValidator()
        self.spurious = SpuriousCorrelationFilter()
        self.graph = CausalGraphUpdater()
        self.zscore = AnomalyZScorer()
        self.quarantine = SignalQuarantineManager()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> ConfounderDetectorResult:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "completed" if result.confounder_ok else "blocked"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "confounder_detector_result",
                    "path": str(self._tenant / f"confounder_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            logs=[
                f"confounder_ok={result.confounder_ok}",
                f"quarantined={result.quarantined}",
                f"novel={result.novel_count}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> ConfounderDetectorResult:
        registered = list(
            payload.get(
                "registered_factors",
                ["oracle_lag", "mev_density", "liquidation_cascade", "stablecoin_flow"],
            )
        )
        known = list(payload.get("known_factors", registered))
        signals = list(payload.get("signals", []))
        candidates = list(
            payload.get(
                "candidate_factors",
                [str(s.get("factor", s.get("id", ""))) for s in signals if s.get("factor") or s.get("id")],
            )
        )
        signal_factors = list(
            payload.get(
                "signal_factors",
                candidates or registered[:1],
            )
        )
        signal_ids = list(
            payload.get(
                "signal_ids",
                [str(s.get("id", f"sig-{i}")) for i, s in enumerate(signals)] or ["sig-0"],
            )
        )
        returns = list(payload.get("cex_returns", []))
        incidents = list(payload.get("chain_incidents", []))
        pairs = list(payload.get("correlation_pairs", []))
        z_value = float(payload.get("z_value", payload.get("value", 0.0)))
        z_mean = float(payload.get("z_mean", 0.0))
        z_stdev = float(payload.get("z_stdev", 1.0))
        shock_thr = float(payload.get("cex_shock_threshold", 0.08))
        corr_thr = float(payload.get("corr_threshold", 0.9))
        approved_edges = list(payload.get("approved_edges", []))

        exo_r = self.exo.run(signals, known)
        cex_r = self.cex.run(returns, shock_thr)
        hack_r = self.hack.run(incidents)
        nov_r = self.novel.run(candidates, registered)
        pre_r = self.prereg.run(signal_factors, registered)
        spu_r = self.spurious.run(pairs, corr_thr)
        gra_r = self.graph.run(nov_r["novel_factors"], approved_edges)
        z_r = self.zscore.run(z_value, z_mean, z_stdev)

        reasons: list[str] = []
        if nov_r["has_novel"]:
            reasons.append("novel_factor")
        if not pre_r["ok"]:
            reasons.append("prereg_gate")
        if exo_r["detected"]:
            reasons.append("exogenous")
        if cex_r["shock_detected"]:
            reasons.append("cex_shock")
        if hack_r["hack_detected"]:
            reasons.append("third_chain_hack")
        if spu_r["has_spurious"]:
            reasons.append("spurious_correlation")
        if z_r["anomalous"] and (nov_r["has_novel"] or exo_r["detected"]):
            reasons.append("anomaly_z")

        must_quarantine = bool(
            nov_r["has_novel"]
            or not pre_r["ok"]
            or exo_r["detected"]
            or cex_r["shock_detected"]
            or hack_r["hack_detected"]
        )
        qua_r = self.quarantine.run(
            signal_ids=signal_ids,
            quarantine=must_quarantine,
            cooldown_h=self.config.confounder_cooldown_h,
            reasons=reasons,
        )

        # confounder_ok only when pre-reg holds and nothing is quarantined
        confounder_ok = bool(pre_r["ok"] and not qua_r["quarantined"])

        return ConfounderDetectorResult(
            confounder_ok=confounder_ok,
            quarantined=bool(qua_r["quarantined"]),
            cooldown_h=float(qua_r["cooldown_h"]),
            novel_count=int(nov_r["novel_count"]),
            prereg_ok=bool(pre_r["ok"]),
            exogenous_detected=bool(exo_r["detected"]),
            subagent_results={
                ExogenousSignalScanner.name: exo_r,
                CEXShockDetector.name: cex_r,
                ThirdChainHackMonitor.name: hack_r,
                NovelFactorClassifier.name: nov_r,
                PreRegistrationValidator.name: pre_r,
                SpuriousCorrelationFilter.name: spu_r,
                CausalGraphUpdater.name: gra_r,
                AnomalyZScorer.name: z_r,
                SignalQuarantineManager.name: qua_r,
            },
        )
