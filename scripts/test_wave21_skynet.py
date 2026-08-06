#!/usr/bin/env python3
"""
Wave 21 E2E Test: Skynet Dynamic Security Score & Real-Time Monitoring Engine.
Testet alle 9 Root-Agenten mit ihren Subagenten (6 Pillars × 8 + 3 Root).

Usage:
    python scripts/test_wave21_skynet.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents_b2g.security.skynet_orchestrator import (
    SkynetOrchestrator,
    SkynetConfig,
    SkynetRating,
    # P1
    AuditRemediationTracker,
    PatchIntegrityVerifier,
    VulnerabilityWeightCalculator,
    BugBountySignalConsumer,
    CompilerWarningAuditor,
    StaticScanScoreFeeder,
    FormalProofScoreFeeder,
    ZeroDayExploitMonitor,
    CodeSecurityAggregator,
    # P2
    CommitVelocityTracker,
    ActiveDeveloperCounter,
    SpecCompletenessChecker,
    DocumentationFreshness,
    BranchSecurityGuard,
    DependencyVulnWatcher,
    ContributorReputationScorer,
    ReviewRigidityAnalyzer,
    FundamentalHealthAggregator,
    # P3
    MultiSigThresholdWatcher,
    TimelockDelayMonitor,
    AdminKeyHSMAuditor,
    RPCUptimeTracker,
    CloudComplianceValidator,
    EmergencyPauseChecker,
    KeyRotationAuditor,
    HSMVerifier,
    OperationalSecurityAggregator,
    # P4
    LiquidityDepthChecker,
    WhaleConcentrationCalc,
    VolatilityIndexMonitor,
    SlippageImpactAnalyzer,
    VolumeValidator,
    WashTradingDetector,
    VestingCliffWatcher,
    ImpermanentLossCalc,
    MarketStabilityAggregator,
    # P5
    SentimentNLPAnalyzer,
    BotDensityDetector,
    MentionVelocityTracker,
    DiscordEngagementScorer,
    TelegramHealthAuditor,
    PhishingTokenWatcher,
    GovernanceSentimentTracker,
    InfluencerManipulationDetector,
    CommunityTrustAggregator,
    # P6
    TokenGiniCalculator,
    VoterDistributionAnalyzer,
    InsiderHoldingAuditor,
    DelegationConcentrationMonitor,
    QuorumAttainmentChecker,
    ExecutionTimelockWatcher,
    FlashLoanVotingGuard,
    VetoRightAuditor,
    GovernanceStrengthAggregator,
    # A7-A9
    SkynetScoreAggregator,
    SkynetRiskAlertEngine,
    SkynetDashboardComposer,
)


PASSED = 0
FAILED = 0


def check(desc: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✅ {desc}")
    else:
        FAILED += 1
        print(f"  ❌ {desc}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ================================================================
# P1: Code Security (9 tests)
# ================================================================


def test_p1_code_security() -> None:
    section("P1: Code Security (9 Subagents)")

    r = AuditRemediationTracker().track([{"fixed": True}, {"fixed": False}])
    check("1.1 Remediation: 1/2 fixed", r["remediation_pct"] == 50.0)

    r = PatchIntegrityVerifier().verify([{"regression": False}, {"regression": False}])
    check("1.2 Patch: 0 regressions", r["regressions"] == 0)

    r = VulnerabilityWeightCalculator().calculate([{"severity": "CRITICAL"}, {"severity": "HIGH"}])
    check("1.3 VulnWeight: penalty=15", r["weight_penalty"] == 15)

    r = BugBountySignalConsumer().consume([])
    check("1.4 BugBounty: clean", r["critical"] == 0)

    r = CompilerWarningAuditor().audit("pragma solidity ^0.8;")
    check("1.5 Compiler: 0 warnings", r["warnings"] == 0)

    r = StaticScanScoreFeeder().feed({"score": 95, "issues": 0})
    check("1.6 Static: score=95", r["score"] == 95)

    r = FormalProofScoreFeeder().feed({"proven": 5, "total": 5})
    check("1.7 Proof: 100% coverage", r["coverage_pct"] == 100.0)

    r = ZeroDayExploitMonitor().monitor("0xdeadbeef")
    check("1.8 ZeroDay: clean", not r["detected"])

    r = CodeSecurityAggregator().aggregate({"a": {"score": 90}, "b": {"score": 80}})
    check("1.9 Aggregator: avg=85", r["pillar_score"] == 85.0)


# ================================================================
# P2: Fundamental Health (9 tests)
# ================================================================


def test_p2_fundamental_health() -> None:
    section("P2: Fundamental Health (9 Subagents)")

    r = CommitVelocityTracker().track([{"date": "2026-08-01"}] * 10)
    check("2.1 Commits: velocity=20", r["velocity_score"] == 20)

    r = ActiveDeveloperCounter().count([{"active": True}, {"active": False}, {"active": True}])
    check("2.2 Devs: 2 active", r["active"] == 2)

    r = SpecCompletenessChecker().check(["f1", "f2", "f3"], ["f1", "f2", "f4"])
    check("2.3 Spec: 2/3=66.7%", r["coverage_pct"] == 66.7)

    r = DocumentationFreshness().audit("2026-08-01T00:00:00Z")
    check("2.4 Docs: recent", r["age_days"] < 30)

    r = BranchSecurityGuard().guard({"required_reviews": True, "status_checks": True})
    check("2.5 Branch: protected", r["protected"])

    r = DependencyVulnWatcher().watch([{"cve": []}, {"cve": ["CVE-2024-1234"]}])
    check("2.6 Deps: 1 vulnerable", r["vulnerable"] == 1)

    r = ContributorReputationScorer().score([{"reputation": 80}, {"reputation": 90}])
    check("2.7 Reputation: avg=85", r["avg_reputation"] == 85.0)

    r = ReviewRigidityAnalyzer().analyze([{"approved": True}, {"approved": False}, {"approved": True}])
    check("2.8 Reviews: 2/3=66.7%", r["approval_pct"] == 66.7)

    r = FundamentalHealthAggregator().aggregate({"a": {"score": 100}, "b": {"score": 60}})
    check("2.9 Aggregator: avg=80", r["pillar_score"] == 80.0)


# ================================================================
# P3: Operational Security (9 tests)
# ================================================================


def test_p3_operational_security() -> None:
    section("P3: Operational Security (9 Subagents)")

    r = MultiSigThresholdWatcher().watch({"required": 3, "total": 5})
    check("3.1 MultiSig: 3/5 secure", r["threshold_ok"])

    r = TimelockDelayMonitor().monitor({"delay_seconds": 172800})
    check("3.2 Timelock: 48h secure", r["secure"])

    r = AdminKeyHSMAuditor().audit({"hsm_used": True})
    check("3.3 HSM Key: secure", r["hsm_used"])

    r = RPCUptimeTracker().track({"uptime_pct": 99.95})
    check("3.4 RPC: 99.95%", r["uptime_pct"] == 99.95)

    r = CloudComplianceValidator().validate(["SOC2 Type2", "ISO 27001"])
    check("3.5 Cloud: SOC2+ISO", r["soc2"] and r["iso27001"])

    r = EmergencyPauseChecker().check(["a1", "a2", "a3"])
    check("3.6 Pause: 3 unique", r["unique_pausers"] == 3)

    r = KeyRotationAuditor().audit([{"date": "2026-07-01T00:00:00Z"}])
    check("3.7 Rotation: recent", r["days_since"] < 90)

    r = HSMVerifier().verify({"verified": True})
    check("3.8 HSM: verified", r["verified"])

    r = OperationalSecurityAggregator().aggregate({"a": {"score": 95}})
    check("3.9 Aggregator: score=95", r["pillar_score"] == 95.0)


# ================================================================
# P4: Market Stability (9 tests)
# ================================================================


def test_p4_market_stability() -> None:
    section("P4: Market Stability (9 Subagents)")

    r = LiquidityDepthChecker().check({"liquidity_usd": 10_000_000})
    check("4.1 Liquidity: 10M USD", r["depth_usd"] == 10_000_000)

    r = WhaleConcentrationCalc().calculate([{"balance": 100}, {"balance": 50}, {"balance": 50}])
    check("4.2 Whale: top10=100%", r["top10_pct"] == 100.0)

    r = VolatilityIndexMonitor().monitor([100, 105, 100])
    check("4.3 Vol: 5% max", r["vol_pct"] == 5.0)

    r = SlippageImpactAnalyzer().analyze({"liquidity_usd": 10_000_000}, sell=500_000)
    check("4.4 Slippage: 5%", r["slippage_pct"] == 5.0)

    r = VolumeValidator().validate({"real_volume": 800, "total_volume": 1000})
    check("4.5 Volume: 20% wash", r["wash_pct"] == 20.0)

    r = WashTradingDetector().detect([])
    check("4.6 Wash: clean", r["circular"] == 0)

    r = VestingCliffWatcher().watch([{"date": "2027-01-01T00:00:00Z"}])
    check("4.7 Vesting: 0 upcoming (<30d)", r["upcoming_cliffs"] == 0)

    r = ImpermanentLossCalc().calculate({"il_pct": 2.5})
    check("4.8 IL: 2.5%", r["il_pct"] == 2.5)

    r = MarketStabilityAggregator().aggregate({"a": {"score": 80}, "b": {"score": 90}})
    check("4.9 Aggregator: avg=85", r["pillar_score"] == 85.0)


# ================================================================
# P5: Community Trust (9 tests)
# ================================================================


def test_p5_community_trust() -> None:
    section("P5: Community Trust (9 Subagents)")

    r = SentimentNLPAnalyzer().analyze([{"sentiment": "positive"}] * 8 + [{"sentiment": "negative"}] * 2)
    check("5.1 Sentiment: ratio=4.0", r["pos_neg_ratio"] == 4.0)

    r = BotDensityDetector().detect([{"is_bot": False}] * 20)
    check("5.2 Bots: 0%", r["bot_pct"] == 0.0)

    r = MentionVelocityTracker().track([{"organic": True}, {"organic": False}])
    check("5.3 Mentions: 1 organic, 1 paid", r["organic"] == 1 and r["paid"] == 1)

    r = DiscordEngagementScorer().score([{"user_id": "u1"}, {"user_id": "u2"}, {"user_id": "u1"}])
    check("5.4 Discord: 2 users", r["active_users"] == 2)

    r = TelegramHealthAuditor().audit({"mod_response_min": 15})
    check("5.5 Telegram: 15min response", r["mod_response_min"] == 15)

    r = PhishingTokenWatcher().watch([])
    check("5.6 Phishing: clean", r["fake_tokens"] == 0)

    r = GovernanceSentimentTracker().track([{"sentiment": "supportive"}, {"sentiment": "supportive"}])
    check("5.7 GovSentiment: 2 supportive", r["supportive"] == 2)

    r = InfluencerManipulationDetector().detect([])
    check("5.8 Influencer: clean", r["manipulative"] == 0)

    r = CommunityTrustAggregator().aggregate({"a": {"score": 75}})
    check("5.9 Aggregator: score=75", r["pillar_score"] == 75.0)


# ================================================================
# P6: Governance Strength (9 tests)
# ================================================================


def test_p6_governance_strength() -> None:
    section("P6: Governance Strength (9 Subagents)")

    r = TokenGiniCalculator().calculate([10, 10, 10, 10, 10])
    check("6.1 Gini: equal=0.0", r["gini"] == 0.0)

    r = VoterDistributionAnalyzer().analyze([{"voter": "v1"}, {"voter": "v2"}, {"voter": "v1"}])
    check("6.2 Voters: 2 unique", r["unique_voters"] == 2)

    r = InsiderHoldingAuditor().audit([{"balance": 100, "is_insider": True},
                                        {"balance": 900, "is_insider": False}])
    check("6.3 Insider: 10%", r["insider_pct"] == 10.0)

    r = DelegationConcentrationMonitor().monitor([{"delegate": "d1", "power": 100},
                                                    {"delegate": "d2", "power": 50}])
    check("6.4 Delegation: top=66.7%", r["top_delegate_pct"] == 66.7)

    r = QuorumAttainmentChecker().check([{"quorum_met": True}, {"quorum_met": True}, {"quorum_met": False}])
    check("6.5 Quorum: 66.7%", r["quorum_pct"] == 66.7)

    r = ExecutionTimelockWatcher().watch({"execution_delay_h": 72})
    check("6.6 ExecTimelock: 72h", r["delay_h"] == 72)

    r = FlashLoanVotingGuard().guard({"flash_loan_protection": True})
    check("6.7 FlashLoan: protected", r["protected"])

    r = VetoRightAuditor().audit({"veto_addresses": ["0xVeto"]})
    check("6.8 Veto: 1 address", r["veto_count"] == 1)

    r = GovernanceStrengthAggregator().aggregate({"a": {"score": 90}})
    check("6.9 Aggregator: score=90", r["pillar_score"] == 90.0)


# ================================================================
# A7-A9: Root Agents
# ================================================================


def test_a7_score_aggregator() -> None:
    section("A7: Skynet Score Aggregator")

    engine = SkynetScoreAggregator()

    # Perfect scores
    r = engine.calculate({p: 100.0 for p in SkynetConfig.weights()})
    check("7.1 Perfect: 100.0", r["skynet_score"] == 100.0)
    check("7.2 Perfect: EXCELLENT", r["rating"] == SkynetRating.SECURE_EXCELLENT.value)

    # Mixed scores
    r = engine.calculate({
        "code_security": 80, "operational_security": 70,
        "governance_strength": 60, "market_stability": 90,
        "fundamental_health": 50, "community_trust": 40,
    })
    expected = round(
        80*0.30 + 70*0.25 + 60*0.15 + 90*0.15 + 50*0.10 + 40*0.05, 1
    )
    check(f"7.3 Mixed: {expected}", r["skynet_score"] == expected)
    check("7.4 Mixed: ACCEPTABLE", r["rating"] == SkynetRating.ACCEPTABLE_MODERATE.value)

    # Below threshold
    r = engine.calculate({p: 50.0 for p in SkynetConfig.weights()})
    check("7.5 All 50: WARNING", r["rating"] == SkynetRating.CRITICAL_WARNING.value)


def test_a8_alert_engine() -> None:
    section("A8: Skynet Risk Alert Engine")

    engine = SkynetRiskAlertEngine()

    r = engine.evaluate(95.0, 96.0)
    check("8.1 Normal: no alert", not r["alert"])

    r = engine.evaluate(90.0, 98.0)
    check("8.2 Drop 8: alert", r["alert"])

    r = engine.evaluate(55.0, 65.0)
    check("8.3 Below critical: alert", r["alert"])

    r = engine.summarize([{"severity": "CRITICAL"}, {"severity": "HIGH"}, {"severity": "LOW"}])
    check("8.4 Summary: 1 crit, 1 high", r["critical"] == 1 and r["high"] == 1)


def test_a9_dashboard() -> None:
    section("A9: Skynet Dashboard Composer")

    dashboard = SkynetDashboardComposer()
    r = dashboard.compose(
        {"skynet_score": 92.5, "rating": "SECURE_EXCELLENT", "risk_level": "LOW", "pillars": {}},
        {"alert": False, "reason": "NORMAL"},
        "TestContract",
    )
    check("9.1 Dashboard: title", "TestContract" in r["title"])
    check("9.2 Dashboard: score", r["skynet_score"] == 92.5)
    check("9.3 Dashboard: has checksum", len(r["checksum"]) == 16)


# ================================================================
# E2E + Config
# ================================================================


def test_e2e_full_orchestrator() -> None:
    section("E2E: Full Skynet Orchestrator")

    orch = SkynetOrchestrator(user_id="test")

    result = orch.run_full_audit(
        contract_name="EscrowVault.sol",
        contract_data={
            "audit_findings": [{"fixed": True}, {"fixed": True}],
            "vulnerabilities": [],
            "contributors": [{"active": True, "reputation": 90} for _ in range(5)],
            "doc_updated": "2026-07-01T00:00:00Z",
            "branch_config": {"required_reviews": True, "status_checks": True},
            "multisig": {"required": 3, "total": 5},
            "timelock": {"delay_seconds": 172800},
            "key_config": {"hsm_used": True},
            "hsm_config": {"verified": True},
            "cloud_certs": ["SOC2 Type2"],
            "key_rotations": [{"date": "2026-07-01T00:00:00Z"}],
        },
        market_data={
            "pool": {"liquidity_usd": 10_000_000},
            "prices": [100, 101, 100],
        },
        community_data={
            "tweets": [{"sentiment": "positive"}] * 10,
        },
        governance_data={
            "voting_power": [1, 2, 3, 4, 5],
            "votes": [{"voter": f"v{i}"} for i in range(15)],
            "voting_config": {"flash_loan_protection": True},
        },
    )

    check("E2E Status completed", result["status"] == "completed")
    check("E2E No error", result["error"] is None)
    report = result["artifacts"][0]
    check("E2E Score exists", isinstance(report["score"]["skynet_score"], (int, float)))
    check("E2E Rating exists", report["score"]["rating"] in [r.value for r in SkynetRating])
    check("E2E 6 Pillars", len(report["score"]["pillars"]) == 6)
    check("E2E Alerts present", "reason" in report["alerts"])
    check("E2E Dashboard present", "checksum" in report["dashboard"])
    check("E2E Raw pillars: 6", len(report["pillars_raw"]) == 6)


def test_config() -> None:
    section("Configuration & Multi-Tenancy")

    check("Cfg: Pass threshold=70", SkynetConfig.SKYNET_PASS_THRESHOLD == 70.0)
    check("Cfg: Excellent=85", SkynetConfig.SKYNET_EXCELLENT == 85.0)
    check("Cfg: Alert delta=5", SkynetConfig.SCORE_DROP_ALERT_DELTA == 5.0)
    check("Cfg: Critical=60", SkynetConfig.SCORE_CRITICAL_THRESHOLD == 60.0)
    weights = SkynetConfig.weights()
    check("Cfg: 6 weights", len(weights) == 6)
    check("Cfg: Sum=1.0", round(sum(weights.values()), 2) == 1.0)


# ================================================================
# Main
# ================================================================


def main() -> int:
    print("=" * 60)
    print("  Wave 21 E2E: Skynet Dynamic Security Score Engine")
    print("  6 Pillars × 8 Subagents + 3 Root Agents")
    print("=" * 60)

    test_p1_code_security()
    test_p2_fundamental_health()
    test_p3_operational_security()
    test_p4_market_stability()
    test_p5_community_trust()
    test_p6_governance_strength()
    test_a7_score_aggregator()
    test_a8_alert_engine()
    test_a9_dashboard()
    test_e2e_full_orchestrator()
    test_config()

    total = PASSED + FAILED
    print(f"\n{'='*60}")
    print(f"  Results: {PASSED}/{total} passed")
    if FAILED > 0:
        print(f"  ❌ {FAILED} FAILED")
    print(f"{'='*60}")

    if FAILED == 0:
        print(f"\n  🛡️  ALLE TESTS BESTANDEN — Skynet Wave 21 ist bereit!")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
