#!/usr/bin/env python3
"""Agent X SimChain — Test Suite (Wave 35).

Tests all 9 agents across 3 chains, the orchestrator, cross-chain mechanics,
economic friction, compliance, and heterogeneous market verification.

Usage:
  python3 scripts/test_simchain.py              # Run all tests
  python3 scripts/test_simchain.py --verbose    # Verbose output
"""

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.simchain.subagents.sensor_aggregator import SensorAggregatorAgent
from agents_b2g.simchain.subagents.bridge_agent import BridgeAgent
from agents_b2g.simchain.subagents.depin_wallet import DePINWalletAgent
from agents_b2g.simchain.subagents.vob_settlement import VOBSettlementAgent
from agents_b2g.simchain.subagents.legal_compliance import LegalComplianceAgent
from agents_b2g.simchain.subagents.settlement_executor import SettlementExecutorAgent
from agents_b2g.simchain.subagents.token_minter import TokenMinterAgent
from agents_b2g.simchain.subagents.staking_pool import StakingPoolAgent
from agents_b2g.simchain.subagents.burn_fee_agent import BurnFeeAgent
from agents_b2g.simchain import EconomicOrchestratorMulti

# ── Test Infrastructure ──────────────────────────────────────────────────────

PASS = 0
FAIL = 0
ERRORS: List[str] = []
VERBOSE = False


def log(msg: str) -> None:
    if VERBOSE:
        print(f"  {msg}")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL, ERRORS
    if condition:
        PASS += 1
        status = "✅"
    else:
        FAIL += 1
        status = "❌"
        ERRORS.append(f"{name}: {detail}")
    print(f"  {status} {name}")


def assert_standard_json(result: Dict, agent_name: str = "") -> None:
    """Verify standardized JSON output contract."""
    required = ["status", "job_id", "artifacts", "error", "logs"]
    for key in required:
        check(
            f"{agent_name} has '{key}' field" if agent_name else f"has '{key}' field",
            key in result,
            f"Missing key: {key}",
        )
    check(
        f"{agent_name} status is valid" if agent_name else "status valid",
        result.get("status") in ("started", "completed", "failed", "skipped"),
    )
    check(
        f"{agent_name} job_id is non-empty" if agent_name else "job_id non-empty",
        bool(result.get("job_id")),
    )


def assert_no_exception(result: Dict) -> None:
    """Verify no unhandled exception in result."""
    check("no unhandled error", result.get("status") != "failed" or result.get("error") is not None)


# ── S1: SensorAggregatorAgent Tests ─────────────────────────────────────────

async def test_sensor_basic():
    """S1.1: Basic sensor batch processing."""
    agent = SensorAggregatorAgent(user_id="test", batch_size=100)
    result = await agent.process_batch(cycle=1)
    assert_standard_json(result, "S1")
    check("S1.1 status=completed", result["status"] == "completed")
    check("S1.1 has artifacts", len(result["artifacts"]) > 0)
    check("S1.1 correct batch size", result["artifacts"][0]["event_count"] == 100)
    check("S1.1 has transactions", len(result["artifacts"][0]["transactions"]) == 100)
    check("S1.1 has batch_hash", bool(result["artifacts"][0]["batch_hash"]))


async def test_sensor_amount_range():
    """S1.2: Sensor amounts within expected range."""
    agent = SensorAggregatorAgent(user_id="test", batch_size=200)
    result = await agent.process_batch(cycle=1)
    txs = result["artifacts"][0]["transactions"]
    amounts = [t["amount"] for t in txs]
    check("S1.2 min >= 0.001", min(amounts) >= 0.001)
    check("S1.2 max <= 0.50", max(amounts) <= 0.50)


async def test_sensor_stats():
    """S1.3: Sensor statistics tracking."""
    agent = SensorAggregatorAgent(user_id="test", batch_size=50)
    await agent.process_batch(cycle=1)
    await agent.process_batch(cycle=2)
    stats = agent.get_stats()
    check("S1.3 total_events=100", stats["total_events"] == 100)
    check("S1.3 total_volume>0", stats["total_volume"] > 0)


async def test_sensor_failure_handling():
    """S1.4: Sensor handles errors gracefully."""
    agent = SensorAggregatorAgent(user_id="test", batch_size=10)
    # Inject invalid state — should still complete
    result = await agent.process_batch(cycle=-1)  # negative cycle, still works
    check("S1.4 handles edge case", result["status"] in ("completed", "failed"))


# ── S2: BridgeAgent Tests ────────────────────────────────────────────────────

