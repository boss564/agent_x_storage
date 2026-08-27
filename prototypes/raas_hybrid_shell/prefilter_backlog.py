"""Backlog prioritization via risk prefilter — no core skip.

When PREFILTER_ENABLED and pending count ≥ threshold, requests are scored
and processed highest-score-first. Every request still runs full
TrustedCoreGateway evaluation. Score failure → FIFO fallback.

Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal
from prototypes.raas_hybrid_shell.supranode_facade import (
    ExternalRequest,
    ExternalResponse,
    SupranodeFacade,
)

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

ScoreFn = Callable[[Dict[str, float]], Dict[str, Any]]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def proposal_to_features(prop: LLMStrategyProposal) -> Dict[str, float]:
    """Map shell proposal fields into prefilter feature space (deterministic)."""
    slip = float(prop.max_slippage_pct)
    lat = float(prop.latency_budget_ms)
    # Heuristic fills for synth-trained dimensions not on the proposal
    return {
        "latency_ms": lat,
        "slippage_pct": slip,
        "pool_depth_usd": 500_000.0,
        "volatility_24h": 0.03 + min(slip, 5.0) / 100.0,
        "gas_price_gwei": 20.0 + min(lat, 200.0) / 10.0,
        "oracle_deviation_pct": 5.0 if "oracle" in prop.profile_hint.lower() else 0.0,
        "mev_bundle_activity": 0.2 + min(slip, 3.0) / 10.0,
        "strategy_complexity_score": 0.3 + min(prop.rebalance_interval_h, 24.0) / 48.0,
    }


def default_score_fn(features: Dict[str, float]) -> Dict[str, Any]:
    """In-process scorer (NATS optional later). Raises on hard failure."""
    from plugins.risk_prefilter.scorer import score_features

    model = os.environ.get(
        "PREFILTER_MODEL_PATH", "models/prefilter/prefilter_gbt.pkl"
    )
    return score_features(features, model_path=model)


@dataclass
class BacklogBatchResult:
    responses: List[ExternalResponse]
    order_correlation_ids: List[str]
    mode: str  # fifo | priority
    prefilter_enabled: bool
    backlog_threshold: int
    scored: int
    score_failures: int
    all_processed: bool
    live_execution: bool = False
    scope: str = SCOPE
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "prefilter_enabled": self.prefilter_enabled,
            "backlog_threshold": self.backlog_threshold,
            "scored": self.scored,
            "score_failures": self.score_failures,
            "all_processed": self.all_processed,
            "order_correlation_ids": list(self.order_correlation_ids),
            "n_responses": len(self.responses),
            "live_execution": self.live_execution,
            "scope": self.scope,
            "note": self.note,
            "gate_verdicts": [r.envelope.gate_verdict for r in self.responses],
        }


@dataclass
class PrefilterBacklogController:
    """Facade wrapper: optional score-sort under backlog; never skip core."""

    facade: SupranodeFacade
    enabled: bool = field(default_factory=lambda: _env_bool("PREFILTER_ENABLED", False))
    backlog_threshold: int = field(
        default_factory=lambda: int(os.environ.get("PREFILTER_BACKLOG_THRESHOLD", "3"))
    )
    score_fn: Optional[ScoreFn] = None

    def _score_one(self, req: ExternalRequest) -> Tuple[float, bool]:
        """Returns (score, ok). ok=False → treat as unscored (FIFO path)."""
        fn = self.score_fn or default_score_fn
        try:
            out = fn(proposal_to_features(req.proposal))
            if "prefilter_score" not in out:
                return 0.0, False
            # Reject if scorer leaked decision fields
            for banned in (
                "gate_verdict",
                "audit_verdict",
                "envelope_id",
                "egress_seal",
                "certificate_id",
            ):
                if banned in out:
                    return 0.0, False
            return float(out["prefilter_score"]), True
        except Exception:
            return 0.0, False

    def process_batch(
        self,
        requests: Sequence[ExternalRequest],
        *,
        n_scenarios: int = 20,
    ) -> BacklogBatchResult:
        pending = list(requests)
        n = len(pending)
        use_priority = self.enabled and n >= self.backlog_threshold

        scored = 0
        failures = 0
        order: List[ExternalRequest] = list(pending)
        mode = "fifo"

        if use_priority:
            ranked: List[Tuple[float, int, ExternalRequest]] = []
            for i, req in enumerate(pending):
                score, ok = self._score_one(req)
                if ok:
                    scored += 1
                    ranked.append((score, i, req))
                else:
                    failures += 1
                    ranked.append((float("-inf"), i, req))  # keep relative FIFO among fails
            if failures == n:
                # Total prefilter outage → pure FIFO
                order = list(pending)
                mode = "fifo"
            else:
                # Highest score first; stable by arrival index for ties
                ranked.sort(key=lambda t: (-t[0], t[1]))
                order = [t[2] for t in ranked]
                mode = "priority"

        responses: List[ExternalResponse] = []
        for req in order:
            # Full deterministic core path — never skipped
            responses.append(
                self.facade.handle_external_request(req, n_scenarios=n_scenarios)
            )

        return BacklogBatchResult(
            responses=responses,
            order_correlation_ids=[r.correlation_id for r in responses],
            mode=mode,
            prefilter_enabled=self.enabled,
            backlog_threshold=self.backlog_threshold,
            scored=scored if use_priority else 0,
            score_failures=failures if use_priority else 0,
            all_processed=len(responses) == n,
            note=(
                "Priority reorders under backlog only; every request fully "
                "evaluated by TrustedCoreGateway. Score failure → FIFO."
            ),
        )
