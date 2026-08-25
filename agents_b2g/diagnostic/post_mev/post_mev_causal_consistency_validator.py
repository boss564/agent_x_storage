"""PM1 — PostMEVCausalConsistencyValidator.

Validates causal consistency after mev_tail_completed. Does not mutate
Wave-38 Gatekeeper envelopes or Wave-40 execution gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agents_b2g.diagnostic.post_mev.agents import make_response
from agents_b2g.diagnostic.post_mev.config import PostMEVConfig
from agents_b2g.diagnostic.post_mev.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.post_mev.types import sha256_hex


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class TailCompletionGuard:
    name = "TailCompletionGuard"

    def run(self, trigger: str, expected: str, checkpoint_status: str) -> dict[str, Any]:
        ok = trigger == expected and checkpoint_status == "completed"
        return {"ok": ok, "trigger": trigger, "checkpoint_status": checkpoint_status}


class EnvelopeImmutabilityChecker:
    name = "EnvelopeImmutabilityChecker"

    def run(self, envelope: Mapping[str, Any], expected_hash: str | None) -> dict[str, Any]:
        current = sha256_hex(dict(envelope))
        if not expected_hash:
            return {"ok": True, "hash": current, "matched": True, "note": "hash_recorded"}
        matched = current == expected_hash
        return {"ok": matched, "hash": current, "matched": matched}


class PreFinalityRejector:
    name = "PreFinalityRejector"

    def run(self, confirmations: int, threshold: int) -> dict[str, Any]:
        # Descriptive only — marks under-finalized signals; no execution halt.
        under = confirmations < threshold
        return {
            "confirmations": confirmations,
            "threshold": threshold,
            "under_finality": under,
            "marked": under,
        }


class OccupancyDriftComparator:
    name = "OccupancyDriftComparator"

    def run(self, before: Mapping[str, float], after: Mapping[str, float]) -> dict[str, Any]:
        keys = set(before) | set(after)
        drifts = {
            k: abs(float(after.get(k, 0)) - float(before.get(k, 0))) for k in keys
        }
        max_drift = max(drifts.values()) if drifts else 0.0
        return {"max_drift": round(max_drift, 6), "drifts": drifts, "ok": True}


class CTEStabilityProbe:
    name = "CTEStabilityProbe"

    def run(self, cte_before: float, cte_after: float, threshold: float) -> dict[str, Any]:
        delta = abs(float(cte_after) - float(cte_before))
        stable = delta <= threshold
        return {"delta": round(delta, 6), "threshold": threshold, "stable": stable}


class DirectionConsistencyChecker:
    name = "DirectionConsistencyChecker"

    def run(self, ab_ok: bool, ba_ok: bool) -> dict[str, Any]:
        return {"ab_ok": ab_ok, "ba_ok": ba_ok, "consistent": ab_ok and ba_ok}


class MEVInterferenceScorer:
    name = "MEVInterferenceScorer"

    def run(self, sandwich_hits: int, frontrun_hits: int, volume: int) -> dict[str, Any]:
        vol = max(int(volume), 1)
        score = min(1.0, (sandwich_hits + frontrun_hits) / vol)
        return {"score": round(score, 6), "elevated": score >= 0.2}


class SignalIntegrityHasher:
    name = "SignalIntegrityHasher"

    def run(self, signal_ids: list[str]) -> dict[str, Any]:
        digest = sha256_hex({"signals": sorted(signal_ids)})
        return {"content_hash": digest, "count": len(signal_ids)}


class ConsistencyVerdictComposer:
    name = "ConsistencyVerdictComposer"

    def run(self, parts: Mapping[str, Any]) -> dict[str, Any]:
        consistency_ok = bool(
            parts.get("tail_ok")
            and parts.get("envelope_ok")
            and parts.get("cte_stable")
            and parts.get("direction_ok")
            and not parts.get("interference_elevated")
        )
        distorted = list(parts.get("distorted_ids", []))
        if not consistency_ok and not distorted:
            distorted = list(parts.get("signal_ids", []))[:8]
        return {
            "consistency_ok": consistency_ok,
            "distorted_signal_ids": distorted,
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class PM1Result:
    consistency_ok: bool
    distorted_signal_ids: list[str]
    envelope_hash: str
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "consistency_ok": self.consistency_ok,
            "distorted_signal_ids": self.distorted_signal_ids,
            "envelope_hash": self.envelope_hash,
            "subagents": self.subagent_results,
        }


class PostMEVCausalConsistencyValidator:
    agent_name = "PostMEVCausalConsistencyValidator"

    def __init__(self, user_id: str = "post_mev", config: PostMEVConfig | None = None):
        self.user_id = user_id
        self.config = config or PostMEVConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.tail = TailCompletionGuard()
        self.immut = EnvelopeImmutabilityChecker()
        self.finality = PreFinalityRejector()
        self.drift = OccupancyDriftComparator()
        self.cte = CTEStabilityProbe()
        self.direction = DirectionConsistencyChecker()
        self.interfer = MEVInterferenceScorer()
        self.hasher = SignalIntegrityHasher()
        self.composer = ConsistencyVerdictComposer()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> PM1Result:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "completed" if result.consistency_ok else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "pm1_result",
                    "path": str(self._tenant / f"pm1_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            logs=[f"consistency_ok={result.consistency_ok}"],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> PM1Result:
        trigger = str(payload.get("trigger", ""))
        ckpt = str(payload.get("checkpoint_status", "completed" if trigger == self.config.trigger_event else "pending"))
        envelope = dict(payload.get("gatekeeper_envelope", payload.get("envelope", {})))
        expected_hash = payload.get("gatekeeper_envelope_hash")
        confirmations = int(payload.get("confirmations", self.config.finality_l1))
        before = dict(payload.get("occupancy_before", {"oracle": 0.5}))
        after = dict(payload.get("occupancy_after", before))
        cte_b = float(payload.get("cte_before", 0.4))
        cte_a = float(payload.get("cte_after", cte_b))
        ab_ok = bool(payload.get("ab_ok", True))
        ba_ok = bool(payload.get("ba_ok", True))
        sandwich = int(payload.get("sandwich_hits", 0))
        frontrun = int(payload.get("frontrun_hits", 0))
        volume = int(payload.get("event_volume", 100))
        signal_ids = list(payload.get("signal_ids", ["sig-0"]))

        tail_r = self.tail.run(trigger, self.config.trigger_event, ckpt)
        imm_r = self.immut.run(envelope, expected_hash)
        fin_r = self.finality.run(confirmations, self.config.finality_l1)
        dri_r = self.drift.run(before, after)
        cte_r = self.cte.run(cte_b, cte_a, self.config.cte_drift_threshold)
        dir_r = self.direction.run(ab_ok, ba_ok)
        int_r = self.interfer.run(sandwich, frontrun, volume)
        has_r = self.hasher.run(signal_ids)
        ver_r = self.composer.run(
            {
                "tail_ok": tail_r["ok"],
                "envelope_ok": imm_r["ok"],
                "cte_stable": cte_r["stable"],
                "direction_ok": dir_r["consistent"],
                "interference_elevated": int_r["elevated"],
                "signal_ids": signal_ids,
                "distorted_ids": list(payload.get("distorted_ids", [])),
            }
        )

        return PM1Result(
            consistency_ok=bool(ver_r["consistency_ok"]),
            distorted_signal_ids=list(ver_r["distorted_signal_ids"]),
            envelope_hash=str(imm_r["hash"]),
            subagent_results={
                TailCompletionGuard.name: tail_r,
                EnvelopeImmutabilityChecker.name: imm_r,
                PreFinalityRejector.name: fin_r,
                OccupancyDriftComparator.name: dri_r,
                CTEStabilityProbe.name: cte_r,
                DirectionConsistencyChecker.name: dir_r,
                MEVInterferenceScorer.name: int_r,
                SignalIntegrityHasher.name: has_r,
                ConsistencyVerdictComposer.name: ver_r,
            },
        )