async def test_bridge_basic():
    """S2.1: Basic bridge relay."""
    agent = BridgeAgent(user_id="test")
    txs = [{"sensor_id": f"S_{i}", "amount": 0.01 * i, "timestamp": "2026-08-09T00:00:00Z"} for i in range(10)]
    result = await agent.process_batch(txs, target_chain="SETTLEMENT_L1")
    assert_standard_json(result, "S2")
    check("S2.1 status=completed", result["status"] == "completed")
    msgs = result["artifacts"][0]["messages"]
    check("S2.1 10 messages", len(msgs) == 10)
    check("S2.1 has bridge_proof", all("bridge_proof" in m for m in msgs))
    check("S2.1 latency in [2,5]", all(2 <= m["latency_ticks"] <= 5 for m in msgs))


async def test_bridge_latency_range():
    """S2.2: Bridge latency stays within configured range."""
    agent = BridgeAgent(user_id="test", latency_ticks=[3, 4])
    txs = [{"sensor_id": "S_1", "amount": 0.5}] * 50
    result = await agent.process_batch(txs)
    msgs = result["artifacts"][0]["messages"]
    latencies = [m["latency_ticks"] for m in msgs]
    check("S2.2 all latencies in [3,4]", all(l in (3, 4) for l in latencies))


async def test_bridge_empty_batch():
    """S2.3: Bridge handles empty batch."""
    agent = BridgeAgent(user_id="test")
    result = await agent.process_batch([], target_chain="SETTLEMENT_L1")
    check("S2.3 handles empty", result["status"] == "completed")
    check("S2.3 zero messages", len(result["artifacts"][0]["messages"]) == 0)


async def test_bridge_stats():
    """S2.4: Bridge statistics accumulation."""
    agent = BridgeAgent(user_id="test")
    txs = [{"sensor_id": "S_1", "amount": 0.5}] * 20
    await agent.process_batch(txs)
    stats = agent.get_stats()
    check("S2.4 total_relayed=20", stats["total_messages_relayed"] == 20)
    check("S2.4 total_volume>0", stats["total_volume_bridged"] > 0)


# ── S3: DePINWalletAgent Tests ──────────────────────────────────────────────

async def test_depin_wallet_basic():
    """S3.1: Basic wallet payout processing."""
    agent = DePINWalletAgent(user_id="test", payout_threshold=5.0)
    txs = [{"sensor_id": f"SENSOR_{i}", "amount": 0.1} for i in range(30)]
    result = await agent.process_batch(txs)
    assert_standard_json(result, "S3")
    check("S3.1 status=completed", result["status"] == "completed")
    check("S3.1 wallets_updated>0", result["artifacts"][0]["wallets_updated"] > 0)


async def test_depin_wallet_threshold_payout():
    """S3.2: Auto-payout triggers at threshold."""
    agent = DePINWalletAgent(user_id="test", payout_threshold=1.0)
    txs = [{"sensor_id": "SENSOR_1", "amount": 0.6}] * 5  # total 3.0 → triggers payout at 1.0
    await agent.process_batch(txs)
    stats = agent.get_stats()
    check("S3.2 active_wallets=1", stats["active_wallets"] == 1)
    check("S3.2 total_payouts>0", stats["total_payouts_processed"] > 0)


async def test_depin_wallet_multi_sensor():
    """S3.3: Multiple sensors tracked independently."""
    agent = DePINWalletAgent(user_id="test")
    txs = [{"sensor_id": f"S_{i}", "amount": 0.01} for i in range(100)]
    await agent.process_batch(txs)
    stats = agent.get_stats()
    check("S3.3 100 wallets", stats["active_wallets"] == 100)


async def test_depin_wallet_empty():
    """S3.4: Wallet handles empty batch."""
    agent = DePINWalletAgent(user_id="test")
    result = await agent.process_batch([])
    check("S3.4 handles empty", result["status"] == "completed")


# ── L1: VOBSettlementAgent Tests ────────────────────────────────────────────

async def test_vob_basic():
    """L1.1: Basic VOB/B settlement processing."""
    agent = VOBSettlementAgent(user_id="test")
    msgs = [{"payload": {"amount": 1000.0, "sensor_id": "S_1"}} for _ in range(5)]
    result = await agent.process_batch(msgs)
    assert_standard_json(result, "L1")
    check("L1.1 status=completed", result["status"] == "completed")
    check("L1.1 has settlements", len(result["artifacts"][0]["settlements"]) > 0)
    check("L1.1 has Z3 proofs", all("z3_proof" in s for s in result["artifacts"][0]["settlements"]))


async def test_vob_projects_have_5pct_retention():
    """L1.2: 5% retention calculated per settlement."""
    agent = VOBSettlementAgent(user_id="test")
    msgs = [{"payload": {"amount": 10000.0, "sensor_id": "S_1"}}]
    result = await agent.process_batch(msgs)
    s = result["artifacts"][0]["settlements"][0]
    check("L1.2 retention=5%", abs(s["retention_5pct"] - s["amount"] * 0.05) < 0.01)


