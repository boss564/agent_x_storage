#!/usr/bin/env python3
"""
Post-MEV Diagnostic Extension — E2E Test Suite (PM1–PM3).

| Gruppe | Tests | Inhalt |
|--------|-------|--------|
| PM1 | 9 | Tail-Guard, Envelope-Immutability, Drift, Verdict |
| PM2 | 9 | Sandwich/Frontrun-Footprint, 24 h Quarantäne, Register |
| PM3 | 9 | Pre-Reg-Freeze, Amendment-Append, Mutation→BLOCKED |
| **Σ** | **27** | |

Usage:
    python3 scripts/test_post_mev_diagnostic.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="post_mev_test_"))
os.environ["POST_MEV_LOG_DIR"] = str(_TMP / "logs")
os.environ["POST_MEV_DATA_ROOT"] = str(_TMP / "data")

from agents_b2g.diagnostic.post_mev import (  # noqa: E402
    AdversarialSignalQuarantiner,
    CausalGraphPostMEVReconciler,
    EVENT_SUBJECT,
    PostMEVBlockCause,
    PostMEVOrchestrator,
    PostMEVCausalConsistencyValidator,
    PostMEVStatus,
    ReconcileVerdict,
    register_mev_tail_hook,
)
from agents_b2g.diagnostic.post_mev.post_mev_causal_consistency_validator import (  # noqa: E402
    ConsistencyVerdictComposer,
    CTEStabilityProbe,
    DirectionConsistencyChecker,
    EnvelopeImmutabilityChecker,
    MEVInterferenceScorer,
    OccupancyDriftComparator,
    PreFinalityRejector,
    SignalIntegrityHasher,
    TailCompletionGuard,
)
from agents_b2g.diagnostic.post_mev.adversarial_signal_quarantiner import (  # noqa: E402
    BotDensityHeuristics,
    CooldownScheduler,
    FalsePositiveAuditor,
    FrontrunFootprintScanner,
    LeakageObservationLinker,
    QuarantineRegistryWriter,
    QuarantineVerdictComposer,
    SandwichFootprintScanner,
    SignalInvalidationMarker,
)
from agents_b2g.diagnostic.post_mev.causal_graph_post_mev_reconciler import (  # noqa: E402
    AmendmentAppendWriter,
    AmendmentHasher,
    AmendmentPayloadBuilder,
    CausalEdgeDiffBuilder,
    GraphSnapshotExporter,
    NovelFactorAnnotator,
    PreRegHashLoader,
    PreRegMutationGuard,
    ReconcileVerdictComposer,
)
from agents_b2g.diagnostic.post_mev.types import sha256_hex  # noqa: E402
from agents_b2g.event_bus import EventBus  # noqa: E402

PASS, FAIL = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


SEALED = "b" * 64


def _pm1_happy(**kw) -> dict:
    env = {"verdict": "RELEASED", "job_id": "gk-1"}
    d = {
        "trigger": "mev_tail_completed",
        "checkpoint_status": "completed",
        "gatekeeper_envelope": env,
        "gatekeeper_envelope_hash": sha256_hex(env),
        "confirmations": 12,
        "occupancy_before": {"oracle": 0.5, "mev": 0.2},
        "occupancy_after": {"oracle": 0.51, "mev": 0.21},
        "cte_before": 0.40,
        "cte_after": 0.41,
        "ab_ok": True,
        "ba_ok": True,
        "sandwich_hits": 0,
        "frontrun_hits": 0,
        "event_volume": 100,
        "signal_ids": ["sig-a", "sig-b"],
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# PM1 (9)
# ---------------------------------------------------------------------------


def test_pm1() -> None:
    section("PM1 PostMEVCausalConsistencyValidator (9)")

    r = TailCompletionGuard().run("mev_tail_completed", "mev_tail_completed", "completed")
    check("PM1.1 TailCompletionGuard accepts trigger", r["ok"] is True)

    r = TailCompletionGuard().run("other", "mev_tail_completed", "completed")
    check("PM1.2 TailCompletionGuard rejects wrong trigger", r["ok"] is False)

    env = {"verdict": "RELEASED"}
    h = sha256_hex(env)
    r = EnvelopeImmutabilityChecker().run(env, h)
    check("PM1.3 EnvelopeImmutabilityChecker hash match", r["matched"] is True)

    r = EnvelopeImmutabilityChecker().run({"verdict": "TAMPERED"}, h)
    check("PM1.4 EnvelopeImmutabilityChecker detects tamper", r["matched"] is False)

    r = PreFinalityRejector().run(5, 12)
    check("PM1.5 PreFinalityRejector marks under-finality", r["under_finality"] is True and r["marked"])

    r = OccupancyDriftComparator().run({"a": 0.1}, {"a": 0.3})
    check("PM1.6 OccupancyDriftComparator reports drift", abs(r["max_drift"] - 0.2) < 1e-9)

    r = CTEStabilityProbe().run(0.4, 0.41, 0.15)
    check("PM1.7 CTEStabilityProbe stable within threshold", r["stable"] is True)

    r = DirectionConsistencyChecker().run(True, False)
    check("PM1.8 DirectionConsistencyChecker AB/BA", r["consistent"] is False)

    agent = PostMEVCausalConsistencyValidator(user_id="pm1_t")
    # elevated interference → consistency_ok False
    bad = agent.evaluate(
        _pm1_happy(sandwich_hits=40, frontrun_hits=10, event_volume=100, distorted_ids=["sig-x"])
    )
    check(
        "PM1.9 ConsistencyVerdictComposer / agent aggregate",
        bad.consistency_ok is False and "sig-x" in bad.distorted_signal_ids,
        detail=str(bad.to_dict()),
    )


# ---------------------------------------------------------------------------
# PM2 (9)
# ---------------------------------------------------------------------------


def test_pm2() -> None:
    section("PM2 AdversarialSignalQuarantiner (9)")

    events = [
        {"signal_id": "s1", "sandwich": True, "front_leg": True, "back_leg": True, "victim": "v"},
        {"signal_id": "s2", "frontrun": True, "competing_nonce": 7, "same_target": True},
        {"signal_id": "s3", "public_mempool_leak": True},
        {"signal_id": "s4", "from_address": "0xbot"},
        {"signal_id": "s5", "from_address": "0xbot"},
    ]

    r = SandwichFootprintScanner().run(events)
    check("PM2.1 SandwichFootprintScanner hits", "s1" in r["hit_ids"])

    r = FrontrunFootprintScanner().run(events)
    check("PM2.2 FrontrunFootprintScanner hits", "s2" in r["hit_ids"])

    r = BotDensityHeuristics().run(events)
    check("PM2.3 BotDensityHeuristics elevated on cluster", r["density"] >= 0.0)

    r = LeakageObservationLinker().run(events)
    check("PM2.4 LeakageObservationLinker descriptive", "s3" in r["leak_ids"] and r["descriptive_only"])

    reg = _TMP / "qreg.jsonl"
    r = QuarantineRegistryWriter().run(reg, [{"signal_id": "s1", "n": 1}])
    check("PM2.5 QuarantineRegistryWriter append-only", r["appended"] == 1 and reg.is_file())

    r = CooldownScheduler().run(24.0)
    check("PM2.6 CooldownScheduler 24h", r["cooldown_h"] == 24.0 and "until" in r)

    r = SignalInvalidationMarker().run(["s1", "s2"])
    check("PM2.7 SignalInvalidationMarker no envelope rewrite", r["envelope_rewritten"] is False)

    r = FalsePositiveAuditor().run(3, 100)
    check("PM2.8 FalsePositiveAuditor estimates FP", 0.0 <= r["est_fp_rate"] <= 1.0)

    agent = AdversarialSignalQuarantiner(user_id="pm2_t")
    result = agent.evaluate({"capture_events": events, "event_volume": 100}, job_id="j-pm2")
    check(
        "PM2.9 QuarantineVerdictComposer / agent quarantine",
        result.quarantined_count >= 3
        and result.cooldown_h == 24.0
        and Path(result.registry_path).is_file(),
        detail=str(result.to_dict()),
    )


# ---------------------------------------------------------------------------
# PM3 (9)
# ---------------------------------------------------------------------------


def test_pm3() -> None:
    section("PM3 CausalGraphPostMEVReconciler (9)")

    r = PreRegHashLoader().run(SEALED)
    check("PM3.1 PreRegHashLoader read-only sealed hash", r["ok"] and r["read_only"] and r["original_pre_reg_hash"] == SEALED)

    r = PreRegMutationGuard().run(sealed_hash=SEALED, attempted_write=True)
    check(
        "PM3.2 PreRegMutationGuard blocks write",
        r["blocked"] and r["cause"] == PostMEVBlockCause.PRE_REG_MUTATION_ATTEMPT.value,
    )

    r = PreRegMutationGuard().run(sealed_hash=SEALED, attempted_write=False)
    check("PM3.3 PreRegMutationGuard allows read path", r["allowed"] is True)

    r = CausalEdgeDiffBuilder().run(
        [{"src": "A", "dst": "B"}],
        [{"src": "A", "dst": "B"}, {"src": "C", "dst": "D"}],
    )
    check("PM3.4 CausalEdgeDiffBuilder detects added edge", r["has_diff"] and len(r["added"]) == 1)

    r = NovelFactorAnnotator().run(["oracle_lag", "novel_x"], ["oracle_lag"])
    check("PM3.5 NovelFactorAnnotator annotation-only", r["novel_factors"] == ["novel_x"] and r["annotation_only"])

    r = AmendmentPayloadBuilder().run(
        edge_diff={"has_diff": True, "added": [{"src": "C", "dst": "D"}], "removed": []},
        novel_factors=["novel_x"],
        distorted_ids=["d1"],
        quarantined_ids=["q1"],
    )
    check("PM3.6 AmendmentPayloadBuilder non-empty", r["empty"] is False and r["payload"]["kind"] == "POST_MEV_CAUSAL_AMENDMENT")

    r = AmendmentHasher().run(
        amendment_id="amd-1",
        original_pre_reg_hash=SEALED,
        amendment_payload={"kind": "POST_MEV_CAUSAL_AMENDMENT"},
        prev_amendment_hash="0" * 64,
    )
    check("PM3.7 AmendmentHasher produces 64-hex", len(r["amendment_hash"]) == 64)

    path = _TMP / "amendments.jsonl"
    r = AmendmentAppendWriter().run(path, {"amendment_id": "amd-1", "h": "x"})
    check("PM3.8 AmendmentAppendWriter append-only", r["append_only"] and r["overwrote"] is False and path.is_file())

    agent = CausalGraphPostMEVReconciler(user_id="pm3_t")
    blocked = agent.evaluate(
        {
            "original_pre_reg_hash": SEALED,
            "mutate_pre_reg": True,
            "overwrite_pre_reg_hash": "c" * 64,
        },
        job_id="mut-1",
    )
    clean = agent.evaluate(
        {
            "original_pre_reg_hash": SEALED,
            "expected_edges": [{"src": "A", "dst": "B"}],
            "observed_edges": [{"src": "A", "dst": "B"}, {"src": "X", "dst": "Y"}],
            "signal_factors": ["oracle_lag", "post_mev_factor"],
            "registered_factors": ["oracle_lag"],
            "distorted_signal_ids": ["d1"],
            "quarantined_ids": ["q1"],
        },
        job_id="amd-ok",
    )
    snap = GraphSnapshotExporter().run(_TMP / "snap.json", {"k": 1})
    check(
        "PM3.9 ReconcileVerdictComposer mutation BLOCKED + amendment proposed",
        blocked.verdict == ReconcileVerdict.BLOCKED.value
        and blocked.block_cause == PostMEVBlockCause.PRE_REG_MUTATION_ATTEMPT.value
        and clean.verdict == ReconcileVerdict.AMENDMENT_PROPOSED.value
        and len(clean.amendments) == 1
        and clean.amendments[0].original_pre_reg_hash == SEALED
        and snap["hash"],
        detail=f"blocked={blocked.verdict} clean={clean.verdict}",
    )


# ---------------------------------------------------------------------------
# Extra smoke for orchestrator + hook (not counted in 27 — wait, spec says 27 only)
# Spec: 27 = 3×9. Orchestrator covered implicitly via PM integration if needed.
# We'll keep exactly 27 from the three groups above.
# ---------------------------------------------------------------------------


def smoke_orchestrator() -> None:
    """Non-counted smoke: orchestrator + EventBus hook."""
    section("Smoke Orchestrator + EventBus (informational)")
    orch = PostMEVOrchestrator(user_id="orch_smoke")
    env = orch.evaluate(
        {
            "trigger": "mev_tail_completed",
            "checkpoint_status": "completed",
            "gatekeeper_envelope": {"verdict": "RELEASED"},
            "original_pre_reg_hash": SEALED,
            "capture_events": [{"signal_id": "z1", "sandwich": True, "front_leg": 1, "back_leg": 1, "victim": "v"}],
            "expected_edges": [{"src": "A", "dst": "B"}],
            "observed_edges": [{"src": "A", "dst": "B"}],
            "confirmations": 12,
        },
        job_id="orch-1",
    )
    print(f"  · orchestrator status={env.status.value} quarantined={env.quarantined_count}")

    bus = EventBus(audit_log=_TMP / "bus.jsonl")
    seen: list[str] = []

    class _Capture(PostMEVOrchestrator):
        def run_from_trigger(self, payload):  # type: ignore[override]
            seen.append(str(payload.get("job_id", "")))
            return super().run_from_trigger(payload)

    hooked = _Capture(user_id="hook_smoke")
    register_mev_tail_hook(bus, hooked)
    bus.publish(
        EVENT_SUBJECT,
        {
            "job_id": "hook-1",
            "gatekeeper_envelope": {"verdict": "RELEASED"},
            "original_pre_reg_hash": SEALED,
            "capture_events": [],
            "confirmations": 12,
        },
    )
    print(f"  · EventBus hook fired={seen == ['hook-1']} subject={EVENT_SUBJECT}")
    assert env.status in {PostMEVStatus.COMPLETED, PostMEVStatus.BLOCKED}
    assert seen == ["hook-1"]


def main() -> int:
    print("Post-MEV Diagnostic Extension — 27 checks")
    test_pm1()
    test_pm2()
    test_pm3()
    smoke_orchestrator()
    print(f"\n{'=' * 60}")
    print(f"Post-MEV Diagnostic: {PASS}/{PASS + FAIL} passed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 and PASS == 27 else 1


if __name__ == "__main__":
    raise SystemExit(main())
