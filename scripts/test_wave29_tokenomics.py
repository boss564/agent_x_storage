#!/usr/bin/env python3
"""
Wave 29 E2E Test Suite: Token Runtime Operations — $AGX Live Mechanics.

Test-Gruppen:
  1. ComputeFuelAuctioneer (9 Subagenten)
  2. SlashingAndPenaltyExecutor (9 Subagenten)
  3. PriorityQueueAccessManager (9 Subagenten)
  4. DisputeBondEscrowAgent (9 Subagenten)
  5. BuybackAndBurnRelayer (9 Subagenten)
  6. LiveYieldAndStakingOperator (9 Subagenten)
  7. OracleDataFeeDispatcher (9 Subagenten)
  8. ERPQuotaAccessManager (9 Subagenten)
  9. E2E: Full Runtime Cycle
  10. E2E: Empty Inputs
  11. Token State
  12. Config & Logging

Usage:
    python3 scripts/test_wave29_tokenomics.py
"""
from __future__ import annotations

import json, os, sys, tempfile, time, uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from agents_b2g.tokenomics.token_runtime_orchestrator import (
    TokenRuntimeConfig, JSONLogger, ComputeFuelAuctioneer,
    SlashingAndPenaltyExecutor, PriorityQueueAccessManager,
    DisputeBondEscrowAgent, BuybackAndBurnRelayer,
    LiveYieldAndStakingOperator, OracleDataFeeDispatcher,
    ERPQuotaAccessManager, TokenRuntimeOrchestrator,
)

PASS, FAIL = 0, 0