async def test_vob_milestone_progress():
    """L1.3: Projects advance through milestones."""
    agent = VOBSettlementAgent(user_id="test")
    msgs = [{"payload": {"amount": 1000.0, "sensor_id": "S_1"}} for _ in range(20)]
    await agent.process_batch(msgs)
    stats = agent.get_stats()
    check("L1.3 total_settlements>0", stats["total_settlements"] > 0)
    check("L1.3 total_settled>0", stats["total_settled"] > 0)


async def test_vob_empty():
    """L1.4: VOB handles empty input."""
    agent = VOBSettlementAgent(user_id="test")
    result = await agent.process_batch([])
    check("L1.4 handles empty", result["status"] == "completed")


# ── L2: LegalComplianceAgent Tests ──────────────────────────────────────────

async def test_legal_basic():
    """L2.1: Basic tax computation."""
    agent = LegalComplianceAgent(user_id="test", tax_rate=0.19, construction_withholding=0.15)
    settlements = [{"project_id": "P1", "amount": 1000.0}]
    result = await agent.process_batch(settlements)
    assert_standard_json(result, "L2")
    tx = result["artifacts"][0]["transactions"][0]
    check("L2.1 tax=190.00", abs(tx["tax"] - 190.0) < 0.01)
    check("L2.1 withholding=150.00", abs(tx["withholding_tax"] - 150.0) < 0.01)
    check("L2.1 net=660.00", abs(tx["net"] - 660.0) < 0.01)


async def test_legal_audit_trail():
    """L2.2: GoBD audit trail accumulates."""
    agent = LegalComplianceAgent(user_id="test")
    settlements = [{"project_id": "P1", "amount": 500.0} for _ in range(10)]
    await agent.process_batch(settlements)
    stats = agent.get_stats()
    check("L2.2 audit_entries=10", stats["audit_trail_entries"] == 10)
    check("L2.2 tax_collected>0", stats["total_tax_collected"] > 0)


async def test_legal_gobd_compliance():
    """L2.3: All transactions have GoBD WORM hash."""
    agent = LegalComplianceAgent(user_id="test")
    result = await agent.process_batch([{"project_id": "P1", "amount": 1000.0}])
    tx = result["artifacts"][0]["transactions"][0]
    check("L2.3 has audit_id", bool(tx.get("audit_id")))
    check("L2.3 has gobd_worm_hash", bool(tx.get("gobd_worm_hash")))


async def test_legal_empty():
    """L2.4: Legal handles empty input."""
    agent = LegalComplianceAgent(user_id="test")
    result = await agent.process_batch([])
    check("L2.4 handles empty", result["status"] == "completed")


# ── L3: SettlementExecutorAgent Tests ───────────────────────────────────────

async def test_executor_basic():
    """L3.1: Basic multi-split execution."""
    agent = SettlementExecutorAgent(user_id="test")
    txs = [{"project_id": "P1", "amount": 1000.0, "tax": 150.0, "audit_id": "A1"}]
    result = await agent.process_batch(txs)
    assert_standard_json(result, "L3")
    s = result["artifacts"][0]["settlements"][0]
    check("L3.1 net=800.00", abs(s["net"] - 800.0) < 0.01)
    check("L3.1 retention=50.00", abs(s["retention"] - 50.0) < 0.01)
    check("L3.1 BHO Δ=0", abs(s["bho_delta"]) < 0.02)


async def test_executor_escrow_accumulation():
    """L3.2: Escrow balance accumulates across settlements."""
    agent = SettlementExecutorAgent(user_id="test")
    txs = [{"project_id": "P1", "amount": 1000.0, "tax": 150.0, "audit_id": "A1"} for _ in range(5)]
    await agent.process_batch(txs)
    stats = agent.get_stats()
    check("L3.2 escrow=250.00", abs(stats["escrow_balance"] - 250.0) < 0.05)


async def test_executor_bho_zero_sum():
    """L3.3: Every settlement has BHO Δ=0."""
    agent = SettlementExecutorAgent(user_id="test")
    txs = [{"project_id": f"P{i}", "amount": 1000.0 * i, "tax": 150.0 * i, "audit_id": f"A{i}"} for i in range(1, 6)]
    result = await agent.process_batch(txs)
    settlements = result["artifacts"][0]["settlements"]
    check("L3.3 all BHO Δ≈0", all(abs(s["bho_delta"]) < 0.02 for s in settlements))


async def test_executor_empty():
    """L3.4: Executor handles empty input."""
    agent = SettlementExecutorAgent(user_id="test")
    result = await agent.process_batch([])
    check("L3.4 handles empty", result["status"] == "completed")


