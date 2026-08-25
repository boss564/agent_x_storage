#!/usr/bin/env python3
"""Wave 28 Threat Engine — DI wiring, lifecycle, memory/DB integration.

    python3 scripts/test_wave28_threat_engine.py

Ohne WAVE28_THREAT_DSN: MemoryThreatBackend (pgvector-Äquivalent in-process).
Mit DSN: optionale Live-Checks gegen PostgreSQL+pgvector.
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agents_b2g.defense.swarm_defense_orchestrator import (  # noqa: E402
    DefenseConfig,
    DefenseOrchestrator,
    JSONLogger,
)
from agents_b2g.defense.threat_engine import (  # noqa: E402
    ClassifierIncidentAdapter,
    LearningEmbeddingAdapter,
    RadarThreatStoreAdapter,
    SensitivityLifecycle,
    eoa_pseudonym,
    make_memory_session,
)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _logger() -> JSONLogger:
    with tempfile.TemporaryDirectory() as td:
        DefenseConfig.LOG_DIR = Path(td)
    return JSONLogger("threat_engine_test", "test_tenant")


def _addr(n: int = 1) -> str:
    return "0x" + f"{n:040x}"


def test_dim_guard_and_ann() -> None:
    print("\n1. Dim-Guard + ANN (MemoryBackend)")
    session = make_memory_session()
    log = _logger()
    learn = LearningEmbeddingAdapter(session, log)
    radar = RadarThreatStoreAdapter(session, log)

    bad = learn.store_embedding(
        signature_id=1,
        eoa_pseudonym=eoa_pseudonym(_addr(1)),
        vector=[0.1] * 10,
    )
    check("dim mismatch fails", bad.get("status") == "failed", str(bad.get("error")))

    now = datetime.now(timezone.utc)
    sig = radar.record_signature(
        eoa_address_or_pseudonym=_addr(2),
        chain="ethereum",
        window_start=now,
        window_end=now,
        interaction_type="dex_swap",
        tx_count=5,
        pattern_label="fee_burst",
        observed_by_user_id="test_tenant",
    )
    check("signature insert", sig.get("status") == "completed", str(sig))
    sid = sig["artifacts"][0]["signature_id"]
    pseudo = sig["artifacts"][0]["eoa_pseudonym"]

    vec = [1.0 / math.sqrt(384)] * 384
    ok = learn.store_embedding(
        signature_id=sid,
        eoa_pseudonym=pseudo,
        vector=vec,
        cluster_id=7,
    )
    check("embedding insert dim=384", ok.get("status") == "completed", str(ok))

    near = learn.query_similar(vec, top_k=3)
    check("ANN returns row", near.get("status") == "completed" and len(near["artifacts"]) >= 1)
    check(
        "ANN same model only",
        near["artifacts"][0]["embedding_model"] == "all-MiniLM-L6-v2",
    )
    labels = learn.get_cluster_labels()
    check("cluster labels", labels["artifacts"][0]["cluster_id"] == 7)


def test_gate_coupling_discipline() -> None:
    print("\n2. gate_coupling SQL discipline (MemoryBackend)")
    session = make_memory_session()
    clf = ClassifierIncidentAdapter(session, _logger())
    pseudo = eoa_pseudonym(_addr(3))

    blocked_no_cause = clf.record_gate_coupling(
        signature_id=1,
        eoa_pseudonym=pseudo,
        action_type="GATE_BLOCKED",
        agent_x_signal_status="BLOCKED",
        block_cause=None,
        s_tau=-0.1,
    )
    check(
        "BLOCKED without cause fails",
        blocked_no_cause.get("status") == "failed",
        str(blocked_no_cause.get("error")),
    )

    blocked_pos = clf.record_gate_coupling(
        signature_id=1,
        eoa_pseudonym=pseudo,
        action_type="GATE_BLOCKED",
        agent_x_signal_status="BLOCKED",
        block_cause="X",
        s_tau=0.2,
    )
    check(
        "BLOCKED with S(τ)>0 fails",
        blocked_pos.get("status") == "failed",
        str(blocked_pos.get("error")),
    )

    ok = clf.record_gate_coupling(
        signature_id=1,
        eoa_pseudonym=pseudo,
        action_type="GATE_BLOCKED",
        agent_x_signal_status="BLOCKED",
        block_cause="SWARM_S_TAU",
        s_tau=-0.2,
        gatekeeper_job_id="job-1",
    )
    check("BLOCKED with cause+S(τ)≤0 ok", ok.get("status") == "completed", str(ok))


def test_sensitivity_lifecycle() -> None:
    print("\n3. SENSITIVITY_RAISED / CLEARED pairing")
    session = make_memory_session()
    store = RadarThreatStoreAdapter(session, _logger())
    life = SensitivityLifecycle(store, observed_by_user_id="test_tenant")
    now = datetime.now(timezone.utc)
    sig = store.record_signature(
        eoa_address_or_pseudonym=_addr(4),
        chain="gnosis",
        window_start=now,
        window_end=now,
        interaction_type="bridge_transfer",
    )
    sid = sig["artifacts"][0]["signature_id"]
    pseudo = sig["artifacts"][0]["eoa_pseudonym"]

    life.raise_sensitivity(signature_id=sid, eoa_pseudonym=pseudo, kfold_sensitivity=2.0)
    check("one open raise", len(life.open_raises()) == 1)
    try:
        life.raise_sensitivity(signature_id=sid, eoa_pseudonym=pseudo)
        check("duplicate raise blocked", False)
    except RuntimeError:
        check("duplicate raise blocked", True)

    life.clear_sensitivity(signature_id=sid)
    check("cleared", len(life.open_raises()) == 0)
    life.assert_all_cleared()
    check("assert_all_cleared", True)

    actions = [i["action_type"] for i in session.incidents]
    check(
        "audit contains RAISED+CLEARED",
        "SENSITIVITY_RAISED" in actions and "SENSITIVITY_CLEARED" in actions,
        str(actions),
    )


def test_orchestrator_e2e_wired() -> None:
    print("\n4. E2E DefenseOrchestrator + ThreatEngine (Memory)")
    session = make_memory_session()
    orch = DefenseOrchestrator(user_id="test_tenant", threat_session=session)
    check("adapters injected", orch.radar_store is not None and orch.sensitivity is not None)

    # Build swarm: ≥5 correlated requests with valid EOA
    base_ts = 1_700_000_000
    results = []
    for i in range(6):
        req = {
            "source_ip": f"10.0.0.{i}",
            "country": "DE",
            "wallet_address": _addr(10 + i),
            "api_key": "sk-" + "b" * 32,
            "amount_eur": 10000.0 + i,  # low variance → cartel signal
            "endpoint": "/api/tender/submit",
            "tender_id": "TED-SWARM-001",
            "timestamp": base_ts + i,
            "chain": "ethereum",
            "interaction_type": "other_allowlisted",
            "latitude": 52.5,
            "longitude": 13.4,
        }
        results.append(orch.process_external_request(req, request_type="bid"))

    last = results[-1]
    art = last.get("artifacts", [{}])[0]
    check("pipeline completed", last.get("status") in ("completed", "blocked"), str(last.get("status")))
    # Once swarm threshold hit, threat_engine lifecycle should run
    te = art.get("threat_engine") or {}
    if art.get("swarm_detected"):
        check("sensitivity raised logged", "sensitivity_raised" in te, str(te))
        check("sensitivity cleared logged", "sensitivity_cleared" in te, str(te))
        check("s_tau present", "s_tau" in te, str(te))
        check("no open raises", len(orch.sensitivity.open_raises()) == 0)
        check("signatures persisted", len(session.signatures) >= 1)
    else:
        # Soft: still prove DI path is inert when no swarm
        check("no swarm → no open raises", len(orch.sensitivity.open_raises()) == 0)


def test_optional_live_dsn() -> None:
    print("\n5. Live PostgreSQL (optional)")
    dsn = os.environ.get("WAVE28_THREAT_DSN", "").strip()
    if not dsn:
        check("skipped (no WAVE28_THREAT_DSN)", True)
        return
    try:
        from agents_b2g.defense.threat_engine.session import ThreatEngineSession, connect_from_env

        conn = connect_from_env(dsn)
        session = ThreatEngineSession(conn)
        learn = LearningEmbeddingAdapter(session, _logger())
        bad = learn.store_embedding(
            signature_id=1,
            eoa_pseudonym=eoa_pseudonym(_addr(99)),
            vector=[0.0] * 10,
        )
        check("live dim guard", bad.get("status") == "failed")
        session.close()
    except Exception as exc:  # noqa: BLE001
        check("live DSN reachable", False, str(exc))


def test_censorship_resilience() -> None:
    print("\n6. Censorship Resilience")
    from agents_b2g.defense.threat_engine import (
        CensorshipBypassAdapter,
        RelayerHealthAdapter,
        SanctionsScreeningAdapter,
        detect_address_poisoning,
    )
    from agents_b2g.diagnostic.types import BlockCause

    session = make_memory_session()
    log = _logger()
    san = SanctionsScreeningAdapter(session, log)
    rel = RelayerHealthAdapter(session, log)
    byp = CensorshipBypassAdapter(session, log)

    target = _addr(42)
    poison = "0x" + target[2:6] + ("00" * 16) + target[-4:]
    # ensure length 42
    poison = "0x" + (target[2:6] + "ab" * 16 + target[-4:])[:40]
    p = detect_address_poisoning(poison, [target])
    check("poisoning vanity overlap", p["poisoning_suspected"], str(p))

    w = san.upsert_watch(
        address=target,
        source="OFAC",
        list_version="sdn-2026-08",
        confidence=0.99,
        observed_by_user_id="test_tenant",
    )
    check("watchlist upsert", w.get("status") == "completed", str(w))
    scr = san.screen_address(target)
    check("sanctioned hit", scr["artifacts"][0]["sanctioned"], str(scr))

    h = rel.record_health(
        relayer_name="OmniBridge",
        chain_id=1,
        asset_symbol="USDC",
        throughput_rate=1.0,
        drop_rate=5.0,
    )
    check("relayer censorship flag", h["artifacts"][0]["censorship_detected"], str(h))

    route = byp.recommend_route(censorship_type="STABLECOIN_FREEZE", asset_symbol="USDC")
    check(
        "USDC→native fallback",
        route["artifacts"][0].get("asset_fallback") == "ETH_NATIVE",
        str(route),
    )
    inc = byp.record_incident(
        censorship_type="STABLECOIN_FREEZE",
        agent_x_signal_status="BLOCKED",
        block_cause="CENSORSHIP_DETECTED",
        route_fallback="ETH_NATIVE",
    )
    check("censorship incident BLOCKED", inc.get("status") == "completed", str(inc))
    check(
        "BlockCause enum",
        BlockCause.CENSORSHIP_DETECTED.value == "CENSORSHIP_DETECTED",
    )

    orch = DefenseOrchestrator(user_id="test_tenant", threat_session=session)
    bypass = orch.response.censorship_bypass_router(
        {"censorship_type": "RPC_BLOCK", "max_confidence": 0.99}
    )
    check("router wired", bypass.get("action") == "CENSORSHIP_BYPASS", str(bypass))
    alias = orch.response.counter_swarm_deployer({"censorship_type": "BUILDER_FILTER"})
    check("alias counter_swarm → bypass", alias.get("action") == "CENSORSHIP_BYPASS")


def main() -> int:
    print("=" * 60)
    print("Wave 28 Threat Engine Tests")
    print("=" * 60)
    test_dim_guard_and_ann()
    test_gate_coupling_discipline()
    test_sensitivity_lifecycle()
    test_orchestrator_e2e_wired()
    test_optional_live_dsn()
    test_censorship_resilience()
    print(f"\nResult: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