def _make_logger(name: str = "test") -> JSONLogger:
    with tempfile.TemporaryDirectory() as td:
        TokenRuntimeConfig.LOG_DIR = Path(td)
    return JSONLogger(name, "test_user")


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1; print(f"  ✅ {name}")
    else:
        FAIL += 1; print(f"  ❌ {name} — {detail}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# Test 1: ComputeFuelAuctioneer
# ============================================================

def test_1_compute():
    section("1. ComputeFuelAuctioneer (9 Subagenten)")
    logger = _make_logger("test_c1")
    cf = ComputeFuelAuctioneer(logger)

    # 1.1 ProofCostEstimator
    cost = cf.proof_cost_estimator(5000, 10)
    check("1.1 ProofCostEstimator > 0", cost > 0)

    # 1.2 ZKCircuitPricer
    zk_cost = cf.zk_circuit_pricer(10000, 10)
    check("1.2 ZKCircuitPricer", zk_cost > 0)

    # 1.3 SkynetScanFeeCalculator
    scan = cf.skynet_scan_fee_calculator(15000, "deep")
    check("1.3 SkynetScanFee (deep > standard)", scan > cf.skynet_scan_fee_calculator(15000, "standard"))

    # 1.4 MempoolSlotAuctioneer
    winner = cf.mempool_slot_auctioneer([{"bidder": "A", "bid_agx": 10}, {"bidder": "B", "bid_agx": 25}])
    check("1.4 MempoolAuction winner = B", winner["winner"] == "B")

    # 1.5 ResourceUtilizationMonitor
    util = cf.resource_utilization_monitor()
    check("1.5 Utilization in range", 10 <= util <= 95)

    # 1.6 DynamicPricingAdjuster
    surge = cf.dynamic_pricing_adjuster()
    check("1.6 Surge factor >= 1.0", surge >= 1.0)

    # 1.7 PrepaidComputeWalletManager
    cf.prepaid_compute_wallet_manager("0xW1", "deposit", 100)
    bal = cf.prepaid_compute_wallet_manager("0xW1")
    check("1.7 Prepaid balance", bal["balance_agx"] == 100.0)

    # 1.8 SolverCompetitionEngine
    solver = cf.solver_competition_engine({})
    check("1.8 Solver competition", solver["winner"] is not None)

    # 1.9 FuelOrchestrator
    result = cf.fuel_orchestrator([{"type": "z3_proof", "constraints": 1000, "depth": 5},
                                    {"type": "skynet_scan", "code_lines": 5000}])
    check("1.9 FuelOrchestrator", result["status"] == "completed")
    check("1.9 Total cost > 0", result["artifacts"][0]["total_cost_agx"] > 0)


# ============================================================
# Test 2: SlashingAndPenaltyExecutor
# ============================================================

def test_2_slashing():
    section("2. SlashingAndPenaltyExecutor (9 Subagenten)")
    logger = _make_logger("test_s2")
    sl = SlashingAndPenaltyExecutor(logger)

    # 2.1 ViolationDetectionEngine
    clean = sl.violation_detection_engine({})
    check("2.1 No violations", not clean["is_violation"])
    bad = sl.violation_detection_engine({"iot_weight_kg": -5, "gps_distance_km": 600})
    check("2.1 Violations detected", bad["count"] == 2)

    # 2.2 SlashingCalculator
    calc = sl.slashing_calculator("0xBad", 100000, 1)
    check("2.2 SlashingCalculator (10%)", calc["penalty_agx"] == 10000)

    # 2.3 StakeLiquidationExecutor
    liq = sl.stake_liquidation_executor("0xBad", 10000)
    check("2.3 Liquidation", liq["status"] == "LIQUIDATED")

    # 2.4 BurnPenaltyDistributor
    burn = sl.burn_penalty_distributor(10000)
    check("2.4 Burn distribution (50%)", burn["burned_agx"] == 5000 and burn["treasury_agx"] == 5000)

    # 2.5 AppealProcessHandler
    appeal = sl.appeal_process_handler("EV-1", "Procedural error")
    check("2.5 Appeal filed", appeal["status"] == "APPEAL_FILED")

    # 2.6 ReputationScoreDeductor
    rep = sl.reputation_score_deductor("0xBad", 100)
    check("2.6 Reputation deduction", rep["new_score"] < 100)

    # 2.7 SlashingEventBroadcaster
    ev = sl.slashing_event_broadcaster({"penalty_agx": 10000})
    check("2.7 Event broadcast", ev["broadcast"])

    # 2.8 AccumulatedPenaltyTracker
    tr = sl.accumulated_penalty_tracker("0xBad")
    check("2.8 Tracker (first offense)", tr["risk_level"] == "CLEAN")

    # 2.9 SlashingOrchestrator
    result = sl.slashing_orchestrator([{"wallet": "0xBad1", "staked_amount": 100000,
                                         "data": {"iot_weight_kg": -5, "zk_proof_invalid": True}}])
    check("2.9 SlashingOrchestrator", result["status"] == "completed")
    check("2.9 Penalty > 0", result["artifacts"][0]["total_penalty_agx"] > 0)


# ============================================================
# Test 3: PriorityQueueAccessManager
# ============================================================

def test_3_priority():
    section("3. PriorityQueueAccessManager (9 Subagenten)")
    logger = _make_logger("test_p3")
    pq = PriorityQueueAccessManager(logger)

    # 3.1 StakeBasedPriorityScore
    score = pq.stake_based_priority_score("0xW", 10000, 365)
    check("3.1 PriorityScore (good stake)", score > 0)
    zero = pq.stake_based_priority_score("0xW", 100, 0)
    check("3.1 PriorityScore (low stake = 0)", zero == 0.0)

    # 3.2 MempoolSlotAllocator
    slot = pq.mempool_slot_allocator({"tx_id": "TX-1", "wallet": "0xW"})
    check("3.2 Slot allocated", slot["slot"] >= 1)

    # 3.3 PriorityFeeCollector
    fee = pq.priority_fee_collector("0xW", 5)
    check("3.3 Priority fee", fee > 0)

    # 3.4 QueuePositionReporter
    pos = pq.queue_position_reporter("TX-1")
    check("3.4 Queue position", pos["slot"] > 0)

    # 3.5 BumpPriorityEngine
    bump = pq.bump_priority_engine("TX-1", 5000)
    check("3.5 Bump", bump["new_slot"] <= bump["old_slot"])

    # 3.6 FairnessEnforcer
    fair = pq.fairness_enforcer("0xW")
    check("3.6 Fairness", not fair["monopolizing"])

    # 3.7 LatencyGuaranteeProvider
    lat = pq.latency_guarantee_provider("TX-1")
    check("3.7 Latency guarantee", lat["guaranteed_max_ms"] > 0)

    # 3.8 PriorityAuditLogger
    al = pq.priority_audit_logger({"action": "SLOT_ASSIGNED"})
    check("3.8 Audit log", len(al["audit_hash"]) > 0)

    # 3.9 PriorityOrchestrator
    reqs = [{"tx_id": f"TX-{i}", "wallet": f"0xW{i}", "staked_agx": 5000, "stake_days": 30} for i in range(3)]
    result = pq.priority_orchestrator(reqs)
    check("3.9 PriorityOrchestrator", result["status"] == "completed")


# ============================================================
# Test 4: DisputeBondEscrowAgent
# ============================================================

def test_4_dispute():
    section("4. DisputeBondEscrowAgent (9 Subagenten)")
    logger = _make_logger("test_d4")
    db = DisputeBondEscrowAgent(logger)

    # 4.1 DisputeBondDepositor
    bond = db.dispute_bond_depositor("D-1", "PartyA", "PartyB", 2000)
    check("4.1 Bond deposited", bond["total_escrow_agx"] == 4000)

    # 4.2 EscrowStateManager
    state = db.escrow_state_manager("D-1")
    check("4.2 Escrow state PENDING", state["state"] == "PENDING")
    db.escrow_state_manager("D-1", "ACTIVE")
    check("4.2 Escrow state ACTIVE", db.escrow_state_manager("D-1")["state"] == "ACTIVE")

    # 4.3 ArbitrationTriggerExecutor
    arb = db.arbitration_trigger_executor("D-1")
    check("4.3 Arbitration started", arb["arbitration_started"])

    # 4.4 ExpertWitnessFeeCollector
    fee = db.expert_witness_fee_collector("D-1", 3)
    check("4.4 Expert fee", fee == 750)

    # 4.5 BondForfeitureEngine
    forfeit = db.bond_forfeiture_engine("D-1", "PartyB")
    check("4.5 Forfeiture", forfeit["forfeited_agx"] > 0)

    # 4.6 SettlementDistributor
    db.dispute_bond_depositor("D-2", "PartyA", "PartyB", 1000)
    settle = db.settlement_distributor("D-2", "PartyA")
    check("4.6 Settlement", settle["settled_agx"] > 0)

    # 4.7 DisputeDurationTimer
    timer = db.dispute_duration_timer("D-1")
    check("4.7 Timer", timer["deadline_days"] == 14)

    # 4.8 AppealProcessManager
    appeal = db.appeal_process_manager("D-1", "New evidence found")
    check("4.8 Appeal", appeal["status"] == "APPEAL_ACCEPTED")

    # 4.9 DisputeOrchestrator
    result = db.dispute_orchestrator([{"party_a": "A", "party_b": "B", "bond_agx": 1000, "resolved_in_favor_of": "A"}])
    check("4.9 DisputeOrchestrator", result["status"] == "completed")


# ============================================================
# Test 5: BuybackAndBurnRelayer
# ============================================================

def test_5_burn():
    section("5. BuybackAndBurnRelayer (9 Subagenten)")
    logger = _make_logger("test_b5")
    bb = BuybackAndBurnRelayer(logger)

    # 5.1 FeeCollectionAggregator
    fees = bb.fee_collection_aggregator([{"source": "fuel", "amount_agx": 5000}, {"source": "prio", "amount_agx": 2000}])
    check("5.1 Fee aggregation", fees["total_fees_collected_agx"] == 7000)

    # 5.2 BuybackSchedulePlanner
    schedule = bb.buyback_schedule_planner()
    check("5.2 Schedule", schedule["schedule_days"] == 7)

    # 5.3 DEXRouterSelector
    dex = bb.dex_router_selector(10000)
    check("5.3 DEX selection", dex["best_dex"] is not None)

    # 5.4 SlippageProtectionEnforcer
    slip = bb.slippage_protection_enforcer(10000)
    check("5.4 Slippage (small = allowed)", slip["allowed"])

    # 5.5 BurnTransactionExecutor
    burn = bb.burn_transaction_executor(5000)
    check("5.5 Burn executed", burn["burn_amount_agx"] == 5000)

    # 5.6 SupplyReductionTracker
    supply = bb.supply_reduction_tracker()
    check("5.6 Supply tracked", supply["circulating"] < TokenRuntimeConfig.TOTAL_SUPPLY)

    # 5.7 DeflationRateDashboard
    dash = bb.deflation_rate_dashboard(30)
    check("5.7 Deflation dashboard", dash["period_days"] == 30)

    # 5.8 BuybackAuditLogger
    audit = bb.buyback_audit_logger({"amount_agx": 5000})
    check("5.8 Audit log", len(audit["worm_hash"]) > 0)

    # 5.9 BurnOrchestrator
    result = bb.burn_orchestrator(10000)
    check("5.9 BurnOrchestrator", result["status"] == "completed")


# ============================================================
# Test 6: LiveYieldAndStakingOperator
# ============================================================

def test_6_yield():
    section("6. LiveYieldAndStakingOperator (9 Subagenten)")
    logger = _make_logger("test_y6")
    ys = LiveYieldAndStakingOperator(logger)

    # 6.1 StakingPoolManager
    pool = ys.staking_pool_manager("pool_1")
    check("6.1 Pool default APY", pool["apy"] == 0.05)

    # 6.2 RewardAccrualEngine
    reward = ys.reward_accrual_engine("0xW", 100000, 30)
    check("6.2 Reward > 0", reward > 0)

    # 6.3 CompoundFrequencyOptimizer
    comp = ys.compound_frequency_optimizer(0.05)
    check("6.3 Compound apy > apr", comp["daily_apy"] > 0.05)

    # 6.4 UnstakingCooldownEnforcer
    cool = ys.unstaking_cooldown_enforcer("0xW")
    check("6.4 Cooldown", cool["cooldown_days"] == 7)

    # 6.5 YieldCurveAdjuster
    adj = ys.yield_curve_adjuster("pool_1", 5_000_000)
    check("6.5 Adjusted APY > base", adj > 0.05)

    # 6.6 StakeMigrationHandler
    mig = ys.stake_migration_handler("0xW", "pool_1", "pool_2", 10000)
    check("6.6 Migration", mig["status"] == "MIGRATED")

    # 6.7 ValidatorPerformanceScorer
    scorer = ys.validator_performance_scorer("0xW")
    check("6.7 Performance score >= 0", scorer["performance_score"] >= 0)

    # 6.8 WithdrawalProtectionGuard
    ys._pools["pool_1"] = {"apy": 0.05, "total_staked": 1000000}
    guard = ys.withdrawal_protection_guard("pool_1", 100000)
    check("6.8 Withdrawal allowed (10%)", not guard["blocked"])
    guard2 = ys.withdrawal_protection_guard("pool_1", 300000)
    check("6.8 Withdrawal blocked (30%)", guard2["blocked"])

    # 6.9 YieldOrchestrator
    result = ys.yield_orchestrator([{"wallet": "0xW1", "amount_agx": 50000}, {"wallet": "0xW2", "amount_agx": 25000}])
    check("6.9 YieldOrchestrator", result["status"] == "completed")
    check("6.9 Rewards > 0", result["artifacts"][0]["total_rewards_distributed_agx"] > 0)


# ============================================================
# Test 7: OracleDataFeeDispatcher
# ============================================================

def test_7_oracle():
    section("7. OracleDataFeeDispatcher (9 Subagenten)")
    logger = _make_logger("test_o7")
    od = OracleDataFeeDispatcher(logger)

    # 7.1 OracleRegistryManager
    od.oracle_registry_manager("CL-1", "register", "https://oracle.chain.link")
    check("7.1 Oracle registered", "CL-1" in str(od._oracle_registry))

    # 7.2 DataFreshnessValidator
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    fresh = od.data_freshness_validator(now)
    check("7.2 Data fresh", fresh["fresh"])

    # 7.3 FeeCalculationEngine
    fee = od.fee_calculation_engine("chainlink", 10)
    check("7.3 Chainlink fee", fee > 0)

    # 7.4 ChainlinkPaymentRelayer
    cl = od.chainlink_payment_relayer("AGX/EURe", 5.0)
    check("7.4 Chainlink paid", cl["status"] == "PAID")

    # 7.5 WeatherOraclePayer
    wx = od.weather_oracle_payer("BERLIN", 2.0)
    check("7.5 Weather paid", wx["amount_agx"] == 2.0)

    # 7.6 DINOraclePayer
    din = od.din_oracle_payer("DIN-276", 10.0)
    check("7.6 DIN paid", din["amount_agx"] == 10.0)

    # 7.7 OraclePerformanceTracker
    perf = od.oracle_performance_tracker("CL-1")
    check("7.7 Performance", perf["queries_served"] == 0)

    # 7.8 DisputeResolutionForOracles
    dr = od.dispute_resolution_for_oracles("CL-1", "Stale data")
    check("7.8 Dispute", dr["resolution"] == "PAYMENT_WITHHELD")

    # 7.9 OracleDispatcherOrchestrator
    result = od.oracle_dispatcher_orchestrator([
        {"oracle_type": "chainlink", "feed_id": "AGX/EURe", "data_points": 5, "timestamp": now},
        {"oracle_type": "weather", "station_id": "BERLIN", "data_points": 3, "timestamp": now},
    ])
    check("7.9 OracleOrchestrator", result["status"] == "completed")
    check("7.9 Payments > 0", result["artifacts"][0]["total_paid_agx"] > 0)


# ============================================================
# Test 8: ERPQuotaAccessManager
# ============================================================

def test_8_erp():
    section("8. ERPQuotaAccessManager (9 Subagenten)")
    logger = _make_logger("test_e8")
    erp = ERPQuotaAccessManager(logger)

    # 8.1 ERPIntegrationRegistry
    erp.erp_integration_registry("SAP_01", "SAP", "0xEnterprise")
    check("8.1 ERP registered", "SAP_01" in erp._erp_registry)

    # 8.2 QuotaTierCalculator
    tier = erp.quota_tier_calculator(200000)
    check("8.2 Tier PLATINUM", tier["tier"] == "PLATINUM")
    tier2 = erp.quota_tier_calculator(500)
    check("8.2 Tier FREE", tier2["tier"] == "FREE")

    # 8.3 RateLimitByStake
    rl = erp.rate_limit_by_stake("SAP_01", 50)
    check("8.3 Rate limit OK", not rl["exceeded"])

    # 8.4 SAPConnectorQuotaManager
    sap = erp.sap_connector_quota_manager("SAP_01", 200)
    check("8.4 SAP exceeded", sap["exceeded"])

    # 8.5 DATEVDatenExporter
    dv = erp.datev_daten_exporter("SAP_01", 500)
    check("8.5 DATEV export", "allowed" in dv)

    # 8.6 ThroughputMonitor
    tp = erp.throughput_monitor("SAP_01")
    check("8.6 Throughput", tp["current_rps"] >= 0)

    # 8.7 OverageFeeCollector
    of = erp.overage_fee_collector("SAP_01", 100)
    check("8.7 Overage fee", of["overage_fee_agx"] > 0)

    # 8.8 QuotaUpgradePath
    up = erp.quota_upgrade_path("SAP_01", "BRONZE")
    check("8.8 Upgrade path", up["next_tier"] == "SILVER")

    # 8.9 ERPOrchestrator
    result = erp.erp_orchestrator([{"erp_id": "SAP_02", "erp_type": "SAP", "wallet": "0xE2", "current_rps": 30},
                                    {"erp_id": "SAP_03", "erp_type": "DATEV", "wallet": "0xE3", "current_rps": 200}])
    check("8.9 ERPOrchestrator", result["status"] == "completed")


# ============================================================
# Test 9: E2E Full Runtime Cycle
# ============================================================

def test_9_e2e():
    section("9. E2E: Full Runtime Cycle")
    orch = TokenRuntimeOrchestrator(user_id="test_e2e")
    result = orch.process_runtime_cycle(
        compute_requests=[{"type": "z3_proof", "constraints": 2000, "depth": 5},
                           {"type": "skynet_scan", "code_lines": 10000, "depth": "standard"}],
        violations=[{"wallet": "0xBadX", "staked_amount": 50000, "reputation_score": 80,
                      "data": {"iot_weight_kg": -3, "zk_proof_invalid": True}}],
        payment_requests=[{"tx_id": f"TX-E2E-{i}", "wallet": f"0xPay{i}", "staked_agx": 20000, "stake_days": 90}
                           for i in range(3)],
        disputes=[{"party_a": "FirmaAG", "party_b": "Kommune", "bond_agx": 1500, "resolved_in_favor_of": "FirmaAG"}],
        fee_sources=[{"source": "fuel", "amount_agx": 8000}, {"source": "priority", "amount_agx": 2000}],
        stakers=[{"wallet": f"0xS{i}", "amount_agx": 25000} for i in range(3)],
        oracle_requests=[{"oracle_type": "chainlink", "feed_id": "AGX/ETH", "data_points": 5,
                           "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}],
        erp_requests=[{"erp_id": "SAP_E2E", "erp_type": "SAP", "wallet": "0xEnt", "current_rps": 25}],
    )
    a = result["artifacts"][0]
    check("9.1 Status completed", result["status"] == "completed")
    check("9.2 All 8 green", a["all_green"])
    check("9.3 Duration < 5s", a["duration_s"] < 5.0)
    check("9.4 Burned > 0", a["burned_agx"] > 0 or a["slashed_agx"] > 0)


# ============================================================
# Test 10: Empty Inputs
# ============================================================

def test_10_empty():
    section("10. E2E: Empty Inputs")
    orch = TokenRuntimeOrchestrator(user_id="test_empty")
    result = orch.process_runtime_cycle()
    check("10.1 Handles empty", result["status"] == "completed")
    check("10.2 All green with empty", result["artifacts"][0]["all_green"])


# ============================================================
# Test 11: Token State
# ============================================================

def test_11_state():
    section("11. Token State")
    orch = TokenRuntimeOrchestrator(user_id="test_state")
    state = orch.get_token_state()
    s = state["artifacts"][0]
    check("11.1 Total supply 100M", s["total_supply"] == 100_000_000)
    check("11.2 Symbol AGX", s["symbol"] == "AGX")
    check("11.3 Decimals 18", s["decimals"] == 18)
    check("11.4 Circulating < total", s["circulating"] < s["total_supply"])


# ============================================================
# Test 12: Config & Logging
# ============================================================

def test_12_config():
    section("12. Config & Logging")
    check("12.1 TOTAL_SUPPLY 100M", TokenRuntimeConfig.TOTAL_SUPPLY == 100_000_000)
    check("12.2 Z3_BASE_PRICE 0.1", TokenRuntimeConfig.Z3_BASE_PRICE_AGX == 0.1)
    check("12.3 SLASHING_RATE 10%", TokenRuntimeConfig.SLASHING_RATE_DEFAULT == 0.1)
    check("12.4 BUYBACK_RATE 20%", TokenRuntimeConfig.BUYBACK_RATE == 0.2)
    check("12.5 STAKING_APY 5%", TokenRuntimeConfig.STAKING_BASE_APY == 0.05)
    check("12.6 UNSTAKING_COOLDOWN 7d", TokenRuntimeConfig.UNSTAKING_COOLDOWN_DAYS == 7)
    check("12.7 DISPUTE_BOND_MIN 500", TokenRuntimeConfig.DISPUTE_BOND_MIN_AGX == 500)
    check("12.8 ERP_BASE_QUOTA 100", TokenRuntimeConfig.ERP_BASE_QUOTA_RPS == 100)

    with tempfile.TemporaryDirectory() as td:
        TokenRuntimeConfig.LOG_DIR = Path(td)
        logger = JSONLogger("test_config", "test_user")
        logger.info("Test log", key="value")
        log_files = list(Path(td).glob("*.jsonl"))
        check("12.9 Log file created", len(log_files) > 0)

    check("12.10 Config env", os.getenv("AGX_SYMBOL", "AGX") == "AGX")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  🧪 WAVE 29: TOKEN RUNTIME OPERATIONS TEST SUITE")
    print("=" * 70)

    test_1_compute()
    test_2_slashing()
    test_3_priority()
    test_4_dispute()
    test_5_burn()
    test_6_yield()
    test_7_oracle()
    test_8_erp()
    test_9_e2e()
    test_10_empty()
    test_11_state()
    test_12_config()

    print(f"\n{'='*70}")
    print(f"  📊 ERGEBNIS: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    print(f"{'='*70}")

    if FAIL > 0:
        print(f"\n  ❌ {FAIL} TEST(S) FEHLGESCHLAGEN!")
        sys.exit(1)
    else:
        print(f"\n  ✅ ALLE {PASS} TESTS BESTANDEN!")
        sys.exit(0)