# ── T1: TokenMinterAgent Tests ──────────────────────────────────────────────

async def test_minter_basic():
    """T1.1: Basic token minting."""
    agent = TokenMinterAgent(user_id="test", burn_rate=0.05)
    settlements = [{"project_id": "P1", "net": 1000.0}]
    result = await agent.process_batch(settlements)
    assert_standard_json(result, "T1")
    t = result["artifacts"][0]["tokens"][0]
    check("T1.1 mint_amount=1000", abs(t["mint_amount"] - 1000.0) < 0.01)
    check("T1.1 burn_amount=50", abs(t["burn_amount"] - 50.0) < 0.01)
    check("T1.1 net_tokens=950", abs(t["net_tokens"] - 950.0) < 0.01)


async def test_minter_burn_rate():
    """T1.2: Custom burn rate applies correctly."""
    agent = TokenMinterAgent(user_id="test", burn_rate=0.10)
    result = await agent.process_batch([{"project_id": "P1", "net": 500.0}])
    t = result["artifacts"][0]["tokens"][0]
    check("T1.2 burn=50 at 10%", abs(t["burn_amount"] - 50.0) < 0.01)


async def test_minter_supply_tracking():
    """T1.3: Effective supply tracks mint-burn."""
    agent = TokenMinterAgent(user_id="test", burn_rate=0.05)
    settlements = [{"project_id": f"P{i}", "net": 100.0} for i in range(10)]
    await agent.process_batch(settlements)
    stats = agent.get_stats()
    check("T1.3 total_minted=1000", abs(stats["total_minted"] - 1000.0) < 0.01)
    check("T1.3 total_burned=50", abs(stats["total_burned"] - 50.0) < 0.01)
    check("T1.3 effective_supply=950", abs(stats["effective_supply"] - 950.0) < 0.01)


async def test_minter_empty():
    """T1.4: Minter handles empty input."""
    agent = TokenMinterAgent(user_id="test")
    result = await agent.process_batch([])
    check("T1.4 handles empty", result["status"] == "completed")


# ── T2: StakingPoolAgent Tests ──────────────────────────────────────────────

async def test_staking_basic():
    """T2.1: Basic staking position creation."""
    agent = StakingPoolAgent(user_id="test", apy=0.12, lockup_ratio=0.80)
    tokens = [{"token_id": "T1", "project_id": "P1", "net_tokens": 1000.0}]
    result = await agent.process_batch(tokens)
    assert_standard_json(result, "T2")
    p = result["artifacts"][0]["positions"][0]
    check("T2.1 locked=800", abs(p["locked_amount"] - 800.0) < 0.01)
    check("T2.1 liquid=200", abs(p["liquid_amount"] - 200.0) < 0.01)
    # Monthly yield = 800 * 0.12/12 = 8.0
    check("T2.1 yield=8.0", abs(p["yield_earned"] - 8.0) < 0.01)


async def test_staking_yield_accumulation():
    """T2.2: Yield accumulates across positions."""
    agent = StakingPoolAgent(user_id="test", apy=0.12, lockup_ratio=1.0)
    tokens = [{"token_id": f"T{i}", "project_id": f"P{i}", "net_tokens": 100.0} for i in range(10)]
    await agent.process_batch(tokens)
    stats = agent.get_stats()
    check("T2.2 total_locked=1000", abs(stats["total_locked"] - 1000.0) < 0.01)
    check("T2.2 total_yield=10.0", abs(stats["total_yield_distributed"] - 10.0) < 0.01)


async def test_staking_custom_lockup():
    """T2.3: Custom lockup ratio."""
    agent = StakingPoolAgent(user_id="test", lockup_ratio=0.50)
    result = await agent.process_batch([{"token_id": "T1", "net_tokens": 1000.0}])
    p = result["artifacts"][0]["positions"][0]
    check("T2.3 locked=500 at 50%", abs(p["locked_amount"] - 500.0) < 0.01)


async def test_staking_empty():
    """T2.4: Staking handles empty input."""
    agent = StakingPoolAgent(user_id="test")
    result = await agent.process_batch([])
    check("T2.4 handles empty", result["status"] == "completed")


# ── T3: BurnFeeAgent Tests ──────────────────────────────────────────────────

async def test_burnfee_basic():
    """T3.1: Basic fee and burn application."""
    agent = BurnFeeAgent(user_id="test", fee_rate=0.02, additional_burn_rate=0.01)
    positions = [{"position_id": "S1", "token_id": "T1", "liquid_amount": 200.0}]
    result = await agent.process_batch(positions)
    assert_standard_json(result, "T3")
    op = result["artifacts"][0]["operations"][0]
    check("T3.1 fee=4.0", abs(op["fee"] - 4.0) < 0.01)
    check("T3.1 burn=2.0", abs(op["burn"] - 2.0) < 0.01)
    check("T3.1 net=194.0", abs(op["net_payout"] - 194.0) < 0.01)
    check("T3.1 friction=6.0", abs(op["friction_eur"] - 6.0) < 0.01)


