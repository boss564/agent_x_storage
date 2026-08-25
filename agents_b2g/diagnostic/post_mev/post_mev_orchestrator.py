"""Post-MEV Orchestrator — PM1 → PM2 → PM3 after mev_tail_completed.

Additive only: does not touch Wave-38 Agents 7–9, Wave-39 §5.4, or Wave-40/K8.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from agents_b2g.diagnostic.post_mev.adversarial_signal_quarantiner import (
    AdversarialSignalQuarantiner,
)
from agents_b2g.diagnostic.post_mev.agents import make_response
from agents_b2g.diagnostic.post_mev.causal_graph_post_mev_reconciler import (
    CausalGraphPostMEVReconciler,
)
from agents_b2g.diagnostic.post_mev.config import PostMEVConfig
from agents_b2g.diagnostic.post_mev.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.post_mev.post_mev_causal_consistency_validator import (
    PostMEVCausalConsistencyValidator,
)
from agents_b2g.diagnostic.post_mev.types import (
    PostMEVBlockCause,
    PostMEVDiagnosticEnvelope,
    PostMEVStatus,
    ReconcileVerdict,
    sha256_hex,
)


TRIGGER_EVENT = "mev_tail_completed"
EVENT_SUBJECT = "mev_tail_completed"


class TriggerGuard:
    name = "TriggerGuard"

    def run(self, trigger: str, checkpoint_status: str, expected: str) -> dict[str, Any]:
        ok = trigger == expected and checkpoint_status == "completed"
        return {"ok": ok, "trigger": trigger, "checkpoint_status": checkpoint_status}


class PipelineSequencer:
    name = "PipelineSequencer"

    def run(self) -> dict[str, Any]:
        return {"order": ["PM1", "PM2", "PM3"], "parallel": False}


class EnvelopeAssembler:
    name = "EnvelopeAssembler"

    def run(self, parts: Mapping[str, Any]) -> PostMEVDiagnosticEnvelope:
        status = PostMEVStatus(parts["status"])
        return PostMEVDiagnosticEnvelope(
            status=status,
            job_id=str(parts["job_id"]),
            trigger="mev_tail_completed",
            gatekeeper_envelope_hash=str(parts.get("gatekeeper_envelope_hash", "")),
            consistency_ok=bool(parts.get("consistency_ok", False)),
            quarantined_count=int(parts.get("quarantined_count", 0)),
            amendments=tuple(parts.get("amendments", ())),
            reconcile_verdict=str(parts.get("reconcile_verdict", ReconcileVerdict.NO_AMENDMENT.value)),
            block_cause=parts.get("block_cause"),
            pm_results=dict(parts.get("pm_results", {})),
        )


class PostMEVOrchestrator:
    """Root: PM1 → PM2 → PM3. Hook via register_mev_tail_hook(EventBus)."""

    agent_name = "PostMEVOrchestrator"

    def __init__(self, user_id: str = "post_mev", config: PostMEVConfig | None = None):
        self.user_id = user_id
        self.config = config or PostMEVConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self.pm1 = PostMEVCausalConsistencyValidator(user_id=user_id, config=self.config)
        self.pm2 = AdversarialSignalQuarantiner(user_id=user_id, config=self.config)
        self.pm3 = CausalGraphPostMEVReconciler(user_id=user_id, config=self.config)
        self.trigger_guard = TriggerGuard()
        self.sequencer = PipelineSequencer()
        self.assembler = EnvelopeAssembler()
        self._last_envelope: PostMEVDiagnosticEnvelope | None = None

    @property
    def last_envelope(self) -> PostMEVDiagnosticEnvelope | None:
        return self._last_envelope

    def run(self, payload: Mapping[str, Any], job_id: str | None = None) -> dict[str, Any]:
        jid = job_id or str(uuid.uuid4())[:12]
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, jid)

    def evaluate(self, payload: Mapping[str, Any], job_id: str | None = None) -> PostMEVDiagnosticEnvelope:
        jid = job_id or str(uuid.uuid4())[:12]
        return self._evaluate(payload, jid)

    def run_from_trigger(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """EventBus callback entry — expects mev_tail_completed semantics."""
        merged = dict(payload)
        merged.setdefault("trigger", TRIGGER_EVENT)
        merged.setdefault("checkpoint_status", "completed")
        return self.run(merged, job_id=str(payload.get("job_id", "")) or None)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        env = self._evaluate(payload, job_id)
        status_map = {
            PostMEVStatus.COMPLETED: "completed",
            PostMEVStatus.BLOCKED: "blocked",
            PostMEVStatus.SKIPPED: "skipped",
        }
        return make_response(
            status_map[env.status],  # type: ignore[arg-type]
            job_id,
            artifacts=[{"type": "post_mev_envelope", "metadata": env.to_dict()}],
            error=env.block_cause,
            logs=[f"status={env.status.value}", f"verdict={env.reconcile_verdict}"],
        )

    def _evaluate(self, payload: Mapping[str, Any], job_id: str) -> PostMEVDiagnosticEnvelope:
        seq = self.sequencer.run()
        trigger = str(payload.get("trigger", ""))
        ckpt = str(payload.get("checkpoint_status", ""))
        guard = self.trigger_guard.run(trigger, ckpt, self.config.trigger_event)

        if not guard["ok"]:
            env = self.assembler.run(
                {
                    "status": PostMEVStatus.SKIPPED.value,
                    "job_id": job_id,
                    "gatekeeper_envelope_hash": "",
                    "consistency_ok": False,
                    "quarantined_count": 0,
                    "amendments": (),
                    "reconcile_verdict": ReconcileVerdict.NO_AMENDMENT.value,
                    "block_cause": PostMEVBlockCause.TRIGGER_MISSING.value,
                    "pm_results": {"trigger_guard": guard, "sequencer": seq},
                }
            )
            self._last_envelope = env
            return env

        envelope = dict(payload.get("gatekeeper_envelope", payload.get("envelope", {"verdict": "RELEASED"})))
        gk_hash = str(payload.get("gatekeeper_envelope_hash") or sha256_hex(envelope))

        pm1_payload = {
            **dict(payload),
            "trigger": trigger,
            "checkpoint_status": ckpt,
            "gatekeeper_envelope": envelope,
            "gatekeeper_envelope_hash": gk_hash,
        }
        pm1 = self.pm1.evaluate(pm1_payload)

        pm2_payload = {
            **dict(payload),
            "capture_events": list(payload.get("capture_events", payload.get("events", []))),
        }
        pm2 = self.pm2.evaluate(pm2_payload, job_id=job_id)

        pm3_payload = {
            **dict(payload),
            "original_pre_reg_hash": str(payload.get("original_pre_reg_hash", "a" * 64)),
            "distorted_signal_ids": pm1.distorted_signal_ids,
            "quarantined_ids": pm2.quarantined_ids,
        }
        pm3 = self.pm3.evaluate(pm3_payload, job_id=job_id)

        if pm3.verdict == ReconcileVerdict.BLOCKED.value:
            status = PostMEVStatus.BLOCKED
            block_cause = pm3.block_cause or PostMEVBlockCause.PRE_REG_MUTATION_ATTEMPT.value
        else:
            status = PostMEVStatus.COMPLETED
            block_cause = None

        env = self.assembler.run(
            {
                "status": status.value,
                "job_id": job_id,
                "gatekeeper_envelope_hash": gk_hash,
                "consistency_ok": pm1.consistency_ok,
                "quarantined_count": pm2.quarantined_count,
                "amendments": tuple(pm3.amendments),
                "reconcile_verdict": pm3.verdict,
                "block_cause": block_cause,
                "pm_results": {
                    "sequencer": seq,
                    "trigger_guard": guard,
                    "pm1": pm1.to_dict(),
                    "pm2": pm2.to_dict(),
                    "pm3": pm3.to_dict(),
                },
            }
        )
        self._last_envelope = env
        return env


def register_mev_tail_hook(bus: Any, orchestrator: PostMEVOrchestrator) -> None:
    """Subscribe Post-MEV pipeline to EventBus subject `mev_tail_completed`.

    Callback receives EventBus envelope `{subject, payload, ...}` or raw payload.
    Never mutates Gatekeeper / Wave-39 / Wave-40 modules.
    """

    def _on_event(message: Mapping[str, Any]) -> None:
        payload = message.get("payload", message)
        if not isinstance(payload, Mapping):
            return
        orchestrator.run_from_trigger(dict(payload))

    bus.subscribe(EVENT_SUBJECT, _on_event)
