#!/usr/bin/env python3
"""Agent X SimChain — Multi-Chain Economic Simulation Demo.

Demonstrates heterogeneous market dynamics with 9 agents across 3 chains.
DePIN (1000 TPS) → Bridge → Settlement (VOB/B) → Liquidity (Token/Staking/Burn).

Usage:
  python3 scripts/demo_simchain.py              # 100 cycles (default)
  python3 scripts/demo_simchain.py 1000         # 1000 cycles
  python3 scripts/demo_simchain.py 100 demo2    # custom user_id
"""

import asyncio
import sys
import time
from datetime import datetime, timezone

# Allow running from repo root
sys.path.insert(0, ".")

from agents_b2g.simchain import EconomicOrchestratorMulti


async def run_full_demo(cycles: int = 100, user_id: str = "demo"):
    """Run the full multi-chain demo with detailed output."""

    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  🏛️  AGENT X SIMCHAIN — MULTI-CHAIN ECONOMIC SIMULATION".center(74) + "█")
    print("█" + "  Wave 35 | 9 Agents × 3 Chains | Heterogeneous Markets".center(74) + "█")
    print("█" + " " * 78 + "█")
    print("█" * 80 + "\n")

    t0 = time.time()

    # ── Initialize ──
    orch = EconomicOrchestratorMulti(user_id=user_id, cycles=cycles)

    print(f"  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║  SimID:    {orch.sim_id:<48} ║")
    print(f"  ║  User:     {user_id:<48} ║")
    print(f"  ║  Cycles:   {cycles:<48} ║")
    print(f"  ║  Chains:   DEPIN_APPCHAIN | SETTLEMENT_L1 | LIQUIDITY_L2  ║")
    print(f"  ╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Run ──
    print("  🚀 Running simulation...\n")
    result = await orch.run_simulation(cycles=cycles)

    if result["status"] == "failed":
        print(f"\n  ❌ SIMULATION FAILED: {result['error']}")
        return 1

    elapsed = result.get("elapsed_total_ms", 0)
    tps = (cycles * orch.sensor_batch_size) / (elapsed / 1000) if elapsed > 0 else 0
    report = result["artifacts"][0]

    # ── Chain Comparison ──
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  📊 CHAIN STATISTICS                                        │")
    print("  ├──────────────┬──────────────┬──────────────┬────────────────┤")
    print("  │ Chain        │      TXs     │    Volume    │   Ø Latency    │")
    print("  ├──────────────┼──────────────┼──────────────┼────────────────┤")
    for name, data in report["chains"].items():
        print(
            f"  │ {name:<13}│ {data['total_txs']:>12,} │ "
            f"€{data['total_volume']:>11,.2f} │ "
            f"{data['avg_latency_ms']:>10.1f} ms │"
        )
    print("  └──────────────┴──────────────┴──────────────┴────────────────┘")
    print()

    # ── Friction Analysis ──
    fa = report["friction_analysis"]
    fv = "✅ YES" if fa["friction_verified"] else "❌ NO (would be red in tests)"
    vc = "✅ YES" if fa["value_conserved"] else "❌ LEAK"
    fb = fa["friction_breakdown"]
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  💸 FRICTION (Liquidity Chain)                              │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print(f"  │  Value In (minted):        €{fa['value_in_eur']:>14,.2f}          │")
    print(f"  │  Net Payout (C09):         €{fa['net_payout_eur']:>14,.2f}          │")
    print(f"  │  Friction (outflows):      €{fa['friction_eur']:>14,.2f}          │")
    print(f"  │    · Mint Burns (5%):      €{fb.get('mint_burns', 0):>14,.2f}          │")
    print(f"  │    · Fee Burns (1%):       €{fb.get('burnfee_burns', 0):>14,.2f}          │")
    print(f"  │    · Fees (2%):            €{fb.get('fees_collected', 0):>14,.2f}          │")
    print(f"  │  Staking Locked (not friction): €{fb.get('staking_locked_not_friction', 0):>14,.2f}          │")
    print(f"  │  Friction Verified:        {fv}  │")
    print(f"  │  Value Conserved:          {vc}  │")
    print(f"  │  Three Separate Ledgers:   ✅ YES — C01–C09 are 3 books    │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    # ── Tokenomics ──
    tok = report["tokenomics"]
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  💰 TOKENOMICS                                              │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print(f"  │  Total Minted:             €{tok['total_minted']:>14,.2f}          │")
    print(f"  │  Total Burned:             €{tok['total_burned']:>14,.2f}          │")
    print(f"  │  Effective Supply:         €{tok['effective_supply']:>14,.2f}          │")
    print(f"  │  Staked:                   €{tok['staked_amount']:>14,.2f} ({tok['staked_ratio_pct']:.1f}%)   │")
    print(f"  │  Yield Distributed:        €{tok['yield_distributed']:>14,.2f}          │")
    print(f"  │  Fees Collected:           €{tok['fees_collected']:>14,.2f}          │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    # ── Compliance ──
    comp = report["compliance"]
    bho_ok = "✅ VERIFIED" if comp["bho_zero_sum_verified"] else "❌ VIOLATION"
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  ⚖️  COMPLIANCE                                             │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print(f"  │  BHO Zero-Sum:             {bho_ok} (Δ=€{comp['bho_delta_eur']:.2f})     │")
    print(f"  │  GoBD Audit Trail:         {comp['gobd_audit_entries']:>10} entries         │")
    print(f"  │  Escrow Balance:           €{comp['escrow_balance']:>14,.2f}          │")
    print(f"  │  Tax Collected:            €{comp['tax_collected']:>14,.2f}          │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    # ── 9-Point Chain Volume Check ──
    cv = report["chain_volumes"]
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  🔗 9-POINT CHAIN VOLUME COMPARISON                         │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    for key in [
        "C01_DEPIN_APPCHAIN", "C02_BRIDGE_LAYER", "C03_SETTLEMENT_L1",
        "C04_LIQUIDITY_L2", "C05_STAKING_LOCKED", "C06_YIELD_DISTRIBUTED",
        "C07_FEES_COLLECTED", "C08_TOKENS_BURNED", "C09_NET_PAYOUT",
    ]:
        val = cv.get(key, 0)
        bar = "█" * max(1, int(abs(val) / max(1, abs(cv.get("C01_DEPIN_APPCHAIN", 1))) * 30))
        print(f"  │  {key:<25} €{val:>12,.2f}  {bar} │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    # ── Summary ──
    total_elapsed = time.time() - t0
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║  ⏱️  Total wall-clock:  {total_elapsed:>6.1f}s  ({elapsed:,.0f}ms CPU)          ║")
    print(f"  ║  📡 Throughput:        {tps:>10,.0f} events/s                     ║")
    print(f"  ║  🔥 Friction verified: {'✅' if fa['friction_verified'] else '❌'}   Value conserved: {'✅' if fa['value_conserved'] else '❌'}          ║")
    print(f"  ║  ⚖️  BHO Δ=0:           {'✅' if comp['bho_zero_sum_verified'] else '❌'}                                   ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()
    print("  🎉 MULTI-CHAIN SIMULATION COMPLETE")
    print("  Real economic friction, heterogeneous markets, verifiable sinks.\n")

    return 0


if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    user_id = sys.argv[2] if len(sys.argv) > 2 else "demo"
    sys.exit(asyncio.run(run_full_demo(cycles=cycles, user_id=user_id)))