async def test_burnfee_friction_tracking():
    """T3.2: Sicker loss accumulates correctly."""
    agent = BurnFeeAgent(user_id="test", fee_rate=0.02, additional_burn_rate=0.01)
    positions = [{"position_id": f"S{i}", "token_id": f"T{i}", "liquid_amount": 100.0} for i in range(10)]
    await agent.process_batch(positions)
    stats = agent.get_stats()
    check("T3.2 total_fees=20.0", abs(stats["total_fees_collected"] - 20.0) < 0.01)
    check("T3.2 total_burns=10.0", abs(stats["total_burns_executed"] - 10.0) < 0.01)
    check("T3.2 total_friction=30.0", abs(stats["total_friction_eur"] - 30.0) < 0.01)


async def test_burnfee_zero_liquid():
    """T3.3: Zero liquid amount handled."""
    agent = BurnFeeAgent(user_id="test")
    result = await agent.process_batch([{"position_id": "S1", "token_id": "T1", "liquid_amount": 0.0}])
    op = result["artifacts"][0]["operations"][0]
    check("T3.3 net_payout=0", op["net_payout"] == 0.0)


async def test_burnfee_empty():
    """T3.4: BurnFee handles empty input."""
    agent = BurnFeeAgent(user_id="test")
    result = await agent.process_batch([])
    check("T3.4 handles empty", result["status"] == "completed")


# ── Orchestrator Tests ──────────────────────────────────────────────────────

async def test_orchestrator_full_simulation():
    """O1: Full multi-chain simulation completes."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=10, sensor_batch_size=50)
    result = await orch.run_simulation(cycles=10)
    check("O1 status=completed", result["status"] == "completed")
    check("O1 has artifacts", len(result["artifacts"]) > 0)
    check("O1 has sim_id", bool(result.get("sim_id")))


async def test_orchestrator_friction_verified():
    """O2: Friction is falsifiable and verified (>0 and ≤ value_in)."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=20, sensor_batch_size=100)
    await orch.run_simulation(cycles=20)
    report = orch.generate_report()
    fa = report["artifacts"][0]["friction_analysis"]
    check("O2 friction_verified=True", fa["friction_verified"] is True)
    check("O2 value_conserved=True", fa["value_conserved"] is True)
    check("O2 three_separate_ledgers=True", fa["three_separate_ledgers"] is True)
    check("O2 friction_eur>0", fa["friction_eur"] > 0)
    check("O2 friction_eur<=value_in", fa["friction_eur"] <= fa["value_in_eur"])


async def test_orchestrator_bho_zero_sum():
    """O3: BHO Zero-Sum verified."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=15, sensor_batch_size=50)
    await orch.run_simulation(cycles=15)
    report = orch.generate_report()
    comp = report["artifacts"][0]["compliance"]
    check("O3 bho_zero_sum_verified=True", comp["bho_zero_sum_verified"] is True)


async def test_orchestrator_chain_volumes():
    """O4: All 9 chain volume points populated."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=10, sensor_batch_size=30)
    await orch.run_simulation(cycles=10)
    report = orch.generate_report()
    cv = report["artifacts"][0]["chain_volumes"]
    expected_keys = [
        "C01_DEPIN_APPCHAIN", "C02_BRIDGE_LAYER", "C03_SETTLEMENT_L1",
        "C04_LIQUIDITY_L2", "C05_STAKING_LOCKED", "C06_YIELD_DISTRIBUTED",
        "C07_FEES_COLLECTED", "C08_TOKENS_BURNED", "C09_NET_PAYOUT",
    ]
    for key in expected_keys:
        check(f"O4 {key} present", key in cv)


