#!/usr/bin/env python3
"""Agent X MultiChain — Test Suite (Wave 36).

Tests: 9 sovereign appchains, 4 chain layers, bridge protocol,
cross-chain messaging, Merkle proofs, identity verification.

Usage: python3 scripts/test_multichain.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.multichain import ChainOrchestrator, BridgeProtocol
from agents_b2g.multichain.subchains.sensor_aggregator import SensorAggregatorChain
from agents_b2g.multichain.subchains.bridge_relayer import BridgeRelayerChain
from agents_b2g.multichain.subchains.depin_wallet import DePINWalletChain
from agents_b2g.multichain.subchains.vob_settlement import VOBSettlementChain
from agents_b2g.multichain.subchains.legal_compliance import LegalComplianceChain
from agents_b2g.multichain.subchains.settlement_executor import SettlementExecutorChain
from agents_b2g.multichain.subchains.token_minter import TokenMinterChain
from agents_b2g.multichain.subchains.staking_pool import StakingPoolChain
from agents_b2g.multichain.subchains.identity_compliance import IdentityComplianceChain

PASS = 0
FAIL = 0
ERRS = []

def check(name, cond, detail=""):
    global PASS, FAIL, ERRS
    if cond: PASS += 1; print(f"  ✅ {name}")
    else: FAIL += 1; ERRS.append(f"{name}: {detail}"); print(f"  ❌ {name}")

def std(result, label=""):
    for k in ["status","job_id","artifacts","error","logs"]:
        check(f"{label} has {k}" if label else f"has {k}", k in result)
    check(f"{label} status valid", result.get("status") in ("started","completed","failed","skipped"))

# ── A1: SensorAggregatorChain ───────────────────────────────────────────────

async def test_a1_basic():
    c = SensorAggregatorChain(batch_size=100)
    r = await c.process_block(1)
    std(r, "A1")
    a = r["artifacts"][0]
    check("A1 block_height=1", c.block_height == 1)
    check("A1 batch_size=100", a["event_count"] == 100)
    check("A1 has state_root", len(a["state_root"]) == 64)
    check("A1 has transactions", len(a["transactions"]) == 100)

async def test_a1_amount_range():
    c = SensorAggregatorChain(batch_size=200)
    r = await c.process_block(1)
    txs = r["artifacts"][0]["transactions"]
    amts = [t["amount"] for t in txs]
    check("A1.2 min>=0.001", min(amts) >= 0.001)
    check("A1.2 max<=0.50", max(amts) <= 0.50)

async def test_a1_state_root_changes():
    c = SensorAggregatorChain(batch_size=10)
    r1 = await c.process_block(1)
    r2 = await c.process_block(2)
    check("A1.3 roots differ", r1["artifacts"][0]["state_root"] != r2["artifacts"][0]["state_root"])

# ── A2: BridgeRelayerChain ──────────────────────────────────────────────────

async def test_a2_basic():
    c = BridgeRelayerChain()
    txs = [{"amount": 0.1}] * 10
    r = await c.relay("DEPIN", "SETTLEMENT", txs, "0xabc")
    std(r, "A2")
    a = r["artifacts"][0]
    check("A2 merkle_root set", len(a["merkle_root"]) == 64)
    check("A2 batch_size=10", a["batch_size"] == 10)
    check("A2 latency in range", 100 <= a["latency_ms"] <= 500)

async def test_a2_empty():
    c = BridgeRelayerChain()
    r = await c.relay("A", "B", [], "0x0")
    check("A2.2 handles empty", r["status"] == "completed")

# ── A3: DePINWalletChain ────────────────────────────────────────────────────

async def test_a3_basic():
    c = DePINWalletChain(payout_threshold=5.0)
    txs = [{"sensor_id": f"S_{i}", "amount": 0.1} for i in range(30)]
    r = await c.process_block(txs)
    std(r, "A3")
    check("A3 wallets_updated>0", r["artifacts"][0]["wallets_updated"] > 0)

async def test_a3_threshold():
    c = DePINWalletChain(payout_threshold=1.0)
    txs = [{"sensor_id": "S_1", "amount": 0.6}] * 5
    await c.process_block(txs)
    s = c.get_chain_state()
    check("A3.2 total_payouts>0", s["total_payouts"] > 0)

# ── A4: VOBSettlementChain ──────────────────────────────────────────────────

async def test_a4_basic():
    c = VOBSettlementChain()
    msgs = [{"payload": {"amount": 1000.0}} for _ in range(5)]
    r = await c.process_block(msgs)
    std(r, "A4")
    check("A4 has settlements", len(r["artifacts"][0]["settlements"]) > 0)
    check("A4 has Z3 proofs", all("z3_proof" in s for s in r["artifacts"][0]["settlements"]))

async def test_a4_empty():
    c = VOBSettlementChain()
    r = await c.process_block([])
    check("A4.2 handles empty", r["status"] == "completed")

# ── A5: LegalComplianceChain ────────────────────────────────────────────────

async def test_a5_basic():
    c = LegalComplianceChain(tax_rate=0.19, withholding_rate=0.15)
    s = [{"project_id": "P1", "amount": 1000.0}]
    r = await c.process_block(s)
    std(r, "A5")
    tx = r["artifacts"][0]["transactions"][0]
    check("A5 tax=190", abs(tx["tax"] - 190.0) < 0.01)
    check("A5 withholding=150", abs(tx["withholding_tax"] - 150.0) < 0.01)
    check("A5 net=660", abs(tx["net"] - 660.0) < 0.01)

async def test_a5_audit_trail():
    c = LegalComplianceChain()
    await c.process_block([{"project_id": "P1", "amount": 500.0}] * 10)
    s = c.get_chain_state()
    check("A5.2 audit_entries=10", s["audit_entries"] == 10)

# ── A6: SettlementExecutorChain ─────────────────────────────────────────────

async def test_a6_basic():
    c = SettlementExecutorChain()
    txs = [{"project_id": "P1", "amount": 1000.0, "tax": 150.0, "withholding_tax": 0.0}]
    r = await c.process_block(txs)
    std(r, "A6")
    s = r["artifacts"][0]["settlements"][0]
    check("A6 BHO Δ=0", s["bho_delta"] == 0.0)

async def test_a6_escrow():
    c = SettlementExecutorChain()
    txs = [{"project_id": "P1", "amount": 1000.0, "tax": 150.0}] * 5
    await c.process_block(txs)
    st = c.get_chain_state()
    check("A6.2 escrow>0", st["escrow_balance"] > 0)

# ── A7: TokenMinterChain ────────────────────────────────────────────────────

async def test_a7_basic():
    c = TokenMinterChain(burn_rate=0.05)
    s = [{"project_id": "P1", "net": 1000.0}]
    r = await c.process_block(s)
    std(r, "A7")
    t = r["artifacts"][0]["tokens"][0]
    check("A7 burn=50", abs(t["burn_amount"] - 50.0) < 0.01)
    check("A7 net=950", abs(t["net_tokens"] - 950.0) < 0.01)

async def test_a7_supply():
    c = TokenMinterChain(burn_rate=0.05)
    await c.process_block([{"project_id": f"P{i}", "net": 100.0} for i in range(10)])
    s = c.get_chain_state()
    check("A7.2 effective_supply=950", abs(s["effective_supply"] - 950.0) < 0.01)

# ── A8: StakingPoolChain ────────────────────────────────────────────────────

async def test_a8_basic():
    c = StakingPoolChain(apy=0.12, lockup_ratio=0.80)
    tokens = [{"token_id": "T1", "net_tokens": 1000.0}]
    r = await c.process_block(tokens)
    std(r, "A8")
    p = r["artifacts"][0]["positions"][0]
    check("A8 locked=800", abs(p["locked_amount"] - 800.0) < 0.01)
    check("A8 liquid=200", abs(p["liquid_amount"] - 200.0) < 0.01)
    check("A8 yield=8", abs(p["yield_earned"] - 8.0) < 0.01)

async def test_a8_tracks_liquid():
    c = StakingPoolChain()
    await c.process_block([{"token_id": "T1", "net_tokens": 1000.0}])
    s = c.get_chain_state()
    check("A8.2 total_liquid>0", s["total_liquid"] > 0)

# ── A9: IdentityComplianceChain ─────────────────────────────────────────────

async def test_a9_basic():
    c = IdentityComplianceChain(verification_success_rate=1.0)
    r = await c.verify_credentials(1)
    std(r, "A9")
    check("A9 valid=True", r["artifacts"][0]["valid"] is True)
    check("A9 has zk_proof", len(r["artifacts"][0].get("zk_proof", "")) > 0)

async def test_a9_always_fails():
    c = IdentityComplianceChain(verification_success_rate=0.0)
    r = await c.verify_credentials(1)
    check("A9.2 valid=False", r["artifacts"][0]["valid"] is False)

async def test_a9_credential_lifecycle():
    c = IdentityComplianceChain()
    c.issue_credential("did:test:1", {"role": "contractor"})
    check("A9.3 credential exists", "did:test:1" in c.credentials)
    c.revoke_credential("did:test:1")
    check("A9.3 credential revoked", "did:test:1" not in c.credentials)

# ── BridgeProtocol ──────────────────────────────────────────────────────────

def test_bridge_merkle():
    bp = BridgeProtocol()
    txs = [{"id": i, "val": i * 10} for i in range(10)]
    proof = bp.create_proof(txs)
    check("B1 merkle_root set", len(proof.merkle_root) == 64)
    check("B1 batch_size=10", proof.batch_size == 10)
    check("B1 verify single tx", bp.verify_proof(proof, txs[0]))
    check("B1 verify batch", bp.batch_verify(proof, txs)["all_verified"])

def test_bridge_empty():
    bp = BridgeProtocol()
    proof = bp.create_proof([])
    check("B2 empty root=0x0", proof.merkle_root == "0x0")

def test_bridge_tamper_detection():
    bp = BridgeProtocol()
    txs = [{"id": 1}, {"id": 2}]
    proof = bp.create_proof(txs)
    tampered = {"id": 999}
    check("B3 tamper detected", not bp.verify_proof(proof, tampered))

# ── Orchestrator ────────────────────────────────────────────────────────────

async def test_orch_full():
    orch = ChainOrchestrator(user_id="test", cycles=10, sensor_batch=50)
    r = await orch.run_simulation(cycles=10)
    check("O1 completed", r["status"] == "completed")
    check("O1 has 4 layers", len(r["artifacts"][0]["layers"]) == 4)
    check("O1 has 9 chain states", len(r["artifacts"][0]["chain_states"]) == 9)

async def test_orch_friction():
    orch = ChainOrchestrator(user_id="test", cycles=20, sensor_batch=100)
    await orch.run_simulation(cycles=20)
    r = orch.generate_report()["artifacts"][0]
    fa = r["friction_analysis"]
    check("O2 friction_verified", fa["friction_verified"])
    check("O2 value_conserved", fa["value_conserved"])

async def test_orch_bho():
    orch = ChainOrchestrator(user_id="test", cycles=15, sensor_batch=50)
    await orch.run_simulation(cycles=15)
    r = orch.generate_report()["artifacts"][0]
    c = r["compliance"]
    check("O3 bho_verified", c["bho_zero_sum_verified"])

async def test_orch_multi_tenancy():
    o1 = ChainOrchestrator(user_id="tenant_A", cycles=5, sensor_batch=10)
    o2 = ChainOrchestrator(user_id="tenant_B", cycles=5, sensor_batch=10)
    await o1.run_simulation(cycles=5)
    await o2.run_simulation(cycles=5)
    check("O4 different sim_ids", o1.sim_id != o2.sim_id)

async def test_orch_empty():
    orch = ChainOrchestrator(cycles=0, sensor_batch=10)
    r = await orch.run_simulation(cycles=0)
    check("O5 handles 0 cycles", r["status"] == "completed")

async def test_orch_identity_integration():
    orch = ChainOrchestrator(user_id="test", cycles=10, sensor_batch=20)
    await orch.run_simulation(cycles=10)
    r = orch.generate_report()["artifacts"][0]
    c = r["compliance"]
    check("O6 identity_verifications>0", c["identity_verifications"] > 0)
    check("O6 identity_pass_rate>0", c["identity_pass_rate"] > 0)

async def test_orch_chain_volumes_9point():
    orch = ChainOrchestrator(user_id="test", cycles=10, sensor_batch=30)
    await orch.run_simulation(cycles=10)
    r = orch.generate_report()["artifacts"][0]
    cv = r["chain_volumes"]
    for k in ["C01","C02","C03","C04","C05","C06","C07","C08","C09"]:
        check(f"O7 {k} present", any(kk.startswith(k) for kk in cv))

# ── Runner ──────────────────────────────────────────────────────────────────

GROUPS = {
    "A1 Sensor": [test_a1_basic, test_a1_amount_range, test_a1_state_root_changes],
    "A2 Bridge": [test_a2_basic, test_a2_empty],
    "A3 Wallet": [test_a3_basic, test_a3_threshold],
    "A4 VOB": [test_a4_basic, test_a4_empty],
    "A5 Legal": [test_a5_basic, test_a5_audit_trail],
    "A6 Executor": [test_a6_basic, test_a6_escrow],
    "A7 Token": [test_a7_basic, test_a7_supply],
    "A8 Staking": [test_a8_basic, test_a8_tracks_liquid],
    "A9 Identity": [test_a9_basic, test_a9_always_fails, test_a9_credential_lifecycle],
    "B BridgeProto": [test_bridge_merkle, test_bridge_empty, test_bridge_tamper_detection],
    "O Orchestrator": [
        test_orch_full, test_orch_friction, test_orch_bho,
        test_orch_multi_tenancy, test_orch_empty,
        test_orch_identity_integration, test_orch_chain_volumes_9point,
    ],
}

async def run():
    global PASS, FAIL
    print(f"\n{'='*70}")
    print(f"🧪 AGENT X MULTICHAIN — TEST SUITE (Wave 36)")
    print(f"   {sum(len(v) for v in GROUPS.values())} tests in {len(GROUPS)} groups")
    print(f"{'='*70}\n")
    t0 = time.time()
    for g, tests in GROUPS.items():
        print(f"── {g} ({len(tests)}) ──")
        for fn in tests:
            try:
                if asyncio.iscoroutinefunction(fn):
                    await fn()
                else:
                    fn()
            except Exception as e:
                FAIL += 1
                ERRS.append(f"{fn.__name__}: {e}")
                print(f"  ❌ {fn.__name__} EXCEPTION: {e}")
        print()
    t = time.time() - t0
    total = PASS + FAIL
    print(f"{'='*70}")
    print(f"  Results: {PASS}/{total} passed ({t:.1f}s)")
    if FAIL:
        print(f"  Failures ({FAIL}):")
        for e in ERRS: print(f"    ❌ {e}")
    print(f"{'='*70}\n")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
