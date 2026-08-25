"""A3 — MEVShield (Wave 40 Quadrant 2 / MEV).

Nine subagents: FlashbotsRelayClient → ExecutionPrivacyEnforcer.
Invariant: Private-Only-Submission — Mempool-Leakage = 0.
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


class FlashbotsRelayClient:
    """Resolve private relay / builder endpoints (Flashbots / MEV-Boost)."""

    name = "FlashbotsRelayClient"

    def run(self, relays: Sequence[str], prefer: str | None = None) -> dict[str, Any]:
        pool = [r for r in relays if r]
        selected = prefer if prefer in pool else (pool[0] if pool else None)
        return {
            "selected_relay": selected,
            "relay_count": len(pool),
            "connected": selected is not None,
            "relays": pool[:8],
        }


class PrivateTxSubmitter:
    """Submit only via private path — public mempool forbidden."""

    name = "PrivateTxSubmitter"

    def run(
        self,
        *,
        use_public_mempool: bool,
        relay_connected: bool,
        tx_hash: str | None = None,
    ) -> dict[str, Any]:
        allowed = relay_connected and not use_public_mempool
        return {
            "submitted": allowed,
            "private": allowed,
            "use_public_mempool": use_public_mempool,
            "tx_hash": tx_hash if allowed else None,
            "reject_reason": None
            if allowed
            else ("public_mempool_forbidden" if use_public_mempool else "no_relay"),
        }


class SandwichDetector:
    """Detect sandwich pattern around target TX (victim between attacker legs)."""

    name = "SandwichDetector"

    def run(self, surrounding_txs: Sequence[Mapping[str, Any]], own_from: str) -> dict[str, Any]:
        own = own_from.lower()
        legs = [
            t
            for t in surrounding_txs
            if str(t.get("from", "")).lower() != own and t.get("role") in {"front", "back", "attacker"}
        ]
        front = any(t.get("role") == "front" for t in legs)
        back = any(t.get("role") == "back" for t in legs)
        sandwich = front and back
        return {
            "sandwich_detected": sandwich,
            "front_legs": sum(1 for t in legs if t.get("role") == "front"),
            "back_legs": sum(1 for t in legs if t.get("role") == "back"),
        }


class FrontRunningGuard:
    """Flag competing TXs that copy calldata / target before ours."""

    name = "FrontRunningGuard"

    def run(
        self,
        mempool_competitors: Sequence[Mapping[str, Any]],
        our_nonce: int,
        our_target: str,
    ) -> dict[str, Any]:
        target = our_target.lower()
        threats = [
            c
            for c in mempool_competitors
            if str(c.get("to", "")).lower() == target
            and int(c.get("nonce", 10**9)) < our_nonce
        ]
        return {
            "frontrun_risk": len(threats) > 0,
            "threat_count": len(threats),
            "threats": threats[:5],
        }


class SlippageEnforcer:
    """Enforce max slippage bps on quoted vs executed price."""

    name = "SlippageEnforcer"

    def run(
        self,
        quoted_price: float,
        executed_or_limit_price: float,
        max_slippage_bps: float = 50.0,
    ) -> dict[str, Any]:
        if quoted_price <= 0:
            return {
                "ok": False,
                "slippage_bps": None,
                "max_slippage_bps": max_slippage_bps,
                "reason": "invalid_quote",
            }
        slippage_bps = abs(executed_or_limit_price - quoted_price) / quoted_price * 10_000
        ok = slippage_bps <= max_slippage_bps
        return {
            "ok": ok,
            "slippage_bps": round(slippage_bps, 4),
            "max_slippage_bps": max_slippage_bps,
            "reason": None if ok else "slippage_cap_exceeded",
        }


class BundlePricer:
    """Price Flashbots bundle (gas + tip) for inclusion probability."""

    name = "BundlePricer"

    def run(
        self,
        base_fee_gwei: float,
        priority_fee_gwei: float,
        gas_limit: int,
        competing_tips_gwei: Sequence[float] | None = None,
    ) -> dict[str, Any]:
        effective = base_fee_gwei + priority_fee_gwei
        cost = effective * gas_limit
        peers = list(competing_tips_gwei or [])
        competitive = not peers or priority_fee_gwei >= max(peers) * 0.9
        return {
            "effective_gwei": round(effective, 4),
            "bundle_cost_gwei_gas": round(cost, 2),
            "competitive": competitive,
            "priority_fee_gwei": priority_fee_gwei,
        }


class BuilderReputationTracker:
    """Track builder reputation scores; prefer high-trust builders."""

    name = "BuilderReputationTracker"

    def run(self, builders: Sequence[Mapping[str, Any]], min_score: float = 0.7) -> dict[str, Any]:
        ranked = sorted(
            (b for b in builders if b.get("id")),
            key=lambda b: float(b.get("score", 0)),
            reverse=True,
        )
        trusted = [b for b in ranked if float(b.get("score", 0)) >= min_score]
        best = trusted[0] if trusted else (ranked[0] if ranked else None)
        return {
            "best_builder": best.get("id") if best else None,
            "best_score": float(best.get("score", 0)) if best else 0.0,
            "trusted_count": len(trusted),
            "min_score": min_score,
            "ok": best is not None and float(best.get("score", 0)) >= min_score,
        }


class MempoolLeakageScanner:
    """Invariant: leakage count must be 0 for Private-Only-Submission."""

    name = "MempoolLeakageScanner"

    def run(
        self,
        *,
        submitted_public: bool,
        observed_in_public_mempool: bool,
        relay_only: bool,
    ) -> dict[str, Any]:
        leakage = 0
        if submitted_public:
            leakage += 1
        if observed_in_public_mempool and relay_only:
            leakage += 1
        return {
            "leakage_count": leakage,
            "leakage_zero": leakage == 0,
            "submitted_public": submitted_public,
            "observed_in_public_mempool": observed_in_public_mempool,
        }


class ExecutionPrivacyEnforcer:
    """Aggregate privacy gate — all private paths + zero leakage."""

    name = "ExecutionPrivacyEnforcer"

    def run(
        self,
        *,
        private_submit: bool,
        leakage_zero: bool,
        sandwich: bool,
        frontrun: bool,
        slippage_ok: bool,
        builder_ok: bool,
    ) -> dict[str, Any]:
        privacy_ok = private_submit and leakage_zero and builder_ok
        threats = sandwich or frontrun or not slippage_ok
        mev_ok = privacy_ok and not threats
        return {
            "privacy_ok": privacy_ok,
            "mev_ok": mev_ok,
            "threats_present": threats,
            "reasons": [
                *([] if private_submit else ["not_private"]),
                *([] if leakage_zero else ["mempool_leakage"]),
                *([] if builder_ok else ["builder_reputation"]),
                *(["sandwich"] if sandwich else []),
                *(["frontrun"] if frontrun else []),
                *([] if slippage_ok else ["slippage"]),
            ],
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class MEVShieldResult:
    mev_ok: bool
    privacy_ok: bool
    leakage_count: int
    selected_relay: str | None
    sandwich_detected: bool
    frontrun_risk: bool
    slippage_ok: bool
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mev_ok": self.mev_ok,
            "privacy_ok": self.privacy_ok,
            "leakage_count": self.leakage_count,
            "selected_relay": self.selected_relay,
            "sandwich_detected": self.sandwich_detected,
            "frontrun_risk": self.frontrun_risk,
            "slippage_ok": self.slippage_ok,
            "subagents": self.subagent_results,
        }


class MEVShield:
    """A3 — private relay submission and MEV threat shield."""

    agent_name = "MEVShield"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.relay = FlashbotsRelayClient()
        self.submitter = PrivateTxSubmitter()
        self.sandwich = SandwichDetector()
        self.frontrun = FrontRunningGuard()
        self.slippage = SlippageEnforcer()
        self.pricer = BundlePricer()
        self.reputation = BuilderReputationTracker()
        self.leakage = MempoolLeakageScanner()
        self.privacy = ExecutionPrivacyEnforcer()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> MEVShieldResult:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "completed" if result.mev_ok else "blocked"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "mev_shield_result",
                    "path": str(self._tenant / f"mev_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            logs=[
                f"mev_ok={result.mev_ok}",
                f"leakage={result.leakage_count}",
                f"relay={result.selected_relay}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> MEVShieldResult:
        relays = list(
            payload.get(
                "relays",
                [
                    "https://relay.flashbots.net",
                    "https://builder.private.local",
                ],
            )
        )
        prefer = payload.get("prefer_relay")
        use_public = bool(payload.get("use_public_mempool", False))
        tx_hash = payload.get("tx_hash")
        surrounding = list(payload.get("surrounding_txs", []))
        own_from = str(payload.get("from_address", "0xown"))
        competitors = list(payload.get("mempool_competitors", []))
        our_nonce = int(payload.get("nonce", 1))
        our_target = str(payload.get("to_address", "0xtarget"))
        quoted = float(payload.get("quoted_price", 1.0))
        limit_price = float(payload.get("limit_price", quoted))
        max_slip_bps = float(payload.get("max_slippage_bps", 50.0))
        base_fee = float(payload.get("base_fee_gwei", 20.0))
        tip = float(payload.get("priority_fee_gwei", 2.0))
        gas_limit = int(payload.get("gas_limit", 21000))
        competing_tips = list(payload.get("competing_tips_gwei", []))
        builders = list(
            payload.get(
                "builders",
                [
                    {"id": "flashbots", "score": 0.95},
                    {"id": "titan", "score": 0.85},
                ],
            )
        )
        observed_public = bool(payload.get("observed_in_public_mempool", False))
        relay_only = not use_public

        relay_r = self.relay.run(relays, prefer=prefer)
        sub_r = self.submitter.run(
            use_public_mempool=use_public,
            relay_connected=bool(relay_r["connected"]),
            tx_hash=str(tx_hash) if tx_hash else "0xpending",
        )
        sand_r = self.sandwich.run(surrounding, own_from)
        front_r = self.frontrun.run(competitors, our_nonce, our_target)
        slip_r = self.slippage.run(quoted, limit_price, max_slip_bps)
        price_r = self.pricer.run(base_fee, tip, gas_limit, competing_tips)
        rep_r = self.reputation.run(builders)
        leak_r = self.leakage.run(
            submitted_public=use_public,
            observed_in_public_mempool=observed_public,
            relay_only=relay_only,
        )
        priv_r = self.privacy.run(
            private_submit=bool(sub_r["private"]),
            leakage_zero=bool(leak_r["leakage_zero"]),
            sandwich=bool(sand_r["sandwich_detected"]),
            frontrun=bool(front_r["frontrun_risk"]),
            slippage_ok=bool(slip_r["ok"]),
            builder_ok=bool(rep_r["ok"]),
        )

        return MEVShieldResult(
            mev_ok=bool(priv_r["mev_ok"]),
            privacy_ok=bool(priv_r["privacy_ok"]),
            leakage_count=int(leak_r["leakage_count"]),
            selected_relay=relay_r["selected_relay"],
            sandwich_detected=bool(sand_r["sandwich_detected"]),
            frontrun_risk=bool(front_r["frontrun_risk"]),
            slippage_ok=bool(slip_r["ok"]),
            subagent_results={
                FlashbotsRelayClient.name: relay_r,
                PrivateTxSubmitter.name: sub_r,
                SandwichDetector.name: sand_r,
                FrontRunningGuard.name: front_r,
                SlippageEnforcer.name: slip_r,
                BundlePricer.name: price_r,
                BuilderReputationTracker.name: rep_r,
                MempoolLeakageScanner.name: leak_r,
                ExecutionPrivacyEnforcer.name: priv_r,
            },
        )