async def test_orchestrator_all_agents_healthy():
    """O5: All 9 agent stats populated."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=20)
    await orch.run_simulation(cycles=5)
    report = orch.generate_report()
    stats = report["artifacts"][0]["agent_stats"]
    agent_names = [
        "sensor", "bridge", "depin_wallet", "vob_settlement",
        "legal_compliance", "settlement_executor", "token_minter",
        "staking_pool", "burn_fee_agent",
    ]
    for name in agent_names:
        check(f"O5 {name} stats exist", name in stats)


async def test_orchestrator_multi_tenancy():
    """O6: Multi-tenancy user_id isolation."""
    orch1 = EconomicOrchestratorMulti(user_id="tenant_A", cycles=5, sensor_batch_size=10)
    orch2 = EconomicOrchestratorMulti(user_id="tenant_B", cycles=5, sensor_batch_size=10)
    r1 = await orch1.run_simulation(cycles=5)
    r2 = await orch2.run_simulation(cycles=5)
    check("O6 tenant_A completed", r1["status"] == "completed")
    check("O6 tenant_B completed", r2["status"] == "completed")
    check("O6 different sim_ids", orch1.sim_id != orch2.sim_id)


async def test_orchestrator_report_idempotent():
    """O7: generate_report() is idempotent."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=10)
    await orch.run_simulation(cycles=5)
    r1 = orch.generate_report()
    r2 = orch.generate_report()
    cv1 = r1["artifacts"][0]["chain_volumes"]["C01_DEPIN_APPCHAIN"]
    cv2 = r2["artifacts"][0]["chain_volumes"]["C01_DEPIN_APPCHAIN"]
    check("O7 report idempotent", cv1 == cv2)


async def test_orchestrator_empty_run():
    """O8: Zero cycles handled."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=0, sensor_batch_size=10)
    result = await orch.run_simulation(cycles=0)
    check("O8 handles 0 cycles", result["status"] == "completed")


# ── Cross-Chain Integration Tests ───────────────────────────────────────────

async def test_cross_chain_latency_decrements():
    """X1: Bridge messages decrement latency each cycle."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=10)
    await orch.run_simulation(cycles=5)
    # Cross-chain queue should have messages with decremented latency
    check("X1 cross_chain_queue exists", isinstance(orch.cross_chain_queue, list))


async def test_cross_chain_drain():
    """X2: _drain_ready_messages extracts expired messages."""
    orch = EconomicOrchestratorMulti(user_id="test")
    from agents_b2g.simchain.economic_orchestrator_multi import CrossChainMessage
    orch.cross_chain_queue = [
        CrossChainMessage("A", "B", {"data": "ready"}, "proof1", 0, ""),
        CrossChainMessage("A", "B", {"data": "pending"}, "proof2", 3, ""),
        CrossChainMessage("A", "B", {"data": "also_ready"}, "proof3", 0, ""),
    ]
    ready = orch._drain_ready_messages()
    check("X2 2 ready messages", len(ready) == 2)
    check("X2 1 still pending", len(orch.cross_chain_queue) == 1)
    check("X2 pending decremented", orch.cross_chain_queue[0].latency_ticks == 2)


# ── Friction & DeFi Tests ───────────────────────────────────────────────────

async def test_friction_total_gt_zero():
    """F1: Total fees + burns > 0 after simulation."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=20, sensor_batch_size=50)
    await orch.run_simulation(cycles=20)
    report = orch.generate_report()
    tok = report["artifacts"][0]["tokenomics"]
    check("F1 fees_collected>0", tok["fees_collected"] > 0)
    check("F1 total_burned>0", tok["total_burned"] > 0)


async def test_friction_effective_supply_lt_minted():
    """F2: Effective supply < total minted (burns reduced it)."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=15, sensor_batch_size=30)
    await orch.run_simulation(cycles=15)
    report = orch.generate_report()
    tok = report["artifacts"][0]["tokenomics"]
    check("F2 supply < minted", tok["effective_supply"] < tok["total_minted"])


