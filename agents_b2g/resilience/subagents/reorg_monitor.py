"""A1 — ReorgMonitor (Wave 40 Quadrant 1 / Infra).

Nine subagents: BlockDepthTracker → RecoveryObserver.
Finality-Gate: ≥12 L1 / ≥64 L2 confirmations before causal signals execute.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from agents_b2g.resilience.agents import make_response
from agents_b2g.resilience.config import ResilienceConfig
from agents_b2g.resilience.logging_utils import JSONLogger, _safe_call
from agents_b2g.resilience.types import ChainLayer


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class BlockDepthTracker:
    """Track confirmation depth relative to tip."""

    name = "BlockDepthTracker"

    def run(self, tip: int, signal_block: int) -> dict[str, Any]:
        depth = max(0, tip - signal_block)
        return {"depth": depth, "tip": tip, "signal_block": signal_block}


class FinalityThresholdEvaluator:
    """Compare depth against L1/L2 finality thresholds."""

    name = "FinalityThresholdEvaluator"

    def __init__(self, config: ResilienceConfig):
        self.config = config

    def run(self, depth: int, layer: ChainLayer) -> dict[str, Any]:
        threshold = (
            self.config.finality_l1 if layer == ChainLayer.L1 else self.config.finality_l2
        )
        return {
            "layer": layer.value,
            "depth": depth,
            "threshold": threshold,
            "finality_ok": depth >= threshold,
        }


class AncestorHashVerifier:
    """Verify parent/ancestor hash continuity (mock-capable)."""

    name = "AncestorHashVerifier"

    def run(
        self,
        block_hash: str,
        parent_hash: str,
        expected_parent: str | None = None,
    ) -> dict[str, Any]:
        expected = expected_parent or parent_hash
        ok = bool(block_hash) and parent_hash == expected and len(block_hash) >= 8
        digest = hashlib.sha256(f"{parent_hash}:{block_hash}".encode()).hexdigest()[:16]
        return {"ok": ok, "chain_digest": digest, "parent_hash": parent_hash}


class ReorgSeverityScorer:
    """Score reorg depth: 0=none, 1=shallow, 2=mid, 3=deep."""

    name = "ReorgSeverityScorer"

    def run(self, reorg_depth: int, finality_threshold: int) -> dict[str, Any]:
        if reorg_depth <= 0:
            severity = 0
            label = "none"
        elif reorg_depth < min(5, finality_threshold):
            severity = 1
            label = "shallow"
        elif reorg_depth < finality_threshold:
            severity = 2
            label = "mid"
        else:
            severity = 3
            label = "deep"
        return {"reorg_depth": reorg_depth, "severity": severity, "label": label}


class SignalInvalidator:
    """Invalidate causal signals when reorg crosses signal block."""

    name = "SignalInvalidator"

    def run(self, signal_ids: list[str], reorg_depth: int, signal_depth: int) -> dict[str, Any]:
        invalidate = reorg_depth > 0 and reorg_depth >= signal_depth
        invalidated = list(signal_ids) if invalidate else []
        return {
            "invalidate": invalidate,
            "invalidated_signals": invalidated,
            "count": len(invalidated),
        }


class RollbackCascader:
    """Plan rollback cascade for dependent execution steps."""

    name = "RollbackCascader"

    def run(self, severity: int, dependent_jobs: list[str]) -> dict[str, Any]:
        cascade = list(dependent_jobs) if severity >= 2 else []
        return {"cascade_jobs": cascade, "cascade_required": bool(cascade), "severity": severity}


class ConfirmationWaiter:
    """Compute remaining confirmations until finality."""

    name = "ConfirmationWaiter"

    def run(self, depth: int, threshold: int) -> dict[str, Any]:
        remaining = max(0, threshold - depth)
        return {"remaining": remaining, "ready": remaining == 0, "depth": depth}


class ChainForkDetector:
    """Detect competing tips (fork) from tip hashes."""

    name = "ChainForkDetector"

    def run(self, tip_hashes: list[str]) -> dict[str, Any]:
        unique = sorted(set(h for h in tip_hashes if h))
        forked = len(unique) > 1
        return {"forked": forked, "tip_count": len(unique), "tips": unique[:8]}


class RecoveryObserver:
    """Observe post-reorg recovery / tip stabilization."""

    name = "RecoveryObserver"

    def run(self, forked: bool, severity: int, finality_ok: bool) -> dict[str, Any]:
        if forked or severity >= 3:
            state = "recovering"
        elif severity > 0 and not finality_ok:
            state = "waiting"
        elif finality_ok:
            state = "stable"
        else:
            state = "pending"
        return {"recovery_state": state, "stable": state == "stable"}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class ReorgMonitorResult:
    finality_ok: bool
    depth: int
    threshold: int
    layer: str
    severity: int
    severity_label: str
    invalidated_signals: list[str]
    recovery_state: str
    forked: bool
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finality_ok": self.finality_ok,
            "depth": self.depth,
            "threshold": self.threshold,
            "layer": self.layer,
            "severity": self.severity,
            "severity_label": self.severity_label,
            "invalidated_signals": self.invalidated_signals,
            "recovery_state": self.recovery_state,
            "forked": self.forked,
            "subagents": self.subagent_results,
        }


class ReorgMonitor:
    """A1 — chain reorg detection and finality gate."""

    agent_name = "ReorgMonitor"

    def __init__(self, user_id: str = "wave40", config: ResilienceConfig | None = None):
        self.user_id = user_id
        self.config = config or ResilienceConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.block_depth = BlockDepthTracker()
        self.finality_eval = FinalityThresholdEvaluator(self.config)
        self.ancestor = AncestorHashVerifier()
        self.severity = ReorgSeverityScorer()
        self.invalidator = SignalInvalidator()
        self.rollback = RollbackCascader()
        self.waiter = ConfirmationWaiter()
        self.fork = ChainForkDetector()
        self.recovery = RecoveryObserver()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any]) -> ReorgMonitorResult:
        return self._evaluate(payload)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload)
        status = "completed" if result.finality_ok and result.severity < 3 else (
            "blocked" if result.severity >= 3 or result.forked else "completed"
        )
        if not result.finality_ok and result.severity == 0:
            status = "completed"  # waiting for confirmations is not a hard block
        artifact = {
            "type": "reorg_monitor_result",
            "path": str(self._tenant / f"reorg_{job_id}.json"),
            "metadata": result.to_dict(),
        }
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[artifact],
            logs=[
                f"finality_ok={result.finality_ok}",
                f"severity={result.severity_label}",
                f"recovery={result.recovery_state}",
            ],
        )

    def _evaluate(self, payload: Mapping[str, Any]) -> ReorgMonitorResult:
        tip = int(payload.get("tip_block", payload.get("tip", 0)))
        signal_block = int(payload.get("signal_block", tip))
        layer_raw = str(payload.get("layer", "L1")).upper()
        layer = ChainLayer.L2 if layer_raw == "L2" else ChainLayer.L1
        reorg_depth = int(payload.get("reorg_depth", 0))
        block_hash = str(payload.get("block_hash", "0xabc12345"))
        parent_hash = str(payload.get("parent_hash", "0xparent00"))
        expected_parent = payload.get("expected_parent")
        signal_ids = list(payload.get("signal_ids", []))
        dependent_jobs = list(payload.get("dependent_jobs", []))
        tip_hashes = list(payload.get("tip_hashes", [block_hash]))

        depth_r = self.block_depth.run(tip, signal_block)
        fin_r = self.finality_eval.run(depth_r["depth"], layer)
        anc_r = self.ancestor.run(block_hash, parent_hash, expected_parent)
        sev_r = self.severity.run(reorg_depth, fin_r["threshold"])
        inv_r = self.invalidator.run(signal_ids, reorg_depth, depth_r["depth"])
        rb_r = self.rollback.run(sev_r["severity"], dependent_jobs)
        wait_r = self.waiter.run(depth_r["depth"], fin_r["threshold"])
        fork_r = self.fork.run(tip_hashes)
        rec_r = self.recovery.run(fork_r["forked"], sev_r["severity"], fin_r["finality_ok"])

        finality_ok = bool(fin_r["finality_ok"] and anc_r["ok"] and not fork_r["forked"])
        if sev_r["severity"] >= 3:
            finality_ok = False

        return ReorgMonitorResult(
            finality_ok=finality_ok,
            depth=depth_r["depth"],
            threshold=fin_r["threshold"],
            layer=layer.value,
            severity=sev_r["severity"],
            severity_label=sev_r["label"],
            invalidated_signals=inv_r["invalidated_signals"],
            recovery_state=rec_r["recovery_state"],
            forked=fork_r["forked"],
            subagent_results={
                BlockDepthTracker.name: depth_r,
                FinalityThresholdEvaluator.name: fin_r,
                AncestorHashVerifier.name: anc_r,
                ReorgSeverityScorer.name: sev_r,
                SignalInvalidator.name: inv_r,
                RollbackCascader.name: rb_r,
                ConfirmationWaiter.name: wait_r,
                ChainForkDetector.name: fork_r,
                RecoveryObserver.name: rec_r,
            },
        )
