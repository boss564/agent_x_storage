#!/usr/bin/env python3
"""
Wave 38 E2E Test Suite — Causal Audit & Signal Guard (contract-first).

Group 9: GatekeeperDispatcherAgent + DiagnosticSignalEnvelope contract.
Additional groups stubbed for future 81-subagent expansion.

Usage:
    python3 scripts/test_wave38_diagnostic.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents_b2g.diagnostic.cte_entropy_engine_agent import CTEEntropyEngineAgent
from agents_b2g.diagnostic.cte_math import classify_role, compute_verdict, run_cte_analysis
from agents_b2g.diagnostic.data_ingestion_agent import DataIngestionAgent
from agents_b2g.diagnostic.fixtures import make_mock_bundle
from agents_b2g.diagnostic.live_prereg import Wave38Thresholds, load_wave38_thresholds
from agents_b2g.diagnostic.intent_and_stablecoin_agent import IntentAndStablecoinAgent
from agents_b2g.diagnostic.intent_stable_lib import (
    MIN_COVERAGE_INTENT_STABLE,
    TOPIC_BY_EVENT,
    WRONG_COW_TRADE_8,
    WRONG_PSM_BUY_4,
    fixture_intent_resolved,
    fixture_stable_resolved,
    topic_for,
)
from agents_b2g.diagnostic.liquidation_cascade_agent import LiquidationCascadeAgent
from agents_b2g.diagnostic.liquidation_lib import (
    MIN_COVERAGE_LIQ,
    TOPIC_LIQUIDATION_CALL,
    encode_liquidation_call_log,
    fixture_resolved_pools,
    parse_liquidation_log,
)
from agents_b2g.diagnostic.mev_capture_agent import MEVCaptureAgent
from agents_b2g.diagnostic.mev_lib import (
    FIXTURE_EXCLUDED,
    load_exclusion_list,
    minute_bucket,
    normalize_address,
)
from agents_b2g.diagnostic.oracle_lib import TOPIC_ANSWER_UPDATED, is_excluded_feed
from agents_b2g.diagnostic.oracle_signal_agent import OracleSignalAgent
from agents_b2g.diagnostic.pre_reg_fdr_guard_agent import PreRegFDRGuardAgent
from agents_b2g.diagnostic.resampling_invariance_agent import ResamplingInvarianceAgent
from agents_b2g.diagnostic.resampling_math import (
    fold_ranges_for_n,
    run_lag_spearman_resampling,
    spearman_rho,
)
from agents_b2g.diagnostic.subagents.data_ingestion import (
    CheckpointWriter,
    IngestionConfig,
    RawEventStorer,
)
from agents_b2g.diagnostic.subagents.intent_stable_capture import IntentStableConfig
from agents_b2g.diagnostic.subagents.liquidation_capture import LiquidationConfig
from agents_b2g.diagnostic.subagents.mev_capture import MEVConfig
from agents_b2g.diagnostic.subagents.oracle_capture import OracleConfig
from agents_b2g.diagnostic.wave38_analysis_pipeline import Wave38AnalysisPipeline
from agents_b2g.diagnostic.wave38_capture_pipeline import (
    OCCUPANCY_ARCHIVE_REQUIRED_KEYS,
    Wave38CaptureToCTEPipeline,
    load_occupancy_archive,
)
from agents_b2g.diagnostic.wave38_full_pipeline import (
    ENVELOPE_REQUIRED_KEYS,
    Wave38FullPipeline,
)
from agents_b2g.diagnostic.config import DiagnosticConfig
from agents_b2g.diagnostic.gatekeeper_dispatcher_agent import GatekeeperDispatcherAgent
from agents_b2g.diagnostic.reference_guard import (
    ReferenceArtifactGuard,
    ReferenceWriteForbiddenError,
    resolve_live_root,
)
from agents_b2g.diagnostic.types import (
    StageContext,
    BlockCause,
    BlockedSignal,
    CandidateRole,
    CollapseInfo,
    DiagnosticSignalEnvelope,
    DiagnosticVerdict,
    DirectionId,
    FDRResult,
    GateAction,
    ReleasedSignal,
    envelope_for_verdict,
    validate_signal_envelope,
)


PASS = FAIL = 0


def _check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}: {detail}")


def test_diagnostic_verdict_enum():
    _check(
        "verdict_taxonomy",
        DiagnosticVerdict.DIAG_SIGNAL_VALID.value == "DIAG_SIGNAL_VALID",
    )


def test_block_cause_enum():
    _check(
        "block_cause_filter_artifact",
        BlockCause.FILTER_ARTIFACT.value == "FILTER_ARTIFACT",
    )
    _check(
        "block_cause_inert_encoding",
        BlockCause.INERT_ENCODING.value == "INERT_ENCODING",
    )


def test_envelope_frozen():
    env = envelope_for_verdict(
        verdict=DiagnosticVerdict.DIAG_SIGNAL_VALID,
        run_id="r1",
        seed=1,
        prereg_version="test",
        s_tau={"chainlink": {"ab": 0.1, "ba": 0.2}},
        fdr_status=FDRResult(n_tests=1, q=0.05, n_rejected=0, passed=True),
        collapse_info=CollapseInfo(),
        released_signals=(
            ReleasedSignal(
                candidate_id="chainlink",
                direction=DirectionId.AB,
                s_tau=0.1,
                role=CandidateRole.CLEANSING_WORKER,
            ),
        ),
    )
    try:
        env.verdict = DiagnosticVerdict.DIAG_INCONCLUSIVE  # type: ignore[misc]
        _check("envelope_frozen", False, "mutation allowed")
    except dataclasses.FrozenInstanceError:
        _check("envelope_frozen", True)


def test_validate_blocked_requires_cause():
    bad = DiagnosticSignalEnvelope(
        verdict=DiagnosticVerdict.DIAG_FILTER_ARTIFACT,
        gate_action=GateAction.BLOCKED,
        s_tau={"x": {"ab": 1.0, "ba": 1.0}},
        fdr_status=FDRResult(n_tests=1, q=0.05, n_rejected=0, passed=False),
        collapse_info=CollapseInfo(),
        released_signals=(),
        blocked_signals=(
            BlockedSignal(
                candidate_id="x",
                direction=DirectionId.AB,
                cause=BlockCause.FILTER_ARTIFACT,
                detail="test",
            ),
        ),
        cause=None,
        run_id="r",
        seed=0,
        prereg_version="t",
        timestamp_utc="2026-08-22T00:00:00+00:00",
    )
    errs = validate_signal_envelope(bad)
    _check("blocked_requires_cause", any("cause" in e.lower() for e in errs), str(errs))


def test_envelope_to_dict_roundtrip_keys():
    env = envelope_for_verdict(
        verdict=DiagnosticVerdict.DIAG_SIGNAL_VALID,
        run_id="roundtrip",
        seed=20260822,
        prereg_version="skeleton",
        s_tau={"chainlink": {"ab": 0.03, "ba": 0.05}},
        fdr_status=FDRResult(n_tests=310, q=0.05, n_rejected=0, passed=True),
        collapse_info=CollapseInfo(cleansing_workers=("chainlink",)),
        released_signals=(
            ReleasedSignal(
                candidate_id="chainlink",
                direction=DirectionId.AB,
                s_tau=0.03,
                role=CandidateRole.CLEANSING_WORKER,
            ),
        ),
    )
    payload = env.to_dict()
    for key in (
        "verdict",
        "gate_action",
        "s_tau",
        "fdr_status",
        "collapse_info",
        "released_signals",
        "blocked_signals",
        "cause",
        "run_id",
        "seed",
        "prereg_version",
    ):
        _check(f"envelope_key_{key}", key in payload, f"missing {key}")


def test_gatekeeper_released_skeleton():
    agent = GatekeeperDispatcherAgent(user_id="test_wave38")
    result = agent.run({"user_id": "test_wave38", "options": {}}, "job-released")
    _check("gatekeeper_status", result["status"] == "completed", result.get("error"))
    meta = result["artifacts"][0]["metadata"]
    _check("gatekeeper_released_action", meta["gate_action"] == "RELEASED")
    _check("gatekeeper_released_verdict", meta["verdict"] == "DIAG_SIGNAL_VALID")
    _check("gatekeeper_has_s_tau", bool(meta.get("s_tau")))
    _check("gatekeeper_released_signals", len(meta.get("released_signals", [])) >= 1)


def test_gatekeeper_blocked_with_cause():
    agent = GatekeeperDispatcherAgent(user_id="test_wave38")
    result = agent.run(
        {"user_id": "test_wave38", "options": {}},
        "job-blocked",
        verdict=DiagnosticVerdict.DIAG_FILTER_ARTIFACT,
        cause=BlockCause.FILTER_ARTIFACT,
    )
    _check("gatekeeper_blocked_status", result["status"] == "completed", result.get("error"))
    meta = result["artifacts"][0]["metadata"]
    _check("gatekeeper_blocked_action", meta["gate_action"] == "BLOCKED")
    _check("gatekeeper_blocked_cause", meta["cause"] == "FILTER_ARTIFACT")
    _check("gatekeeper_blocked_signals", len(meta.get("blocked_signals", [])) >= 1)


def test_gatekeeper_rejects_blocked_without_cause():
    agent = GatekeeperDispatcherAgent(user_id="test_wave38")
    result = agent.run(
        {"user_id": "test_wave38", "options": {}},
        "job-no-cause",
        verdict=DiagnosticVerdict.DIAG_INCONCLUSIVE,
        cause=None,
    )
    _check("gatekeeper_no_cause_failed", result["status"] == "failed")
    _check(
        "gatekeeper_no_cause_message",
        "cause" in (result.get("error") or "").lower(),
    )


def test_live_blocked_without_prereg():
    agent = GatekeeperDispatcherAgent(user_id="test_wave38")
    missing = DiagnosticConfig.LIVE_PRE_REG
    if missing.is_file():
        _check("live_prereg_skip", True)
        return
    result = agent.run(
        {"options": {"live": True}},
        "job-live",
    )
    _check("live_blocked_status", result["status"] == "failed")
    _check(
        "live_blocked_message",
        "live" in (result.get("error") or "").lower()
        or "prereg" in (result.get("error") or "").lower(),
    )


def test_live_prereg_final_bindend_content():
    """3d-viii: Pre-Reg must be bindend with operative §1 and Agent-X §7."""
    path = DiagnosticConfig.LIVE_PRE_REG
    _check("prereg_file", path.is_file())
    text = path.read_text(encoding="utf-8")
    _check("prereg_marked_bindend", "**bindend**" in text.lower())
    _check(
        "prereg_operative_not_science",
        "keine neue wissenschaftliche Evidenz" in text
        or "keine** neue wissenschaftliche" in text
        or "Operatives Monitoring" in text,
    )
    _check(
        "prereg_wave24_28",
        "Wave 24" in text and "Wave 28" in text,
    )
    _check("prereg_ax_multitenancy", "Multi-Tenancy" in text)
    _check("prereg_ax_gobd", "GoBD" in text and "WORM" in text)
    _check(
        "prereg_ax_envelope",
        "DiagnosticSignalEnvelope" in text or '"status"' in text,
    )
    _check("prereg_ax_eventbus", "EventBus" in text)
    _check("prereg_verdict_priority", "unclassified" in text.lower() or "n_unclassified" in text)
    _check("prereg_rho_spearman", "RHO_SPEARMAN_MIN" in text and "0.90" in text)
    th = load_wave38_thresholds()
    _check("prereg_load_ok", th.rho_spearman_min == 0.90)
    _check("prereg_unstable_max", th.n_unstable_folds_max == 1)


def test_live_allowed_when_prereg_bindend():
    """Gatekeeper must not block --live when Pre-Reg exists and is bindend."""
    if not DiagnosticConfig.LIVE_PRE_REG.is_file():
        _check("live_allow_skip", True)
        return
    # Ensure loader accepts current file
    load_wave38_thresholds()
    agent = GatekeeperDispatcherAgent(user_id="test_wave38")
    result = agent.run(
        {"options": {"live": True, "seed": 20260822}},
        "job-live-ok",
    )
    _check(
        "live_allow_status",
        result["status"] == "completed",
        result.get("error"),
    )


def test_live_blocked_when_prereg_not_bindend():
    """Structural: non-bindend Pre-Reg must fail load_wave38_thresholds."""
    with tempfile.TemporaryDirectory() as tmp:
        stub = Path(tmp) / "WAVE38_LIVE_PREREG.md"
        stub.write_text("# Stub\nStatus: draft\n| `EPS_INERT` | 0.001 |\n", encoding="utf-8")
        try:
            load_wave38_thresholds(stub)
            _check("prereg_not_bindend_raises", False)
        except Exception as exc:
            _check(
                "prereg_not_bindend_raises",
                "bindend" in str(exc).lower() or "LivePreReg" in type(exc).__name__,
            )


def test_reference_guard_blocks_write():
    guard = ReferenceArtifactGuard(ROOT)
    existing = [p for p in guard.registered_paths if p.is_file()]
    if not existing:
        _check("reference_guard_write_skip", True)
        return
    target = existing[0]
    try:
        guard.assert_write_allowed(target)
        _check("reference_guard_write_blocked", False, "write allowed on reference")
    except ReferenceWriteForbiddenError:
        _check("reference_guard_write_blocked", True)


def test_live_path_separate_from_reference():
    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp)
        live = resolve_live_root(data_root, "tenant_a")
        live.mkdir(parents=True)
        probe = live / "capture.jsonl"
        probe.write_text("{}\n", encoding="utf-8")
        guard = ReferenceArtifactGuard(ROOT)
        try:
            guard.assert_write_allowed(probe)
            _check("live_path_writable", True)
        except ReferenceWriteForbiddenError as exc:
            _check("live_path_writable", False, str(exc))


def test_wave38_live_root_helper():
    path = DiagnosticConfig.wave38_live_root("u1")
    _check("live_root_suffix", str(path).endswith("wave38/live"))


def _fast_thresholds() -> Wave38Thresholds:
    base = load_wave38_thresholds()
    return Wave38Thresholds(
        eps_inert=base.eps_inert,
        tau_cleansing=base.tau_cleansing,
        rho_collapse=base.rho_collapse,
        occ_sat=base.occ_sat,
        alpha_perm=base.alpha_perm,
        fdr_q=base.fdr_q,
        p_sign_min=base.p_sign_min,
        rho_spearman_min=base.rho_spearman_min,
        k_folds=base.k_folds,
        n_unstable_folds_max=base.n_unstable_folds_max,
        n_perm_shifts=5,
        seed_default=base.seed_default,
    )


def test_live_prereg_thresholds_load():
    th = load_wave38_thresholds()
    _check("live_prereg_eps_inert", th.eps_inert == 0.001)
    _check("live_prereg_tau_cleansing", th.tau_cleansing == 0.05)
    _check("live_prereg_occ_sat", th.occ_sat == 0.90)
    _check("live_prereg_rho_spearman", th.rho_spearman_min == 0.90)
    _check("live_prereg_k_folds", th.k_folds == 9)


def test_cte_math_classify_role():
    th = _fast_thresholds()
    role, _ = classify_role(
        rel_loo=0.10,
        perm_neutral=True,
        perm_collapse=0.8,
        byte_identical=False,
        thresholds=th,
    )
    _check("classify_cleansing_worker", role == "cleansing_worker")


def test_agent6_mock_bundle():
    bundle = make_mock_bundle(n_bins=256, seed=7)
    result = run_cte_analysis(bundle, _fast_thresholds(), seed=7)
    _check("agent6_s_tau_nonempty", bool(result.s_tau_by_candidate))
    _check("agent6_perm_fragment", result.perm_fragment in {"PERM_PASS", "PERM_FAIL"})
    _check("agent6_roles_all_candidates", len(result.roles) == len(bundle.candidate_ids))


def test_agent8_informativity_then_verdict():
    bundle = make_mock_bundle(n_bins=128, seed=11)
    th = _fast_thresholds()
    ctx = StageContext(
        run_id="a8",
        user_id="test_wave38",
        job_id="a8",
        data_root="mock",
        seed=th.seed_default,
        prereg_version="WAVE38_LIVE_PREREG.md",
    )
    guard = PreRegFDRGuardAgent("test_wave38")
    pre = guard.run(ctx, bundle=bundle, thresholds=th)
    _check("agent8_informativity_ok", pre["status"] == "completed")
    _check("agent8_encoding_map", "encoding_inert" in ctx.stage_outputs)

    cte = CTEEntropyEngineAgent("test_wave38").run(
        ctx,
        bundle=bundle,
        thresholds=th,
        encoding_inert=ctx.stage_outputs.get("encoding_inert"),
    )
    _check("agent6_stage_ok", cte["status"] == "completed")

    post = guard.run(ctx, bundle=None, thresholds=th)
    _check("agent8_verdict_ok", post["status"] == "completed")
    verdict = ctx.stage_outputs.get("preliminary_verdict")
    _check(
        "agent8_verdict_value",
        str(getattr(verdict, "value", verdict))
        in {"DIAG_SIGNAL_VALID", "DIAG_FILTER_ARTIFACT", "DIAG_INCONCLUSIVE"},
    )


def test_e2e_stages_6_8_9():
    pipeline = Wave38AnalysisPipeline(user_id="test_wave38")
    bundle = make_mock_bundle(n_bins=256, seed=99)
    result = pipeline.run_stages_6_7_8_9(
        bundle,
        job_id="e2e-6-7-8-9",
        thresholds=_fast_thresholds(),
    )
    _check("e2e_status", result["status"] == "completed", result.get("error"))
    meta = result["artifacts"][0]["metadata"]
    _check("e2e_envelope_verdict", "verdict" in meta)
    _check("e2e_pipeline_meta", "pipeline" in meta)
    _check("e2e_bundle_mock", meta["pipeline"]["bundle_source"] == "mock")
    _check(
        "e2e_stages_include_7",
        "7_resampling" in meta["pipeline"]["stages"],
    )
    _check(
        "e2e_resampling_fragment",
        meta["pipeline"].get("resampling_fragment")
        in {"KFOLD_STABLE", "KFOLD_UNSTABLE"},
    )
    _check(
        "e2e_gate_action",
        meta["gate_action"] in {"RELEASED", "BLOCKED"},
    )
    if meta["gate_action"] == "BLOCKED":
        _check("e2e_blocked_has_cause", meta.get("cause") is not None)


def test_spearman_perfect_correlation():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    _check("spearman_perfect", abs(spearman_rho(x, y) - 1.0) < 1e-9)


def test_spearman_constant_is_zero():
    _check("spearman_constant", spearman_rho([1, 1, 1], [1, 2, 3]) == 0.0)


def test_fold_ranges_cover_bins():
    ranges = fold_ranges_for_n(100, 9)
    _check("fold_count", len(ranges) == 9)
    _check("fold_start", ranges[0][0] == 0)
    _check("fold_end", ranges[-1][1] == 100)


def test_agent7_lag_spearman():
    bundle = make_mock_bundle(n_bins=270, seed=21)
    th = _fast_thresholds()
    result = run_lag_spearman_resampling(bundle, th)
    _check(
        "agent7_fragment",
        result.resampling_fragment in {"KFOLD_STABLE", "KFOLD_UNSTABLE"},
    )
    _check("agent7_n_folds", len(result.folds) == th.k_folds)
    _check("agent7_p_sign_descriptive", "note" in result.p_sign_descriptive)

    ctx = StageContext(
        run_id="a7",
        user_id="test_wave38",
        job_id="a7",
        data_root="mock",
        seed=th.seed_default,
        prereg_version="WAVE38_LIVE_PREREG.md",
    )
    agent = ResamplingInvarianceAgent("test_wave38")
    out = agent.run(ctx, bundle=bundle, thresholds=th)
    _check("agent7_status", out["status"] == "completed", out.get("error"))
    _check(
        "agent7_ctx_fragment",
        ctx.stage_outputs.get("resampling_fragment") == result.resampling_fragment,
    )


def test_compute_verdict_priority():
    _check(
        "verdict_inconclusive_first",
        compute_verdict(perm_fragment="PERM_PASS", n_unclassified=1)
        == "DIAG_INCONCLUSIVE",
    )
    _check(
        "verdict_filter_artifact",
        compute_verdict(perm_fragment="PERM_FAIL", n_unclassified=0)
        == "DIAG_FILTER_ARTIFACT",
    )
    _check(
        "verdict_resampling_unstable",
        compute_verdict(
            perm_fragment="PERM_PASS",
            n_unclassified=0,
            resampling_fragment="KFOLD_UNSTABLE",
        )
        == "DIAG_INCONCLUSIVE",
    )
    _check(
        "verdict_signal_valid",
        compute_verdict(
            perm_fragment="PERM_PASS",
            n_unclassified=0,
            resampling_fragment="KFOLD_STABLE",
        )
        == "DIAG_SIGNAL_VALID",
    )


def test_agent1_data_ingestion_fixture():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            agent = DataIngestionAgent(user_id="ingest_test")
            result = agent.run(
                {
                    "user_id": "ingest_test",
                    "run_id": "ing-1",
                    "options": {"fixture": True, "seed": 1},
                },
                "job-ingest-1",
                fixture_mode=True,
                cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=6),
            )
            _check("agent1_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("agent1_fixture", meta.get("fixture_mode") is True)
            _check("agent1_nine_steps", len(meta.get("subagents") or []) == 9)
            tele = meta.get("telemetry") or {}
            _check("agent1_blocks", int(tele.get("n_blocks", 0)) > 0)
            _check("agent1_receipts", int(tele.get("n_receipts", 0)) > 0)
            cp = Path(meta["checkpoint_path"])
            db = Path(meta["raw_db_path"])
            _check("agent1_checkpoint_exists", cp.is_file())
            _check("agent1_sqlite_exists", db.is_file())
            _check("agent1_live_path", "wave38/live" in str(cp))
            loaded = CheckpointWriter.load(cp)
            _check("agent1_checkpoint_job", loaded.get("job_id") == "job-ingest-1")
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_agent1_dedup_and_reference_guard():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            agent = DataIngestionAgent(user_id="dedup_test")
            first = agent.run(
                {"user_id": "dedup_test", "options": {"fixture": True}},
                "job-dedup",
                fixture_mode=True,
                cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=4),
            )
            _check("agent1_dedup_first", first["status"] == "completed")
            from agents_b2g.diagnostic.ingestion_rpc import FixtureRpcTransport

            ctx = StageContext(
                run_id="d",
                user_id="dedup_test",
                job_id="job-dedup2",
                data_root=str(DiagnosticConfig.wave38_live_root("dedup_test")),
                seed=0,
                prereg_version="WAVE38_LIVE_PREREG.md",
            )
            Path(ctx.data_root).mkdir(parents=True, exist_ok=True)
            transport = FixtureRpcTransport()
            receipts = []
            for chain in ("ethereum", "gnosis"):
                for b in range(
                    transport.eth_block_number(chain) - 1,
                    transport.eth_block_number(chain) + 1,
                ):
                    for r in transport.eth_get_block_receipts(chain, b):
                        r = dict(r)
                        r["_chain"] = chain
                        r["_block"] = b
                        receipts.append(r)
            ctx.stage_outputs["receipts"] = receipts
            storer = RawEventStorer()
            cfg = IngestionConfig(fixture_mode=True)
            r1 = storer.run(ctx, cfg=cfg)
            r2 = storer.run(ctx, cfg=cfg)
            _check("agent1_insert_ok", r1.status == "ok" and int(r1.metrics["inserted"]) > 0)
            _check(
                "agent1_dedup_skip",
                int(r2.metrics["dedup_skipped"]) > 0,
                str(r2.metrics),
            )
            guard = ReferenceArtifactGuard(ROOT)
            refs = [p for p in guard.registered_paths if p.is_file()]
            if refs:
                try:
                    guard.assert_write_allowed(refs[0])
                    _check("agent1_ref_blocked", False)
                except ReferenceWriteForbiddenError:
                    _check("agent1_ref_blocked", True)
            else:
                _check("agent1_ref_blocked_skip", True)
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_oracle_topic0_from_keccak():
    _check(
        "oracle_topic0_prefix",
        TOPIC_ANSWER_UPDATED.startswith("0x") and len(TOPIC_ANSWER_UPDATED) == 66,
    )
    _check("oracle_exclude_usdt_eth", is_excluded_feed("ethereum", "USDT/USD"))
    _check("oracle_exclude_gno_eth", is_excluded_feed("gnosis", "GNO/ETH"))
    _check("oracle_keep_gno_usd", not is_excluded_feed("gnosis", "GNO/USD"))


def test_agent2_oracle_on_agent1_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            ing = DataIngestionAgent(user_id="oracle_test")
            ing_result = ing.run(
                {"user_id": "oracle_test", "options": {"fixture": True}},
                "job-ing-oracle",
                fixture_mode=True,
                cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=4),
            )
            _check("agent2_pre_ingest", ing_result["status"] == "completed")
            db = ing_result["artifacts"][0]["metadata"]["raw_db_path"]

            oracle = OracleSignalAgent(user_id="oracle_test")
            result = oracle.run(
                {"user_id": "oracle_test", "options": {"fixture": True}},
                "job-oracle-1",
                raw_db_path=db,
                fixture_mode=True,
                cfg=OracleConfig(fixture_mode=True, n_bins=128, fixture_min_events=10),
            )
            _check("agent2_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("agent2_nine_steps", len(meta.get("subagents") or []) == 9)
            _check("agent2_events", int(meta.get("n_events") or 0) >= 10)
            _check("agent2_occupied", int(meta.get("n_occupied") or 0) > 0)
            excluded = meta.get("excluded_feeds") or []
            names = {f"{e['chain']}:{e['feed']}" for e in excluded}
            _check("agent2_excl_usdt", "ethereum:USDT/USD" in names)
            _check("agent2_excl_gno_eth", "gnosis:GNO/ETH" in names)
            occ_path = Path(meta["occupancy_path"])
            _check("agent2_occ_file", occ_path.is_file())
            _check("agent2_live_oracle_path", "wave38/live/oracle" in str(occ_path))
            # Consumer, not second RPC: must use Agent 1 db
            _check("agent2_uses_agent1_db", meta.get("raw_db_path") == db)
            # Phase history: ETH has 2 aggs, GNO/USD 4 phases tracked before exclusion filter on events
            phase_step = next(
                s for s in meta["subagents"] if s["step"] == "phases"
            )
            _check(
                "agent2_phase_aggs",
                int(phase_step["metrics"]["n_capture_aggregators"]) >= 4,
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_agent2_requires_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            oracle = OracleSignalAgent(user_id="oracle_fail")
            result = oracle.run(
                {"user_id": "oracle_fail", "options": {"fixture": True}},
                "job-oracle-no-db",
                raw_db_path=None,
                fixture_mode=True,
            )
            _check("agent2_no_db_failed", result["status"] == "failed")
            _check(
                "agent2_no_db_msg",
                "raw_db" in (result.get("error") or "").lower()
                or "sqlite" in (result.get("error") or "").lower()
                or "agent 1" in (result.get("error") or "").lower(),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_mev_exclusion_and_join():
    excl = load_exclusion_list()
    _check("mev_excl_n63", len(excl) == 63)
    _check("mev_excl_omnibridge", FIXTURE_EXCLUDED in excl)
    # Same UTC minute (t//60), not |Δt|≤60
    _check("mev_join_same_minute", minute_bucket(120) == minute_bucket(179))
    _check("mev_join_next_minute", minute_bucket(120) != minute_bucket(180))
    # |Δt|=50s can still span two minutes — must NOT join
    _check("mev_join_not_abs_delta", minute_bucket(100) != minute_bucket(150))
    _check(
        "mev_normalize_eip55",
        normalize_address("0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa")
        == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )


def test_agent3_mev_on_agent1_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            ing = DataIngestionAgent(user_id="mev_test")
            ing_result = ing.run(
                {"user_id": "mev_test", "options": {"fixture": True}},
                "job-ing-mev",
                fixture_mode=True,
                cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=4),
            )
            _check("agent3_pre_ingest", ing_result["status"] == "completed")
            db = ing_result["artifacts"][0]["metadata"]["raw_db_path"]

            mev = MEVCaptureAgent(user_id="mev_test")
            result = mev.run(
                {"user_id": "mev_test", "options": {"fixture": True}},
                "job-mev-1",
                raw_db_path=db,
                fixture_mode=True,
                cfg=MEVConfig(fixture_mode=True, n_bins=128, fixture_min_occupied=3),
            )
            _check("agent3_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("agent3_nine_steps", len(meta.get("subagents") or []) == 9)
            _check("agent3_uses_agent1_db", meta.get("raw_db_path") == db)
            _check("agent3_excl_n", int(meta.get("n_exclusion") or 0) == 63)
            _check(
                "agent3_excl_hit",
                FIXTURE_EXCLUDED in (meta.get("exclusion_hits") or []),
            )
            _check("agent3_occupied", int(meta.get("n_occupied") or 0) >= 3)
            _check(
                "agent3_cross_eoas",
                int(meta.get("n_cross_chain_eoas") or 0) >= 2,
            )
            _check("agent3_join", meta.get("join") == "t//60")
            occ_path = Path(meta["occupancy_path"])
            _check("agent3_occ_file", occ_path.is_file())
            _check("agent3_live_mev_path", "wave38/live/mev" in str(occ_path))
            body = json.loads(occ_path.read_text(encoding="utf-8"))
            _check("agent3_dense_schema", "occupancy" in body and body.get("candidate_id") == "mev_cluster")
            jsonl = Path(meta.get("occupancy_jsonl") or "")
            _check("agent3_sparse_file", jsonl.is_file())
            lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln]
            _check("agent3_sparse_jsonl", len(lines) == int(meta["n_occupied"]))
            # Failed TXs skipped
            ext = next(s for s in meta["subagents"] if s["step"] == "extractor")
            _check("agent3_failed_skipped", int(ext["metrics"].get("n_failed_skipped") or 0) >= 1)
            eoa_step = next(s for s in meta["subagents"] if s["step"] == "eoa")
            _check("agent3_eoa_two_stage", eoa_step["metrics"].get("two_stage") is True)
            _check(
                "agent3_contract_filtered",
                int(eoa_step["metrics"].get("n_contract") or 0) >= 1,
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_agent3_requires_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            mev = MEVCaptureAgent(user_id="mev_fail")
            result = mev.run(
                {"user_id": "mev_fail", "options": {"fixture": True}},
                "job-mev-no-db",
                raw_db_path=None,
                fixture_mode=True,
            )
            _check("agent3_no_db_failed", result["status"] == "failed")
            _check(
                "agent3_no_db_msg",
                "raw_db" in (result.get("error") or "").lower()
                or "sqlite" in (result.get("error") or "").lower()
                or "agent 1" in (result.get("error") or "").lower(),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_liq_topic0_and_resolver():
    _check(
        "liq_topic0_prefix",
        TOPIC_LIQUIDATION_CALL.startswith("0x") and len(TOPIC_LIQUIDATION_CALL) == 66,
    )
    _check("liq_coverage_gate_40", MIN_COVERAGE_LIQ == 0.40)
    plan = fixture_resolved_pools()
    _check("liq_resolver_released", plan.get("capture_release") == "RELEASED")
    pools = plan.get("pools") or []
    _check("liq_four_pools", len(pools) == 4)
    protocols = {p["protocol"] for p in pools}
    _check("liq_aave_spark", protocols == {"aave_v3", "spark"})
    topics, data = encode_liquidation_call_log(
        collateral="0x1111111111111111111111111111111111111111",
        debt="0x2222222222222222222222222222222222222222",
        user="0x3333333333333333333333333333333333333333",
        debt_to_cover=1000,
        liq_collateral=500,
        liquidator="0x4444444444444444444444444444444444444444",
        receive_atoken=True,
    )
    parsed = parse_liquidation_log({"topics": topics, "data": data})
    _check("liq_parse_user", parsed["user"].endswith("3333"))
    _check("liq_parse_receive", parsed["receive_atoken"] is True)


def test_agent4_liq_on_agent1_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            ing = DataIngestionAgent(user_id="liq_test")
            ing_result = ing.run(
                {"user_id": "liq_test", "options": {"fixture": True}},
                "job-ing-liq",
                fixture_mode=True,
                cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=4),
            )
            _check("agent4_pre_ingest", ing_result["status"] == "completed")
            db = ing_result["artifacts"][0]["metadata"]["raw_db_path"]

            liq = LiquidationCascadeAgent(user_id="liq_test")
            result = liq.run(
                {"user_id": "liq_test", "options": {"fixture": True}},
                "job-liq-1",
                raw_db_path=db,
                fixture_mode=True,
                cfg=LiquidationConfig(
                    fixture_mode=True, n_bins=128, fixture_min_events=8
                ),
            )
            _check("agent4_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("agent4_nine_steps", len(meta.get("subagents") or []) == 9)
            _check("agent4_uses_agent1_db", meta.get("raw_db_path") == db)
            _check("agent4_events", int(meta.get("n_events") or 0) >= 8)
            _check("agent4_occupied", int(meta.get("n_occupied") or 0) > 0)
            _check("agent4_or", meta.get("or_aggregation") is True)
            _check("agent4_coverage_gate", meta.get("min_coverage_days") == 0.40)
            reg = meta.get("pool_registry") or []
            _check("agent4_registry_4", len(reg) == 4)
            occ_path = Path(meta["occupancy_path"])
            _check("agent4_occ_file", occ_path.is_file())
            _check(
                "agent4_live_liq_path",
                "wave38/live/liquidations" in str(occ_path),
            )
            jsonl = Path(meta.get("occupancy_jsonl") or "")
            _check("agent4_sparse_jsonl", jsonl.is_file())
            lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln]
            _check("agent4_sparse_n", len(lines) == int(meta["n_occupied"]))
            # Topic0 from keccak in parser metrics
            parser = next(s for s in meta["subagents"] if s["step"] == "parser")
            _check(
                "agent4_topic0_keccak",
                parser["metrics"].get("topic0") == TOPIC_LIQUIDATION_CALL,
            )
            occ_step = next(s for s in meta["subagents"] if s["step"] == "occupancy")
            _check("agent4_or_metric", occ_step["metrics"].get("or_aggregation") is True)
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_agent4_requires_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            liq = LiquidationCascadeAgent(user_id="liq_fail")
            result = liq.run(
                {"user_id": "liq_fail", "options": {"fixture": True}},
                "job-liq-no-db",
                raw_db_path=None,
                fixture_mode=True,
            )
            _check("agent4_no_db_failed", result["status"] == "failed")
            _check(
                "agent4_no_db_msg",
                "raw_db" in (result.get("error") or "").lower()
                or "sqlite" in (result.get("error") or "").lower()
                or "agent 1" in (result.get("error") or "").lower(),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_intent_stable_topics_and_resolvers():
    _check("is_coverage_60", MIN_COVERAGE_INTENT_STABLE == 0.60)
    _check(
        "is_cow_7param",
        topic_for("cow_trade") == TOPIC_BY_EVENT["cow_trade"],
    )
    _check("is_cow_not_8param", TOPIC_BY_EVENT["cow_trade"] != WRONG_COW_TRADE_8)
    _check("is_psm_not_4param", TOPIC_BY_EVENT["psm_buy_gem"] != WRONG_PSM_BUY_4)
    _check(
        "is_across_two_topics",
        "across_filled_relay" in TOPIC_BY_EVENT
        and "across_filled_v3_relay" in TOPIC_BY_EVENT,
    )
    _check(
        "is_cctp_v2_fee",
        "cctp_v2_mint_and_withdraw" in TOPIC_BY_EVENT,
    )
    intent = fixture_intent_resolved()
    stable = fixture_stable_resolved()
    _check("is_intent_released", intent.get("capture_release") == "RELEASED")
    _check("is_stable_released", stable.get("capture_release") == "RELEASED")
    across = [c for c in intent["contracts"] if c["protocol"] == "across"]
    _check("is_across_eth_only", all(c["chain"] == "ethereum" for c in across))
    _check("is_across_present", len(across) == 1)
    protocols = {c["protocol"] for c in stable["contracts"]}
    _check(
        "is_stable_four",
        protocols == {"lite_psm", "classic_psm", "cctp_v1", "cctp_v2"},
    )


def test_agent5_intent_stable_on_agent1_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            ing = DataIngestionAgent(user_id="is_test")
            ing_result = ing.run(
                {"user_id": "is_test", "options": {"fixture": True}},
                "job-ing-is",
                fixture_mode=True,
                cfg=IngestionConfig(fixture_mode=True, fixture_scan_blocks=4),
            )
            _check("agent5_pre_ingest", ing_result["status"] == "completed")
            db = ing_result["artifacts"][0]["metadata"]["raw_db_path"]

            agent = IntentAndStablecoinAgent(user_id="is_test")
            result = agent.run(
                {"user_id": "is_test", "options": {"fixture": True}},
                "job-is-1",
                raw_db_path=db,
                fixture_mode=True,
                cfg=IntentStableConfig(
                    fixture_mode=True, n_bins=128, fixture_min_events=8
                ),
            )
            _check("agent5_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("agent5_nine_steps", len(meta.get("subagents") or []) == 9)
            _check("agent5_uses_agent1_db", meta.get("raw_db_path") == db)
            _check("agent5_events", int(meta.get("n_events") or 0) >= 8)
            _check("agent5_occupied", int(meta.get("n_occupied") or 0) > 0)
            _check("agent5_or", meta.get("or_aggregation") is True)
            _check("agent5_coverage_gate", meta.get("min_coverage_days") == 0.60)
            _check("agent5_registry_6plus", int(meta.get("n_registry") or 0) >= 6)
            scanners = {s["step"] for s in meta["subagents"]}
            _check(
                "agent5_six_scanners",
                {"across", "cow", "lite_psm", "classic_psm", "cctp_v1", "cctp_v2"}
                <= scanners,
            )
            tele = meta.get("telemetry") or {}
            by_proto = tele.get("by_protocol") or {}
            _check("agent5_multi_protocol", len(by_proto) >= 4)
            _check(
                "agent5_families",
                set(meta.get("families") or [])
                == {"intent_relayers", "stablecoin_mint_burn"},
            )
            occ_path = Path(meta["occupancy_path"])
            _check("agent5_occ_file", occ_path.is_file())
            _check(
                "agent5_live_path",
                "wave38/live/intent_stablecoin" in str(occ_path),
            )
            jsonl = Path(meta.get("occupancy_jsonl") or "")
            _check("agent5_sparse_jsonl", jsonl.is_file())
            lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln]
            _check("agent5_sparse_n", len(lines) == int(meta["n_occupied"]))
            # Migration-safe: Across registered both topics
            across_step = next(s for s in meta["subagents"] if s["step"] == "across")
            _check(
                "agent5_across_two_topics",
                int(across_step["metrics"].get("n_topics") or 0) >= 2,
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_agent5_requires_sqlite():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            agent = IntentAndStablecoinAgent(user_id="is_fail")
            result = agent.run(
                {"user_id": "is_fail", "options": {"fixture": True}},
                "job-is-no-db",
                raw_db_path=None,
                fixture_mode=True,
            )
            _check("agent5_no_db_failed", result["status"] == "failed")
            _check(
                "agent5_no_db_msg",
                "raw_db" in (result.get("error") or "").lower()
                or "sqlite" in (result.get("error") or "").lower()
                or "agent 1" in (result.get("error") or "").lower(),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_e2e_stages_1_to_6_fixture():
    """Capture 1→5 → OccupancyBundle → Agent 6 CTE; format, guard, data flow."""
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            # Fewer perm shifts for speed; seed fixed for determinism checks
            thresholds = Wave38Thresholds(n_perm_shifts=12, seed_default=20260822)
            pipe = Wave38CaptureToCTEPipeline(user_id="e2e16")
            result = pipe.run_stages_1_to_6(
                job_id="e2e-a",
                seed=20260822,
                n_bins=128,
                thresholds=thresholds,
            )
            _check("e2e16_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("e2e16_not_live", meta.get("live") is False)
            _check("e2e16_seed", meta.get("seed") == 20260822)
            _check("e2e16_raw_db", bool(meta.get("raw_db_path")))
            caps = meta.get("captures") or {}
            for key in (
                "chainlink",
                "mev_cluster",
                "liquidations",
                "intent_stablecoin",
            ):
                _check(f"e2e16_cap_{key}", caps.get(key, {}).get("status") == "completed")
                path = caps[key].get("occupancy_path")
                _check(f"e2e16_path_{key}", bool(path) and Path(path).is_file())
                body = load_occupancy_archive(path)
                _check(
                    f"e2e16_fmt_{key}",
                    OCCUPANCY_ARCHIVE_REQUIRED_KEYS <= set(body.keys()),
                )
            z_occ = meta.get("z_neu_occupied") or {}
            for cid in (
                "chainlink",
                "mev_cluster",
                "liquidations",
                "intent_relayers",
                "stablecoin_mint_burn",
            ):
                _check(f"e2e16_z_{cid}", int(z_occ.get(cid) or 0) > 0)
            cte = meta.get("cte") or {}
            _check("e2e16_cte_sum", isinstance(cte.get("sum_cte_ref"), dict))
            _check("e2e16_cte_stau", isinstance(cte.get("s_tau_by_candidate"), dict))
            _check("e2e16_perm", cte.get("perm_fragment") in ("PERM_PASS", "PERM_FAIL"))
            _check("e2e16_guard_ok", meta.get("reference_guard_unchanged") is True)
            _check("e2e16_write_blocked", meta.get("reference_write_blocked") is True)
            # Live paths only
            for key, cap in caps.items():
                _check(
                    f"e2e16_live_{key}",
                    "wave38/live" in str(cap.get("occupancy_path")),
                )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_e2e_stages_1_to_6_determinism():
    """Two identical fixture E2E runs → byte-identical CTE payloads."""
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            thresholds = Wave38Thresholds(n_perm_shifts=12, seed_default=20260822)
            pipe = Wave38CaptureToCTEPipeline(user_id="e2e16d")

            def _run(job: str) -> dict:
                r = pipe.run_stages_1_to_6(
                    job_id=job,
                    seed=20260822,
                    n_bins=128,
                    thresholds=thresholds,
                )
                assert r["status"] == "completed", r.get("error")
                return r["artifacts"][0]["metadata"]["cte"]

            a = _run("e2e-d1")
            b = _run("e2e-d2")
            _check(
                "e2e16_det_sum",
                json.dumps(a["sum_cte_ref"], sort_keys=True)
                == json.dumps(b["sum_cte_ref"], sort_keys=True),
            )
            _check(
                "e2e16_det_stau",
                json.dumps(a["s_tau_by_candidate"], sort_keys=True)
                == json.dumps(b["s_tau_by_candidate"], sort_keys=True),
            )
            _check("e2e16_det_perm", a["perm_fragment"] == b["perm_fragment"])
            _check(
                "e2e16_det_loo",
                json.dumps(a["rel_loo_by_candidate"], sort_keys=True)
                == json.dumps(b["rel_loo_by_candidate"], sort_keys=True),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_e2e_forbids_live_flag():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            pipe = Wave38CaptureToCTEPipeline(user_id="e2e_live_block")
            result = pipe.run_stages_1_to_6(
                job_id="e2e-live",
                run_input={
                    "run_id": "e2e-live",
                    "user_id": "e2e_live_block",
                    "options": {"fixture": True, "live": True},
                },
            )
            _check("e2e16_live_blocked", result["status"] == "failed")
            _check(
                "e2e16_live_msg",
                "live" in (result.get("error") or "").lower(),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_e2e_stages_1_to_9_fixture():
    """Full Capture→Analyse→Envelope; five validation points."""
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            thresholds = Wave38Thresholds(
                n_perm_shifts=12,
                seed_default=20260822,
                rho_spearman_min=0.90,
                n_unstable_folds_max=1,
                k_folds=9,
            )
            pipe = Wave38FullPipeline(user_id="e2e19")
            result = pipe.run_stages_1_to_9(
                job_id="e2e-19a",
                seed=20260822,
                n_bins=128,
                thresholds=thresholds,
            )
            _check("e2e19_status", result["status"] == "completed", result.get("error"))
            meta = result["artifacts"][0]["metadata"]
            _check("e2e19_pipeline", meta.get("pipeline") == "1→9")
            _check("e2e19_not_live", meta.get("live") is False)
            _check("e2e19_nine_stages", len(meta.get("stages") or []) == 9)

            # 1) Data flow: captures + CTE + resampling + envelope
            caps = meta.get("captures") or {}
            for key in (
                "chainlink",
                "mev_cluster",
                "liquidations",
                "intent_stablecoin",
            ):
                _check(f"e2e19_cap_{key}", caps.get(key, {}).get("status") == "completed")
            z_occ = meta.get("z_neu_occupied") or {}
            _check("e2e19_z_all", all(int(z_occ.get(c) or 0) > 0 for c in (
                "chainlink",
                "mev_cluster",
                "liquidations",
                "intent_relayers",
                "stablecoin_mint_burn",
            )))

            # 2) Lag-Spearman on real CTE path
            _check(
                "e2e19_resampling",
                meta.get("resampling_fragment")
                in ("KFOLD_STABLE", "KFOLD_UNSTABLE"),
            )
            ap = meta.get("analysis_pipeline") or {}
            _check("e2e19_rho_min_set", ap.get("rho_min") is not None)
            _check(
                "e2e19_rho_threshold",
                float((ap.get("thresholds") or {}).get("RHO_SPEARMAN_MIN", 0)) >= 0.90,
            )
            _check(
                "e2e19_unstable_max",
                int((ap.get("thresholds") or {}).get("N_UNSTABLE_FOLDS_MAX", -1)) == 1,
            )
            _check("e2e19_stage7", "7_resampling" in (ap.get("stages") or []))

            # 3) Verdict mapping under Live Pre-Reg thresholds
            _check(
                "e2e19_verdict",
                meta.get("verdict")
                in {
                    "DIAG_SIGNAL_VALID",
                    "DIAG_FILTER_ARTIFACT",
                    "DIAG_INCONCLUSIVE",
                },
            )
            _check(
                "e2e19_prelim",
                ap.get("preliminary_verdict") == meta.get("verdict"),
            )
            _check("e2e19_perm_frag", ap.get("perm_fragment") in ("PERM_PASS", "PERM_FAIL"))

            # 4) Envelope contract under full load
            env = meta.get("envelope") or {}
            _check(
                "e2e19_env_keys",
                ENVELOPE_REQUIRED_KEYS <= set(env.keys()),
            )
            _check(
                "e2e19_gate",
                env.get("gate_action") in ("RELEASED", "BLOCKED"),
            )
            if env.get("gate_action") == "BLOCKED":
                _check("e2e19_blocked_cause", env.get("cause") is not None)
            if env.get("gate_action") == "RELEASED":
                _check("e2e19_released_stau", bool(env.get("s_tau")))
            _check("e2e19_fdr", isinstance(env.get("fdr_status"), dict))
            _check("e2e19_collapse", isinstance(env.get("collapse_info"), dict))
            _check("e2e19_released_list", isinstance(env.get("released_signals"), list))
            _check("e2e19_blocked_list", isinstance(env.get("blocked_signals"), list))
            _check("e2e19_env_seed", env.get("seed") == 20260822)

            # 5) Reference guard full chain
            _check("e2e19_guard_ok", meta.get("reference_guard_unchanged") is True)
            _check("e2e19_write_blocked", meta.get("reference_write_blocked") is True)
            for key, cap in caps.items():
                _check(
                    f"e2e19_live_{key}",
                    "wave38/live" in str(cap.get("occupancy_path")),
                )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_e2e_stages_1_to_9_determinism():
    """Two identical 1→9 runs → identical verdict + resampling + CTE sum."""
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            thresholds = Wave38Thresholds(
                n_perm_shifts=12,
                seed_default=20260822,
                rho_spearman_min=0.90,
                n_unstable_folds_max=1,
                k_folds=9,
            )
            pipe = Wave38FullPipeline(user_id="e2e19d")

            def _run(job: str) -> dict:
                r = pipe.run_stages_1_to_9(
                    job_id=job,
                    seed=20260822,
                    n_bins=128,
                    thresholds=thresholds,
                )
                assert r["status"] == "completed", r.get("error")
                return r["artifacts"][0]["metadata"]

            a = _run("e2e-19d1")
            b = _run("e2e-19d2")
            _check("e2e19_det_verdict", a["verdict"] == b["verdict"])
            _check(
                "e2e19_det_resampling",
                a["resampling_fragment"] == b["resampling_fragment"],
            )
            _check(
                "e2e19_det_cte",
                json.dumps(a["analysis_pipeline"].get("sum_cte_ref"), sort_keys=True)
                == json.dumps(b["analysis_pipeline"].get("sum_cte_ref"), sort_keys=True),
            )
            _check(
                "e2e19_det_stau",
                json.dumps(a["envelope"].get("s_tau"), sort_keys=True)
                == json.dumps(b["envelope"].get("s_tau"), sort_keys=True),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_e2e_1_to_9_forbids_live():
    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            pipe = Wave38FullPipeline(user_id="e2e19_live")
            result = pipe.run_stages_1_to_9(
                job_id="e2e-19-live",
                run_input={
                    "run_id": "e2e-19-live",
                    "user_id": "e2e19_live",
                    "options": {"fixture": True, "live": True},
                },
            )
            _check("e2e19_live_blocked", result["status"] == "failed")
            _check(
                "e2e19_live_msg",
                "live" in (result.get("error") or "").lower(),
            )
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_live_window_freeze_not_bridge():
    """3d-ix: freeze [T0−90d,T0] before capture; must not equal Bridge endpoints."""
    from agents_b2g.diagnostic.live_window import (
        BRIDGE_WINDOW_END_UTC,
        BRIDGE_WINDOW_START_UTC,
        compute_window,
        freeze_live_window,
        is_bridge_window_identical,
    )

    w = compute_window(job_id="test-freeze", user_id="wave38_test_freeze")
    _check("freeze_n_bins_90d", w.n_bins == 90 * 24 * 60)
    _check(
        "freeze_not_bridge",
        not is_bridge_window_identical(
            BRIDGE_WINDOW_START_UTC, BRIDGE_WINDOW_END_UTC
        )
        or w.window_start_utc != BRIDGE_WINDOW_START_UTC.isoformat(),
    )
    # Explicit: frozen endpoints differ from sealed Bridge pair as identical sole source
    _check(
        "freeze_end_not_bridge_end_pair",
        not (
            w.window_start_utc.startswith("2026-05-20T00:00:00")
            and w.window_end_utc.startswith("2026-08-17T23:59:59")
        ),
    )
    with tempfile.TemporaryDirectory() as tmp:
        prev = DiagnosticConfig.DATA_ROOT
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            frozen = freeze_live_window(user_id="u1", job_id="j1")
            path = Path(tmp) / "u1" / "wave38" / "live" / "live_window.json"
            _check("freeze_written", path.is_file())
            again = freeze_live_window(user_id="u1", job_id="j1")
            _check("freeze_idempotent", again.window_start_ts == frozen.window_start_ts)
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_gobd_report_and_eventbus():
    """3d-ix §7: GoBD WORM + EventBus publish for a synthetic envelope."""
    from agents_b2g.diagnostic.subagents.diagnostic_report_composer import (
        DiagnosticReportComposer,
    )
    from agents_b2g.diagnostic.wave38_live_pipeline import _publish_eventbus

    with tempfile.TemporaryDirectory() as tmp:
        prev = DiagnosticConfig.DATA_ROOT
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        try:
            env = {
                "verdict": "DIAG_INCONCLUSIVE",
                "gate_action": "BLOCKED",
                "cause": "INCONCLUSIVE",
                "s_tau": {},
                "released_signals": [],
                "blocked_signals": [],
                "run_id": "gobd-test",
                "seed": 20260822,
                "prereg_version": "WAVE38_LIVE_PREREG.md",
            }
            composer = DiagnosticReportComposer(user_id="u_gobd")
            rep = composer.compose(
                "gobd-test",
                envelope=env,
                live_window={"n_bins": 100},
                agent_response={"status": "completed", "job_id": "gobd-test"},
            )
            _check("gobd_status", rep["status"] == "completed")
            meta = rep["artifacts"][0]["metadata"]
            _check("gobd_worm", meta.get("worm") is True)
            _check("gobd_hash", bool(meta.get("entry_hash")))
            pdf = Path(meta["pdf_path"])
            _check("gobd_pdf", pdf.is_file() and pdf.read_bytes()[:5] == b"%PDF-")
            bus = _publish_eventbus(
                user_id="u_gobd",
                envelope=env,
                agent_response={"status": "completed", "job_id": "gobd-test"},
            )
            _check("bus_subject", bus["subject"] == "wave38.diagnostic.signal")
            audit = Path(bus["audit_log"])
            _check("bus_audit", audit.is_file() and audit.stat().st_size > 0)
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def test_live_capture_checkpoint_helpers():
    import os

    from agents_b2g.diagnostic.live_ingestion import (
        _checkpoint_path,
        _etherscan_strategy_status,
        _load_capture_checkpoint,
        _target_fingerprint,
        _write_capture_checkpoint,
        run_live_ingestion,
    )
    from agents_b2g.diagnostic.live_window import FrozenLiveWindow
    from agents_b2g.diagnostic.reference_guard import ReferenceArtifactGuard

    prev = DiagnosticConfig.DATA_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        DiagnosticConfig.DATA_ROOT = Path(tmp)
        live = DiagnosticConfig.wave38_live_root("ck_test")
        live.mkdir(parents=True, exist_ok=True)
        try:
            tgt = {
                "family": "bridge",
                "chain": "ethereum",
                "address": "0xabc",
                "topics": ["0x1"],
            }
            fp = _target_fingerprint(tgt)
            _check("live_ck_fp_stable", fp == _target_fingerprint(tgt))

            ck_path = _checkpoint_path(live, "live-90d")
            guard = ReferenceArtifactGuard(DiagnosticConfig.PROJECT_ROOT)
            payload = {
                "job_id": "live-90d",
                "status": "in_progress",
                "next_target_index": 15,
                "mev_phase": "pending",
                "n_events": 24866,
            }
            _write_capture_checkpoint(ck_path, guard=guard, payload=payload)
            loaded = _load_capture_checkpoint(live, "live-90d")
            _check("live_ck_load", loaded is not None)
            _check("live_ck_status", loaded.get("status") == "in_progress")
            _check("live_ck_next", loaded.get("next_target_index") == 15)

            prev_key = os.environ.pop("ETHERSCAN_API_KEY", None)
            try:
                st = _etherscan_strategy_status()
                _check("live_eth_no_key", st["ethereum_strategy"] == "rpc_fallback")
                os.environ["ETHERSCAN_API_KEY"] = "test-key"
                st2 = _etherscan_strategy_status()
                _check("live_eth_key", st2["ethereum_strategy"] == "etherscan_first")
                os.environ.pop("ETHERSCAN_API_KEY", None)

                window = FrozenLiveWindow(
                    t0_utc="2023-11-14T22:13:20Z",
                    window_start_utc="2023-11-14T22:13:20Z",
                    window_end_utc="2023-11-15T22:13:20Z",
                    window_start_ts=1_700_000_000,
                    window_end_ts=1_700_086_400,
                    n_bins=1440,
                    rolling_days=1,
                    seed=42,
                    prereg_version="test",
                    frozen_at_utc="2026-08-23T00:00:00Z",
                    job_id="require-eth-x",
                    user_id="ck_test",
                )
                try:
                    run_live_ingestion(
                        window,
                        user_id="ck_test",
                        job_id="require-eth-x",
                        require_etherscan=True,
                        capture_tail_days=1,
                    )
                    _check("live_require_eth_raises", False)
                except RuntimeError as exc:
                    _check("live_require_eth_raises", "ETHERSCAN_API_KEY" in str(exc))
            finally:
                if prev_key is not None:
                    os.environ["ETHERSCAN_API_KEY"] = prev_key
                else:
                    os.environ.pop("ETHERSCAN_API_KEY", None)
        finally:
            DiagnosticConfig.DATA_ROOT = prev


def run_all() -> int:
    global PASS, FAIL
    tests = [
        test_diagnostic_verdict_enum,
        test_block_cause_enum,
        test_envelope_frozen,
        test_validate_blocked_requires_cause,
        test_envelope_to_dict_roundtrip_keys,
        test_gatekeeper_released_skeleton,
        test_gatekeeper_blocked_with_cause,
        test_gatekeeper_rejects_blocked_without_cause,
        test_live_blocked_without_prereg,
        test_live_prereg_final_bindend_content,
        test_live_allowed_when_prereg_bindend,
        test_live_blocked_when_prereg_not_bindend,
        test_reference_guard_blocks_write,
        test_live_path_separate_from_reference,
        test_wave38_live_root_helper,
        test_live_prereg_thresholds_load,
        test_cte_math_classify_role,
        test_agent6_mock_bundle,
        test_agent8_informativity_then_verdict,
        test_e2e_stages_6_8_9,
        test_spearman_perfect_correlation,
        test_spearman_constant_is_zero,
        test_fold_ranges_cover_bins,
        test_agent7_lag_spearman,
        test_compute_verdict_priority,
        test_agent1_data_ingestion_fixture,
        test_agent1_dedup_and_reference_guard,
        test_oracle_topic0_from_keccak,
        test_agent2_oracle_on_agent1_sqlite,
        test_agent2_requires_sqlite,
        test_mev_exclusion_and_join,
        test_agent3_mev_on_agent1_sqlite,
        test_agent3_requires_sqlite,
        test_liq_topic0_and_resolver,
        test_agent4_liq_on_agent1_sqlite,
        test_agent4_requires_sqlite,
        test_intent_stable_topics_and_resolvers,
        test_agent5_intent_stable_on_agent1_sqlite,
        test_agent5_requires_sqlite,
        test_e2e_stages_1_to_6_fixture,
        test_e2e_stages_1_to_6_determinism,
        test_e2e_forbids_live_flag,
        test_e2e_stages_1_to_9_fixture,
        test_e2e_stages_1_to_9_determinism,
        test_e2e_1_to_9_forbids_live,
        test_live_window_freeze_not_bridge,
        test_live_capture_checkpoint_helpers,
        test_gobd_report_and_eventbus,
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:
            FAIL += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = PASS + FAIL
    print(f"\n{PASS}/{total} passed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_all())