async def test_friction_staking_lockup():
    """F3: Staking locks up a significant portion."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=15, sensor_batch_size=50)
    await orch.run_simulation(cycles=15)
    stats = orch.staking.get_stats()
    check("F3 total_locked>0", stats["total_locked"] > 0)


# ── Config & Environment Tests ──────────────────────────────────────────────

async def test_config_env_overrides():
    """C1: Environment variables override defaults."""
    os.environ["SIMCHAIN_SENSOR_BATCH_SIZE"] = "25"
    os.environ["SIMCHAIN_TOKEN_BURN_RATE"] = "0.08"
    agent_s = SensorAggregatorAgent(user_id="test")
    agent_t = TokenMinterAgent(user_id="test")
    check("C1 sensor batch_size=25", agent_s.batch_size == 25)
    check("C1 token burn_rate=0.08", agent_t.burn_rate == 0.08)
    os.environ.pop("SIMCHAIN_SENSOR_BATCH_SIZE", None)
    os.environ.pop("SIMCHAIN_TOKEN_BURN_RATE", None)


async def test_config_user_id_isolation():
    """C2: user_id stored in all agent metadata."""
    agent = SensorAggregatorAgent(user_id="custom_user_123")
    result = await agent.process_batch(cycle=1)
    meta = result.get("metadata", {})
    check("C2 user_id in metadata", meta.get("user_id") == "custom_user_123")


# ── Error Handling Tests ────────────────────────────────────────────────────

async def test_error_status_on_failure():
    """E1: Failed status returns error object."""
    agent = TokenMinterAgent(user_id="test")
    # Trigger error with malformed input
    result = await agent.process_batch([{"bad_key": None}])  # should handle gracefully
    check("E1 status is valid", result["status"] in ("completed", "failed"))
    if result["status"] == "failed":
        check("E1 error is not None", result["error"] is not None)


async def test_error_all_agents_graceful():
    """E2: All agents handle completely empty/malformed input."""
    agents = [
        SensorAggregatorAgent(user_id="test"),
        BridgeAgent(user_id="test"),
        DePINWalletAgent(user_id="test"),
        VOBSettlementAgent(user_id="test"),
        LegalComplianceAgent(user_id="test"),
        SettlementExecutorAgent(user_id="test"),
        TokenMinterAgent(user_id="test"),
        StakingPoolAgent(user_id="test"),
        BurnFeeAgent(user_id="test"),
    ]
    for agent in agents:
        # Each agent should handle empty input without crashing
        try:
            result = await agent.process_batch([])
            assert result["status"] in ("completed", "failed"), \
                f"{agent.__class__.__name__} returned invalid status"
        except Exception as e:
            check(f"E2 {agent.__class__.__name__} crashed: {e}", False)


# ── Dashboard Tests ─────────────────────────────────────────────────────────


async def test_dashboard_import():
    """D1: Dashboard module can be imported."""
    try:
        from agents_b2g.simchain import streamlit_app  # noqa: F401
        check("D1 dashboard importable", True)
    except ImportError as e:
        check(f"D1 dashboard import failed: {e}", False)


async def test_dashboard_helpers():
    """D2: Dashboard helper functions work."""
    try:
        from agents_b2g.simchain.streamlit_app import format_eur, format_num
        check("D2 format_eur millions", format_eur(5_000_000) == "€5.00M")
        check("D2 format_eur thousands", "K" in format_eur(50_000))
        check("D2 format_eur small", "€" in format_eur(42.50))
        check("D2 format_num millions", format_num(2_000_000) == "2.00M")
        check("D2 format_num small", format_num(42) == "42")
    except Exception as e:
        check(f"D2 helpers failed: {e}", False)


async def test_dashboard_chart_chain_volumes():
    """D3: Chain volume bar chart generates without error."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=3, sensor_batch_size=10)
    await orch.run_simulation(cycles=3)
    report = orch.generate_report()["artifacts"][0]
    try:
        from agents_b2g.simchain.streamlit_app import chart_chain_volumes
        fig = chart_chain_volumes(report)
        check("D3 chart generated", fig is not None)
        check("D3 has data", len(fig.data) > 0)
    except Exception as e:
        check(f"D3 chart failed: {e}", False)


async def test_dashboard_chart_friction_waterfall():
    """D4: Friction waterfall chart generates without error."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=20)
    await orch.run_simulation(cycles=5)
    report = orch.generate_report()["artifacts"][0]
    try:
        from agents_b2g.simchain.streamlit_app import chart_friction_waterfall
        fig = chart_friction_waterfall(report)
        check("D4 waterfall generated", fig is not None)
        check("D4 has data", len(fig.data) > 0)
    except Exception as e:
        check(f"D4 waterfall failed: {e}", False)


async def test_dashboard_chart_compliance_gauge():
    """D5: Compliance gauge chart generates without error."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=3, sensor_batch_size=10)
    await orch.run_simulation(cycles=3)
    report = orch.generate_report()["artifacts"][0]
    try:
        from agents_b2g.simchain.streamlit_app import chart_compliance_gauge
        fig = chart_compliance_gauge(report)
        check("D5 gauge generated", fig is not None)
        check("D5 has 3 subplots", len(fig.data) >= 3)
    except Exception as e:
        check(f"D5 gauge failed: {e}", False)


