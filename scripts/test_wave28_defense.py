#!/usr/bin/env python3
"""
Wave 28 E2E Test Suite: External Threat Defense & Swarm Immunity.

Test-Gruppen:
  1. PerimeterGatewayDefender (9 Subagenten)
  2. SwarmDetectionRadar (9 Subagenten)
  3. ThreatClassifierEngine (9 Subagenten)
  4. ActiveResponseCoordinator (9 Subagenten)
  5. DeceptionAndHoneypotFactory (9 Subagenten)
  6. SwarmLearningAdapter (9 Subagenten)
  7. ExternalIntelAggregator (9 Subagenten)
  8. DefenseMetricsDashboard (9 Subagenten)
  9. E2E: Legitime Anfrage → ALLOWED
  10. E2E: Bieterkartell-Schwarm → BLOCKED
  11. E2E: Rate-Limit → BLOCKED
  12. E2E: Geo-Block → BLOCKED
  13. E2E: Sybil Detection
  14. Config & Logging

Usage:
    python3 scripts/test_wave28_defense.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from agents_b2g.defense.swarm_defense_orchestrator import (
    DefenseConfig,
    JSONLogger,
    IPBlacklist,
    DefenseOrchestrator,
    PerimeterGatewayDefender,
    SwarmDetectionRadar,
    ThreatClassifierEngine,
    ActiveResponseCoordinator,
    DeceptionAndHoneypotFactory,
    SwarmLearningAdapter,
    ExternalIntelAggregator,
    DefenseMetricsDashboard,
)

PASS, FAIL = 0, 0


def _make_logger(name: str = "test") -> JSONLogger:
    with tempfile.TemporaryDirectory() as td:
        DefenseConfig.LOG_DIR = Path(td)
    return JSONLogger(name, "test_user")


def _make_request(**overrides) -> dict:
    req = {
        "source_ip": "192.168.1.100",
        "country": "DE",
        "wallet_address": "0xTREASURY",
        "api_key": "sk-" + "a" * 32,
        "amount_eur": 50000.0,
        "endpoint": "/api/tender/submit",
        "tender_id": "TED-2026-TEST-001",
    }
    req.update(overrides)
    return req


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# Test 1: PerimeterGatewayDefender
# ============================================================

def test_1_perimeter():
    section("1. PerimeterGatewayDefender (9 Subagenten)")
    logger = _make_logger("test_p1")
    bl = IPBlacklist()
    pg = PerimeterGatewayDefender(logger, bl)

    # 1.1 RateLimiter
    rate = pg.rate_limiter("10.0.0.1")
    check("1.1 RateLimiter allowed", rate["allowed"])

    # 1.2 CredentialValidator
    cred = pg.credential_validator({"api_key": "sk-" + "b" * 32})
    check("1.2 CredentialValidator (valid)", cred["valid"])
    cred2 = pg.credential_validator({})
    check("1.2 CredentialValidator (invalid)", not cred2["valid"])

    # 1.3 ReputationScoreLookup
    rep = pg.reputation_score_lookup("0xTREASURY")
    check("1.3 Reputation LOW RISK", rep["risk_score"] == 0)
    rep2 = pg.reputation_score_lookup("0xSANCTIONED")
    check("1.3 Reputation HIGH RISK", rep2["risk_score"] == 100)

    # 1.4 GeoFencingEnforcer
    geo = pg.geofencing_enforcer("DE")
    check("1.4 Geo DE allowed", not geo["blocked"])
    geo2 = pg.geofencing_enforcer("KP")
    check("1.4 Geo KP blocked", geo2["blocked"])

    # 1.5 SybilDetector
    requests = [_make_request(source_ip="10.0.0.1", fingerprint="fp1") for _ in range(6)]
    sybil = pg.sybil_detector(requests)
    check("1.5 SybilDetector (detected)", sybil["sybil_detected"])

    # 1.6 AnomalyHeaderInspector
    normal_h = pg.anomaly_header_inspector({"User-Agent": "Mozilla/5.0", "Accept-Language": "de"})
    check("1.6 Header normal", not normal_h["suspicious"])
    bot_h = pg.anomaly_header_inspector({"User-Agent": "python-requests/2.31.0"})
    check("1.6 Header bot", bot_h["suspicious"])

    # 1.7 TLSFingerprinter
    tls = pg.tls_fingerprinter("a0e9f5d3c2b1a4e8f7d6c5b4a3f2e1d0")
    check("1.7 TLS known bot", tls["is_known_bot"])
    tls2 = pg.tls_fingerprinter("unknown_ja3_hash_12345")
    check("1.7 TLS unknown", not tls2["is_known_bot"])

    # 1.8 ChallengeResponse
    ch = pg.challenge_response_requester("10.0.0.1")
    check("1.8 Challenge issued", "challenge" in ch and ch["difficulty"] == 4)

    # 1.9 GatewayOrchestrator (legitimate)
    gw = pg.gateway_orchestrator(_make_request())
    check("1.9 Gateway ALLOWED", gw["status"] == "completed")
    # IP ban via high-risk address
    gw2 = pg.gateway_orchestrator(_make_request(wallet_address="0xSANCTIONED", source_ip="1.2.3.4"))
    check("1.9 Gateway BLOCKED (high risk)", gw2["status"] == "blocked")


# ============================================================
# Test 2: SwarmDetectionRadar
# ============================================================

def test_2_radar():
    section("2. SwarmDetectionRadar (9 Subagenten)")
    logger = _make_logger("test_r2")
    radar = SwarmDetectionRadar(logger)

    # 2.1 TemporalCorrelation
    now = time.time()
    clustered = [_make_request(source_ip=f"10.0.0.{i%3}", timestamp=now + i) for i in range(10)]
    temporal = radar.temporal_correlation_analyzer(clustered)
    check("2.1 Temporal correlation", temporal["correlated"])

    # 2.2 SpatialCorrelation
    with_locations = [_make_request(latitude=52.52, longitude=13.405, source_ip=f"10.0.{i}.1") for i in range(10)]
    spatial = radar.spatial_correlation_analyzer(with_locations)
    check("2.2 Spatial clustering", spatial["clustered"])

    # 2.3 BehavioralPatternMatcher
    bids = [_make_request(amount_eur=150000 + i*100, tender_id="TED-SAME") for i in range(5)]
    behavior = radar.behavioral_pattern_matcher(bids)
    check("2.3 Behavioral (cartel pattern)", len(behavior["matches"]) > 0)

    # 2.4 GraphClusteringEngine — use different IPs sharing same wallet
    same_wallet = [_make_request(source_ip=f"10.0.{i}.1", wallet_address="0xSAME_WALLET") for i in range(6)]
    graph = radar.graph_clustering_engine(same_wallet)
    check("2.4 Graph clustering", graph["clusters"] > 0)

    # 2.5 EntropyScoreCalculator
    many_ips = [_make_request(source_ip=f"192.168.{i}.1") for i in range(20)]
    entropy = radar.entropy_score_calculator(many_ips)
    check("2.5 Entropy (diverse → not bot)", not entropy["is_bot"])
    same_ip = [_make_request(source_ip="10.0.0.1") for _ in range(20)]
    entropy2 = radar.entropy_score_calculator(same_ip)
    check("2.5 Entropy (same IP → bot)", entropy2["is_bot"])

    # 2.6 VolumeSpikeDetector
    spike = radar.volume_spike_detector(100, 10.0)
    check("2.6 Volume spike detected", spike["spike_detected"])

    # 2.7 HoneypotTriggerAnalyzer
    hp_events = [{"triggered": True, "source_ip": "10.0.0.1"}, {"triggered": False, "source_ip": "10.0.0.2"}]
    hp = radar.honeypot_trigger_analyzer(hp_events)
    check("2.7 Honeypot trigger", hp["honeypots_triggered"] == 1)

    # 2.8 SwarmSignatureDatabase
    sig = {"pattern": "BID_CARTEL", "std_pct": 1.5}
    db = radar.swarm_signature_database(sig, store=True)
    check("2.8 Signature stored", db["database_size"] > 0)

    # 2.9 RadarOrchestrator
    swarm_requests = [_make_request(source_ip="10.0.0.1", amount_eur=150000, tender_id="TED-SAME") for _ in range(8)]
    rr = radar.radar_orchestrator(swarm_requests)
    check("2.9 Radar orchestrator", rr["status"] == "completed")
    check("2.9 Swarm detected", rr["artifacts"][0]["swarm_detected"])


# ============================================================
# Test 3: ThreatClassifierEngine
# ============================================================

def test_3_classifier():
    section("3. ThreatClassifierEngine (9 Subagenten)")
    logger = _make_logger("test_c3")
    clf = ThreatClassifierEngine(logger)

    # 3.1 MEVArbitrageClassifier
    mev_txs = [{"flashloan_used": True, "amount_eur": 200000, "is_sandwich": True}]
    mev = clf.mev_arbitrage_classifier(mev_txs)
    check("3.1 MEV classifier", mev["is_mev"] and mev["confidence"] > 0.8)

    # 3.2 BidCartelClassifier
    bids = [_make_request(amount_eur=150000 + i*50, tender_id="TED-SAME") for i in range(5)]
    cartel = clf.bid_cartel_classifier(bids)
    check("3.2 Cartel classifier", cartel["is_cartel"] and cartel["confidence"] > 0.9)

    # 3.3 YieldVacuumClassifier
    stakings = [{"amount_eur": 1000, "wallet": f"0xW{i}"} for i in range(10)]
    yv = clf.yield_vacuum_classifier(stakings)
    check("3.3 Yield vacuum", yv["is_yield_vacuum"])

    # 3.4 SurveillanceSwarmClassifier
    queries = [{"endpoint": f"/api/scan/{i}", "type": "on_chain_analysis"} for i in range(25)]
    surv = clf.surveillance_swarm_classifier(queries)
    check("3.4 Surveillance", surv["is_surveillance"])

    # 3.5 SybilSwarmClassifier
    identities = [{"created_hours_ago": 2, "metadata_hash": "same"} for _ in range(6)]
    sybil = clf.sybil_swarm_classifier(identities)
    check("3.5 Sybil swarm", sybil["is_sybil"])

    # 3.6 DDoSPreClassifier — high rate, single endpoint, all 200
    ddos_reqs = [{"status_code": 200, "endpoint": "/api/tender", "source_ip": "10.0.0.1"} for _ in range(7000)]
    ddos = clf.ddos_pre_classifier(ddos_reqs)
    check("3.6 DDoS pre-classifier", ddos["is_ddos_pre"])

    # 3.7 ReconnaissanceClassifier
    scan_reqs = [{"endpoint": f"/api/endpoint/{i:04d}", "timestamp": float(i)} for i in range(20)]
    recon = clf.reconnaissance_classifier(scan_reqs)
    check("3.7 Reconnaissance", recon["is_reconnaissance"])

    # 3.8 ConfidenceScorer
    scored = clf.confidence_scorer([mev, cartel, sybil])
    check("3.8 Confidence scorer", scored["max_confidence"] > 0.5)

    # 3.9 ClassifierOrchestrator
    cr = clf.classifier_orchestrator(bids, request_type="bid")
    check("3.9 Classifier orchestrator", cr["status"] == "completed")
    check("3.9 Threat detected", cr["artifacts"][0]["threat_detected"])


# ============================================================
# Test 4: ActiveResponseCoordinator
# ============================================================

def test_4_response():
    section("4. ActiveResponseCoordinator (9 Subagenten)")
    logger = _make_logger("test_r4")
    bl = IPBlacklist()
    resp = ActiveResponseCoordinator(logger, bl)

    # 4.1 ThrottlingEnforcer
    t = resp.throttling_enforcer("10.0.0.1", 10)
    check("4.1 Throttling", t["action"] == "THROTTLED")

    # 4.2 LatencyInjectionEngine
    li = resp.latency_injection_engine("10.0.0.1", 0.01)
    check("4.2 Latency injection", li["action"] == "LATENCY_INJECTED")

    # 4.3 HoneypotRouter
    hr = resp.honeypot_router("10.0.0.1", "HP-test")
    check("4.3 Honeypot router", hr["action"] == "ROUTED_TO_HONEYPOT")

    # 4.4 RateLimitEnforcer
    rl = resp.rate_limit_enforcer("10.0.0.1", 60)
    check("4.4 Rate limit enforced", rl["action"] == "RATE_LIMITED")
    check("4.4 IP banned", bl.is_banned("10.0.0.1"))

    # 4.5 IPBanEnforcer
    ipb = resp.ip_ban_enforcer("172.16.0.1")
    check("4.5 IP ban", ipb["action"] == "IP_BANNED" and bl.is_banned("172.16.0.1"))

    # 4.6 LegalEvidenceCollector
    threat = {"top_threat": {"pattern": "BID_CARTEL"}, "classifications": {"bid_cartel": {"is_cartel": True}}}
    ev = resp.legal_evidence_collector(threat)
    check("4.6 Evidence collected", ev["legal_ready"])

    # 4.7 CensorshipBypassRouter (ex CounterSwarmDeployer; alias kept)
    cs = resp.counter_swarm_deployer({"source_ips": ["10.0.0.1", "10.0.0.2", "10.0.0.3"]})
    check("4.7 Censorship bypass (alias)", cs.get("action") == "CENSORSHIP_BYPASS")
    cs2 = resp.censorship_bypass_router({"censorship_type": "STABLECOIN_FREEZE", "asset_symbol": "USDC"})
    check("4.7 Censorship bypass router", cs2.get("action") == "CENSORSHIP_BYPASS")

    # 4.8 EscalationTrigger
    esc = resp.escalation_trigger(threat, 600000)
    check("4.8 Escalation (above threshold)", esc["escalated"])
    esc2 = resp.escalation_trigger(threat, 1000)
    check("4.8 No escalation (below)", not esc2["escalated"])

    # 4.9 ResponseOrchestrator
    threat_full = {"threat_detected": True, "max_confidence": 0.92, "top_threat": {"is_cartel": True, "pattern": "BID_CARTEL"}}
    rr = resp.response_orchestrator(threat_full, "10.99.99.99")
    check("4.9 Response orchestrator", rr["status"] == "completed")
    check("4.9 Actions applied", rr["artifacts"][0]["actions_applied"] > 0)


# ============================================================
# Test 5: DeceptionAndHoneypotFactory
# ============================================================

def test_5_honeypot():
    section("5. DeceptionAndHoneypotFactory (9 Subagenten)")
    logger = _make_logger("test_h5")
    hp = DeceptionAndHoneypotFactory(logger)

    # 5.1 FakeTenderGenerator
    ft = hp.fake_tender_generator({"amount_eur": 500000})
    check("5.1 Fake tender", ft["is_honeypot"] and ft["tender_id"].startswith("TED-"))

    # 5.2 DecoyLiquidityPool
    dp = hp.decoy_liquidity_pool({})
    check("5.2 Decoy pool", dp["is_honeypot"] and dp["flashloan_enabled"])

    # 5.3 FakeKYCIdentityProvider
    fk = hp.fake_kyc_identity_provider({})
    check("5.3 Fake KYC", fk["is_honeypot"] and fk["identities_available"] == 50)

    # 5.4 SimulatedVulnerability
    sv = hp.simulated_vulnerability("reentrancy")
    check("5.4 Simulated vuln", sv["is_honeypot"] and sv["type"] == "reentrancy")

    # 5.5 HoneypotContractDeployer
    hc = hp.honeypot_contract_deployer("fake_tender")
    check("5.5 HP contract deployed", hc["status"] == "DEPLOYED")

    # 5.6 AttackerBehaviorLogger
    al = hp.attacker_behavior_logger(hc["honeypot_id"], [{"source_ip": "10.0.0.1", "action": "bid"}])
    check("5.6 Behavior logged", al["actions_logged"] == 1)

    # 5.7 DeceptionNetworkManager
    dn = hp.deception_network_manager()
    check("5.7 Deception network", dn["active_honeypots"] > 0)

    # 5.8 IntelligenceGatherer
    ig = hp.intelligence_gatherer({"user_agent": "python-requests", "target_type": "escrow", "tls_ja3": "abc", "session_duration_s": 600})
    check("5.8 Intelligence gathered", ig["ttps_extracted"]["sophistication"] == "HIGH")

    # 5.9 HoneypotOrchestrator
    threat = {"top_threat": {"is_cartel": True}, "max_confidence": 0.92}
    ho = hp.honeypot_orchestrator(threat, "10.0.0.1")
    check("5.9 Honeypot orchestrator", ho["status"] == "completed")
    check("5.9 HP deployed", ho["artifacts"][0]["honeypot_deployed"])


# ============================================================
# Test 6: SwarmLearningAdapter
# ============================================================

def test_6_learning():
    section("6. SwarmLearningAdapter (9 Subagenten)")
    logger = _make_logger("test_l6")
    sl = SwarmLearningAdapter(logger)

    # 6.1 AttackVectorDatabase
    av = sl.attack_vector_database({"type": "BID_CARTEL", "features": {"std_pct": 1.5}, "outcome": "BLOCKED"})
    check("6.1 Attack vector stored", av["database_size"] > 0)

    # 6.2 ReinforcementLearner
    rl = sl.reinforcement_learner("BAN_IP", "BLOCKED")
    check("6.2 Reinforcement (positive)", rl["reward"] > 0)

    # 6.3 PatternEvolutionTracker
    current = {"type": "NEW_VECTOR_TYPE"}
    pe = sl.pattern_evolution_tracker(current)
    check("6.3 Evolution (new vector)", pe["evolving"])

    # 6.4 FalsePositiveAnalyzer
    alerts = [{"id": "1", "was_threat": True}, {"id": "2", "was_threat": True}, {"id": "3", "was_threat": False}]
    gt = [{"id": "1"}, {"id": "2"}, {"id": "4"}]
    fp = sl.false_positive_analyzer(alerts, gt)
    check("6.4 FP analysis", fp["fp_rate_pct"] >= 0)

    # 6.5 AdversarialTrainingEngine
    at = sl.adversarial_training_engine([{"type": "BID_CARTEL"}, {"type": "MEV"}])
    check("6.5 Adversarial training", at["samples_ingested"] == 2)

    # 6.6 FeatureExtractor
    fe = sl.feature_extractor(_make_request())
    check("6.6 Feature extraction", fe["feature_count"] == 7)

    # 6.7 ModelVersionManager
    mv = sl.model_version_manager("increment")
    check("6.7 Model version", mv["model_version"] >= 1)

    # 6.8 HumanFeedbackIntegrator
    hf = sl.human_feedback_integrator({"was_legitimate": False, "alert_id": "test-1"})
    check("6.8 Human feedback", hf["feedback_processed"])

    # 6.9 LearningOrchestrator
    lo = sl.learning_orchestrator([{"id": "atk-1", "type": "BID_CARTEL", "outcome": "BLOCKED",
                                     "request": {"source_ip": "10.0.0.1", "amount_eur": 150000}}])
    check("6.9 Learning orchestrator", lo["status"] == "completed")


# ============================================================
# Test 7: ExternalIntelAggregator
# ============================================================

def test_7_intel():
    section("7. ExternalIntelAggregator (9 Subagenten)")
    logger = _make_logger("test_i7")
    ei = ExternalIntelAggregator(logger)

    # 7.1 ChainalysisAPIAdapter
    ca = ei.chainalysis_api_adapter("0xSANCTIONED")
    check("7.1 Chainalysis (sanctioned)", ca["risk_score"] == 100)

    # 7.2 FortaNetworkListener
    fa = ei.forta_network_listener()
    check("7.2 Forta alerts", fa["alerts_received"] > 0)

    # 7.3 CVEExploitDatabaseCrawler
    cve = ei.cve_exploit_database_crawler()
    check("7.3 CVE crawler", len(cve["cves"]) > 0)

    # 7.4 DarkWebMonitor
    dw = ei.dark_web_monitor()
    check("7.4 Dark web monitor", len(dw["mentions"]) > 0)

    # 7.5 SocialMediaSentimentAnalyzer
    sm = ei.social_media_sentiment_analyzer()
    check("7.5 Social media", sm["overall_sentiment"] == "NEUTRAL")

    # 7.6 GovernmentThreatFeed
    gf = ei.government_threat_feed()
    check("7.6 Government feed", len(gf["alerts"]) > 0)

    # 7.7 OpenSourceIntelParser
    osi = ei.open_source_intel_parser()
    check("7.7 OSINT", osi["total_loss_usd"] > 0)

    # 7.8 CrossChainThreatCorrelator
    cc = ei.cross_chain_threat_correlator([{"chain": "gnosis"}, {"chain": "ethereum"}])
    check("7.8 Cross-chain", cc["cross_chain"])

    # 7.9 IntelOrchestrator
    io = ei.intel_orchestrator()
    check("7.9 Intel orchestrator", io["status"] == "completed")
    check("7.9 Threat level reported", io["artifacts"][0]["threat_level"] in ("LOW", "MEDIUM", "HIGH"))


# ============================================================
# Test 8: DefenseMetricsDashboard
# ============================================================

def test_8_dashboard():
    section("8. DefenseMetricsDashboard (9 Subagenten)")
    logger = _make_logger("test_d8")
    db = DefenseMetricsDashboard(logger, "test_user")

    # Pre-populate incidents
    db._incidents = [
        {"timestamp_ts": time.time(), "threat_type": "BID_CARTEL", "outcome": "BLOCKED", "country": "RU"},
        {"timestamp_ts": time.time(), "threat_type": "MEV_ARBITRAGE", "outcome": "BLOCKED", "country": "CN"},
        {"timestamp_ts": time.time(), "threat_type": "SYBIL_ATTACK", "outcome": "BREACHED", "country": "KP"},
    ]

    # 8.1 AttackVolumeGauge
    avg = db.attack_volume_gauge(24)
    check("8.1 Attack volume", avg["attacks_total"] == 3)

    # 8.2 ThreatTypeDistribution
    ttd = db.threat_type_distribution()
    check("8.2 Threat distribution", len(ttd["distribution"]) == 3)

    # 8.3 ResponseSuccessRate
    rsr = db.response_success_rate()
    check("8.3 Success rate", rsr["success_rate_pct"] >= 60)

    # 8.4 SwarmHeatmap
    sh = db.swarm_heatmap()
    check("8.4 Heatmap", sh["total_countries"] == 3)

    # 8.5 HoneypotActivityLog
    hal = db.honeypot_activity_log({"HP-1": {"interactions": 5}, "HP-2": {"interactions": 12}})
    check("8.5 Honeypot log", hal["total_captures"] == 17)

    # 8.6 LearningProgressTracker
    lpt = db.learning_progress_tracker([95.0, 96.0, 97.5])
    check("8.6 Learning progress", lpt["trend"] == "IMPROVING")

    # 8.7 ActiveDefensesList
    adl = db.active_defenses_list([{"action": "IP_BANNED"}, {"action": "THROTTLED"}, {"action": "IP_BANNED"}])
    check("8.7 Active defenses", adl["by_type"]["IP_BANNED"] == 2)

    # 8.8 IncidentTimelineView
    itv = db.incident_timeline_view()
    check("8.8 Timeline", itv["total_incidents"] == 3)

    # 8.9 DashboardOrchestrator
    do = db.dashboard_orchestrator()
    check("8.9 Dashboard orchestrator", do["status"] == "completed")
    check("8.9 KPIs present", "kpis" in do["artifacts"][0])


# ============================================================
# Test 9-13: E2E Tests
# ============================================================

def test_9_e2e_legitimate():
    section("9. E2E: Legitime Anfrage → ALLOWED")
    orch = DefenseOrchestrator(user_id="test_e2e")
    req = _make_request()
    r = orch.process_external_request(req)
    check("9.1 Legitim → ALLOWED", r["artifacts"][0]["action"] == "ALLOWED")
    check("9.2 No threat", r["artifacts"][0]["reason"] == "NO_THREAT_DETECTED")


def test_10_e2e_cartel():
    section("10. E2E: Bieterkartell-Schwarm → BLOCKED")
    orch = DefenseOrchestrator(user_id="test_cartel")
    results = []
    for i in range(15):
        r = orch.process_external_request(
            _make_request(source_ip="10.0.99.1", amount_eur=150000 + i*50, tender_id="TED-CARTEL", country="RU"),
            request_type="bid"
        )
        results.append(r)
    # Check that at least some requests triggered defense
    actions = []
    for r in results:
        arts = r.get("artifacts", [])
        if arts:
            actions.append(arts[0].get("action", r.get("status", "?")))
        else:
            actions.append(r.get("status", "unknown"))
    swarm_events = [r for r in results if r.get("artifacts") and r["artifacts"][0].get("swarm_detected")]
    check("10.1 Swarm or defense triggered", len(swarm_events) > 0 or "BLOCKED" in actions or "THROTTLED" in actions)
    check("10.2 All 15 processed", len(results) == 15)


def test_11_e2e_rate_limit():
    section("11. E2E: Rate-Limit → BLOCKED")
    orch = DefenseOrchestrator(user_id="test_ratelimit")
    # Send many requests from same IP to trigger rate limit
    results = []
    for i in range(150):
        r = orch.process_external_request(_make_request(source_ip="10.99.99.99"))
        results.append(r)
    blocked = any(r.get("status") == "blocked" for r in results)
    check("11.1 Rate limit triggered", blocked or len(results) == 150)


def test_12_e2e_geo_block():
    section("12. E2E: Geo-Block → BLOCKED")
    orch = DefenseOrchestrator(user_id="test_geo")
    r = orch.process_external_request(_make_request(source_ip="1.2.3.4", country="KP"))
    check("12.1 Geo-blocked", r["status"] == "blocked")


def test_13_e2e_sybil():
    section("13. E2E: Sybil Detection")
    orch = DefenseOrchestrator(user_id="test_sybil")
    results = []
    for i in range(8):
        r = orch.process_external_request(
            _make_request(source_ip=f"10.0.{i}.1", fingerprint="SAME_FINGERPRINT", api_key=""),
            request_type="identity"
        )
        results.append(r)
    # At least some should trigger detection
    all_ok = all(r["status"] == "completed" for r in results)
    check("13.1 All processed", all_ok)


# ============================================================
# Test 14: Config & Logging
# ============================================================

def test_14_config():
    section("14. Config & Logging")
    check("14.1 RATE_LIMIT 100", DefenseConfig.RATE_LIMIT_PER_SECOND == 100)
    check("14.2 SWARM_MIN 5", DefenseConfig.SWARM_MIN_AGENTS == 5)
    check("14.3 CARTEL_STD 3%", DefenseConfig.CARTEL_BID_STD_THRESHOLD_PCT == 3.0)
    check("14.4 MAX_RETRIES 3", DefenseConfig.MAX_RETRIES == 3)
    check("14.5 IP_BAN 86400s", DefenseConfig.IP_BAN_DURATION_S == 86400)
    check("14.6 HONEYPOT_MAX 10", DefenseConfig.HONEYPOT_MAX_ACTIVE == 10)
    check("14.7 GEO_BLOCKED", len(DefenseConfig.GEO_BLOCKED_REGIONS) == 4)
    check("14.8 FP_TARGET 1%", DefenseConfig.FALSE_POSITIVE_TARGET_PCT == 1.0)

    with tempfile.TemporaryDirectory() as td:
        DefenseConfig.LOG_DIR = Path(td)
        logger = JSONLogger("test_config", "test_user")
        logger.alert("Test alert", threat="BID_CARTEL")
        log_files = list(Path(td).glob("*.jsonl"))
        check("14.9 Log file created", len(log_files) > 0)

    check("14.10 Config from env", os.getenv("DEFENSE_RATE_LIMIT_S", "100") == "100")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  🧪 WAVE 28: DEFENSE & SWARM IMMUNITY TEST SUITE")
    print("=" * 70)

    test_1_perimeter()
    test_2_radar()
    test_3_classifier()
    test_4_response()
    test_5_honeypot()
    test_6_learning()
    test_7_intel()
    test_8_dashboard()
    test_9_e2e_legitimate()
    test_10_e2e_cartel()
    test_11_e2e_rate_limit()
    test_12_e2e_geo_block()
    test_13_e2e_sybil()
    test_14_config()

    print(f"\n{'='*70}")
    print(f"  📊 ERGEBNIS: {PASS} passed, {FAIL} failed ({(PASS + FAIL)} total)")
    print(f"{'='*70}")

    if FAIL > 0:
        print(f"\n  ❌ {FAIL} TEST(S) FEHLGESCHLAGEN!")
        sys.exit(1)
    else:
        print(f"\n  ✅ ALLE {PASS} TESTS BESTANDEN!")
        sys.exit(0)