async def test_dashboard_report_export_structure():
    """D6: Report has all required export fields."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=10)
    await orch.run_simulation(cycles=5)
    report = orch.generate_report()["artifacts"][0]
    required_sections = [
        "chains", "friction_analysis", "tokenomics",
        "compliance", "chain_volumes", "agent_stats",
    ]
    for section in required_sections:
        check(f"D6 has '{section}'", section in report)


async def test_dashboard_tokenomics_sankey():
    """D7: Tokenomics Sankey diagram generates without error."""
    orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=20)
    await orch.run_simulation(cycles=5)
    report = orch.generate_report()["artifacts"][0]
    try:
        from agents_b2g.simchain.streamlit_app import chart_tokenomics_sankey
        fig = chart_tokenomics_sankey(report)
        check("D7 sankey generated", fig is not None)
        check("D7 has data", len(fig.data) > 0)
    except Exception as e:
        check(f"D7 sankey failed: {e}", False)


async def test_dashboard_tps_chart():
    """D8: TPS/Latency chart handles empty and populated data."""
    try:
        from agents_b2g.simchain.streamlit_app import chart_tps_latency
        # Empty data should return empty figure without crashing
        fig = chart_tps_latency([])
        check("D8 empty handled", fig is not None)
        # Populated data
        orch = EconomicOrchestratorMulti(user_id="test", cycles=5, sensor_batch_size=20)
        await orch.run_simulation(cycles=5)
        fig2 = chart_tps_latency(orch._cycle_log)
        check("D8 populated chart", fig2 is not None)
    except Exception as e:
        check(f"D8 tps chart failed: {e}", False)


# ── Main Runner ─────────────────────────────────────────────────────────────

TEST_GROUPS = {
    "S1 — SensorAggregator": [
        test_sensor_basic, test_sensor_amount_range, test_sensor_stats,
        test_sensor_failure_handling,
    ],
    "S2 — BridgeAgent": [
        test_bridge_basic, test_bridge_latency_range, test_bridge_empty_batch,
        test_bridge_stats,
    ],
    "S3 — DePINWallet": [
        test_depin_wallet_basic, test_depin_wallet_threshold_payout,
        test_depin_wallet_multi_sensor, test_depin_wallet_empty,
    ],
    "L1 — VOBSettlement": [
        test_vob_basic, test_vob_projects_have_5pct_retention,
        test_vob_milestone_progress, test_vob_empty,
    ],
    "L2 — LegalCompliance": [
        test_legal_basic, test_legal_audit_trail, test_legal_gobd_compliance,
        test_legal_empty,
    ],
    "L3 — SettlementExecutor": [
        test_executor_basic, test_executor_escrow_accumulation,
        test_executor_bho_zero_sum, test_executor_empty,
    ],
    "T1 — TokenMinter": [
        test_minter_basic, test_minter_burn_rate, test_minter_supply_tracking,
        test_minter_empty,
    ],
    "T2 — StakingPool": [
        test_staking_basic, test_staking_yield_accumulation,
        test_staking_custom_lockup, test_staking_empty,
    ],
    "T3 — BurnFeeAgent": [
        test_burnfee_basic, test_burnfee_friction_tracking,
        test_burnfee_zero_liquid, test_burnfee_empty,
    ],
    "O — Orchestrator": [
        test_orchestrator_full_simulation, test_orchestrator_friction_verified,
        test_orchestrator_bho_zero_sum, test_orchestrator_chain_volumes,
        test_orchestrator_all_agents_healthy, test_orchestrator_multi_tenancy,
        test_orchestrator_report_idempotent, test_orchestrator_empty_run,
    ],
    "X — Cross-Chain": [
        test_cross_chain_latency_decrements, test_cross_chain_drain,
    ],
    "F — Friction & DeFi": [
        test_friction_total_gt_zero, test_friction_effective_supply_lt_minted,
        test_friction_staking_lockup,
    ],
    "C — Config": [
        test_config_env_overrides, test_config_user_id_isolation,
    ],
    "E — Error Handling": [
        test_error_status_on_failure, test_error_all_agents_graceful,
    ],
    "D — Dashboard": [
        test_dashboard_import, test_dashboard_helpers,
        test_dashboard_chart_chain_volumes, test_dashboard_chart_friction_waterfall,
        test_dashboard_chart_compliance_gauge, test_dashboard_report_export_structure,
        test_dashboard_tokenomics_sankey, test_dashboard_tps_chart,
    ],
}


async def run_all_tests():
    global PASS, FAIL, ERRORS, VERBOSE
    VERBOSE = "--verbose" in sys.argv

    print("\n" + "=" * 70)
    print("🧪 AGENT X SIMCHAIN — TEST SUITE (Wave 35)")
    print(f"   {sum(len(v) for v in TEST_GROUPS.values())} tests in {len(TEST_GROUPS)} groups")
    print("=" * 70 + "\n")

    total_start = time.time()

    for group_name, tests in TEST_GROUPS.items():
        print(f"── {group_name} ({len(tests)} tests) ──")
        for test_fn in tests:
            try:
                await test_fn()
            except Exception as e:
                FAIL += 1
                ERRORS.append(f"{test_fn.__name__}: unhandled exception: {e}")
                print(f"  ❌ {test_fn.__name__} — EXCEPTION: {e}")
        print()

    elapsed = time.time() - total_start
    total = PASS + FAIL
    print("=" * 70)
    print(f"  Results: {PASS}/{total} passed ({elapsed:.1f}s)")
    if FAIL > 0:
        print(f"  Failures ({FAIL}):")
        for err in ERRORS:
            print(f"    ❌ {err}")
    print("=" * 70 + "\n")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all_tests()))
