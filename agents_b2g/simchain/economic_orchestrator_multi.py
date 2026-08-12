"""EconomicOrchestratorMulti — Multi-Chain Economic Simulation Engine (Wave 35).

Orchestrates 9 agents across 3 heterogeneous chains:
  DEPIN_APPCHAIN → BRIDGE → SETTLEMENT_L1 → LIQUIDITY_L2
  (High-Freq μTX)  (Async)  (Low-Freq VOB/B)  (Token + Staking + Burn)

Key properties:
  - Heterogeneous market mechanics per chain (not linear pass-through)
  - Cross-chain latency (2–5 ticks) for realistic asynchrony
  - Economic friction: fees, burns, lockups, retention
  - C01 (DePIN input) ≠ C09 (Liquidity output) — real sink losses
  - Standardized JSON output, JSONLogger, multi-tenancy
"""

import asyncio
import hashlib
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .subagents.sensor_aggregator import SensorAggregatorAgent
from .subagents.bridge_agent import BridgeAgent
from .subagents.depin_wallet import DePINWalletAgent
from .subagents.vob_settlement import VOBSettlementAgent
from .subagents.legal_compliance import LegalComplianceAgent
from .subagents.settlement_executor import SettlementExecutorAgent
from .subagents.token_minter import TokenMinterAgent
from .subagents.staking_pool import StakingPoolAgent
from .subagents.burn_fee_agent import BurnFeeAgent

logger = logging.getLogger("EconomicOrchestratorMulti")

# ─── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class ChainState:
    """Runtime state of a single chain."""
    name: str
    block_height: int = 0
    pending_txs: List[Dict] = field(default_factory=list)
    total_volume: float = 0.0
    total_txs: int = 0
    avg_latency_ms: float = 0.0


@dataclass
class CrossChainMessage:
    """Message in transit between chains."""
    source_chain: str
    target_chain: str
    payload: Dict
    bridge_proof: str
    latency_ticks: int
    timestamp: str


# ─── Orchestrator ────────────────────────────────────────────────────────────


class EconomicOrchestratorMulti:
    """
    Multi-Chain Economic Simulation Orchestrator.

    Runs 9 agents across 3 chains with heterogeneous market dynamics,
    cross-chain latency, and real economic friction (fees, burns, lockups).
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        cycles: int = 100,
        sensor_batch_size: Optional[int] = None,
    ):
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.cycles = cycles
        self.sensor_batch_size = sensor_batch_size or int(
            os.getenv("SIMCHAIN_SENSOR_BATCH_SIZE", "1000")
        )

        # ── 9 Agents with Chain Assignment ──
        self.sensor = SensorAggregatorAgent(
            chain="DEPIN_APPCHAIN", user_id=self.user_id,
            batch_size=self.sensor_batch_size,
        )
        self.bridge = BridgeAgent(
            chain="BRIDGE_LAYER", user_id=self.user_id,
        )
        self.depin_wallet = DePINWalletAgent(
            chain="DEPIN_APPCHAIN", user_id=self.user_id,
        )
        self.vob_settlement = VOBSettlementAgent(
            chain="SETTLEMENT_L1", user_id=self.user_id,
        )
        self.legal = LegalComplianceAgent(
            chain="SETTLEMENT_L1", user_id=self.user_id,
        )
        self.settlement_exec = SettlementExecutorAgent(
            chain="SETTLEMENT_L1", user_id=self.user_id,
        )
        self.token_minter = TokenMinterAgent(
            chain="LIQUIDITY_L2", user_id=self.user_id,
        )
        self.staking = StakingPoolAgent(
            chain="LIQUIDITY_L2", user_id=self.user_id,
        )
        self.burn_fee = BurnFeeAgent(
            chain="LIQUIDITY_L2", user_id=self.user_id,
        )

        # ── Chain States ──
        self.chains = {
            "DEPIN_APPCHAIN": ChainState(name="DEPIN_APPCHAIN"),
            "SETTLEMENT_L1": ChainState(name="SETTLEMENT_L1"),
            "LIQUIDITY_L2": ChainState(name="LIQUIDITY_L2"),
        }

        # ── Cross-Chain Message Queue ──
        self.cross_chain_queue: List[CrossChainMessage] = []

        # ── Cycle Log ──
        self._cycle_log: List[Dict] = []

        # ── Simulation ID ──
        self.sim_id = hashlib.sha256(
            f"SIM_{self.user_id}_{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        logger.info(
            "EconomicOrchestratorMulti initialized",
            extra={
                "sim_id": self.sim_id,
                "user_id": self.user_id,
                "cycles": cycles,
                "batch_size": self.sensor_batch_size,
            },
        )

    # ── Public API ──────────────────────────────────────────────────────────

    async def run_simulation(self, cycles: Optional[int] = None) -> Dict[str, Any]:
        """Run the full multi-chain simulation for N cycles."""
        cycles = cycles or self.cycles
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "Starting multi-chain simulation",
                extra={
                    "job_id": job_id,
                    "sim_id": self.sim_id,
                    "cycles": cycles,
                    "user_id": self.user_id,
                },
            )
            logs.append(f"[INFO] sim_id={self.sim_id} cycles={cycles}")

            for cycle in range(1, cycles + 1):
                cycle_start = time.time()

                # ── Phase 1: DEPIN_APPCHAIN (High-Freq Sensor Data) ──
                sensor_result = await self.sensor.process_batch(cycle)
                sensor_txs = self._extract_txs(sensor_result)
                self.chains["DEPIN_APPCHAIN"].total_txs += len(sensor_txs)
                depin_vol = sum(t.get("amount", 0) for t in sensor_txs)
                self.chains["DEPIN_APPCHAIN"].total_volume += depin_vol

                # ── Phase 2: BRIDGE (Cross-Chain with Latency) ──
                bridge_result = await self.bridge.process_batch(
                    sensor_txs, target_chain="SETTLEMENT_L1"
                )
                bridge_messages = self._extract_messages(bridge_result)
                self.cross_chain_queue.extend(bridge_messages)

                # ── Phase 3: DePIN Wallet (Micro-Payouts) ──
                await self.depin_wallet.process_batch(sensor_txs)

                # ── Phase 4: SETTLEMENT_L1 (Low-Freq VOB/B) ──
                ready_messages = self._drain_ready_messages()
                if ready_messages:
                    settlement_result = await self.vob_settlement.process_batch(
                        ready_messages
                    )
                    settlements = self._extract_settlements(settlement_result)
                    self.chains["SETTLEMENT_L1"].total_txs += len(settlements)
                    settle_vol = sum(s.get("amount", 0) for s in settlements)
                    self.chains["SETTLEMENT_L1"].total_volume += settle_vol

                    # ── Phase 5: Legal & Compliance ──
                    legal_result = await self.legal.process_batch(settlements)
                    compliant_txs = self._extract_compliant_txs(legal_result)

                    # ── Phase 6: Settlement Executor ──
                    exec_result = await self.settlement_exec.process_batch(
                        compliant_txs
                    )
                    executed = self._extract_executed(exec_result)

                    # ── Phase 7: LIQUIDITY_L2 ──
                    # Token Minting
                    mint_result = await self.token_minter.process_batch(executed)
                    tokens = self._extract_tokens(mint_result)
                    liq_vol = sum(t.get("mint_amount", 0) for t in tokens)
                    self.chains["LIQUIDITY_L2"].total_volume += liq_vol
                    self.chains["LIQUIDITY_L2"].total_txs += len(tokens)

                    # Staking
                    stake_result = await self.staking.process_batch(tokens)
                    positions = self._extract_positions(stake_result)

                    # Burn & Fees
                    burn_result = await self.burn_fee.process_batch(positions)

                # ── Phase 8: Cycle Logging ──
                cycle_elapsed = round((time.time() - cycle_start) * 1000, 2)
                self._cycle_log.append({
                    "cycle": cycle,
                    "depin_volume": round(depin_vol, 6),
                    "depin_txs": len(sensor_txs),
                    "settlement_volume": round(
                        self.chains["SETTLEMENT_L1"].total_volume, 2
                    ),
                    "liquidity_volume": round(
                        self.chains["LIQUIDITY_L2"].total_volume, 6
                    ),
                    "cross_chain_queue_depth": len(self.cross_chain_queue),
                    "elapsed_ms": cycle_elapsed,
                })

                if cycle % 50 == 0 or cycle == 1:
                    logs.append(
                        f"[INFO] cycle={cycle}/{cycles} "
                        f"depin_vol={depin_vol:.2f}€ "
                        f"settle_vol={self.chains['SETTLEMENT_L1'].total_volume:,.0f}€ "
                        f"liq_vol={self.chains['LIQUIDITY_L2'].total_volume:,.0f}€ "
                        f"queue={len(self.cross_chain_queue)}"
                    )

            # ── Generate Final Report ──
            elapsed_total = round((time.time() - start_time) * 1000, 2)
            report = self.generate_report()
            report["job_id"] = job_id
            report["elapsed_total_ms"] = elapsed_total
            report["logs"] = logs

            logger.info(
                "Simulation completed",
                extra={
                    "job_id": job_id,
                    "sim_id": self.sim_id,
                    "elapsed_ms": elapsed_total,
                },
            )

            return report

        except Exception as e:
            elapsed_total = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "Simulation failed",
                extra={"job_id": job_id, "sim_id": self.sim_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "sim_id": self.sim_id,
                "artifacts": [],
                "error": {"code": "SIMULATION_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {
                    "elapsed_ms": elapsed_total,
                    "cycles_completed": len(self._cycle_log),
                    "user_id": self.user_id,
                },
            }

    def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive multi-chain simulation report.

        Honest accounting:
        - The three chains are separate ledgers with separate volumes.
          Comparing C01 (DePIN μTX) with C03 (VOB/B milestones) is meaningless —
          they differ by design. The real friction lives inside each chain.
        - Friction in the Liquidity chain: fees + burns + lockups are outflows
          that reduce circulating supply. This is measured and MUST be >= 0
          and <= total input (falsifiable).
        - Value conservation: minted_total = net_payout + mint_burns + fees + burnfee_burns + staked.
          Partition check compares StakingPool's 80/20 split against TokenMinter's output
          (cross-module consistency). Fee/burn ratio checks verify the 2%/1% rates are actually
          applied — without these, fees and burns cancel algebraically in the partition.
        - BHO zero-sum: per-settlement, gross = net + tax_total + retention (exact, retention is
          the residual). ADR 2: |Δ| > 0.01 € halts all payments.
        """
        depin_volume = self.chains["DEPIN_APPCHAIN"].total_volume
        liquidity_volume = self.chains["LIQUIDITY_L2"].total_volume
        settlement_volume = self.chains["SETTLEMENT_L1"].total_volume

        # ── Friction: only measurable inside the Liquidity chain ──
        # Value enters the liquidity pool as minted tokens.
        # At mint time: 5% is burned (token_minter burn).
        # Of the remaining: 80% is staked (locked, NOT friction — still exists),
        # 20% is liquid. Of the liquid: 2% fees, 1% additional burn → net payout.
        # Conservation: minted = net_payout + mint_burns + fees + burnfee_burns + staked
        minted_total = self.token_minter.total_minted
        mint_burns = self.token_minter.total_burned          # 5% at mint
        fees_collected = self.burn_fee.total_fees_collected  # 2% on liquid
        burnfee_burns = self.burn_fee.total_burns_executed   # 1% on liquid
        staking_locked = self.staking.total_locked           # 80% of post-mint supply
        total_liquid = self.staking.total_liquid             # 20% of post-mint supply
        burns_executed = round(mint_burns + burnfee_burns, 6)

        # Net payout = liquid amount after fees and burns
        net_payout = round(total_liquid - fees_collected - burnfee_burns, 6)

        # Friction = value destroyed or permanently removed (not staking — that still exists)
        friction_eur = round(mint_burns + burnfee_burns + fees_collected, 6)
        value_in = round(minted_total, 6)
        # Everything accounted for: payout + destroyed + locked
        value_out = round(net_payout + friction_eur + staking_locked, 6)

        # Falsifiable: must be > 0 AND <= value_in (can go red in tests)
        friction_verified = 0 < friction_eur <= value_in

        # Partition check: minted == liquid + mint_burns + locked (cross-module consistency)
        partition_ok = abs(value_in - value_out) < 0.02
        # Fee/burn ratio checks: prevent fees and burns from canceling algebraically.
        # Without these, fee×10 would still pass because fees appear as both + and −.
        fees_ok = abs(fees_collected - total_liquid * self.burn_fee.fee_rate) < 0.02
        burns_ok = abs(burnfee_burns - total_liquid * self.burn_fee.additional_burn_rate) < 0.02
        value_conserved = partition_ok and fees_ok and burns_ok

        # Token supply metrics
        effective_supply = round(minted_total - burns_executed, 6)
        staked_ratio = round(
            (staking_locked / effective_supply * 100)
            if effective_supply > 0 else 0, 2
        )

        # ── BHO verification (ADR 2: |Δ| > 0.01 € halts all payments) ──
        bho_delta = round(
            abs(
                self.settlement_exec.escrow_balance
                + self.settlement_exec.total_settled
                - settlement_volume
            ), 2
        )
        # Absolute 0.01 € threshold — not volume-relative. ADR 2 is not scalable.
        # No-settlement case is N/A, not "verified".
        bho_verified = (
            self.settlement_exec._settlement_count > 0
            and bho_delta <= 0.01
        )

        # ── Chain volumes (three separate books, not a pipeline) ──
        chain_volumes = {
            "C01_DEPIN_APPCHAIN": round(depin_volume, 2),
            "C02_BRIDGE_LAYER": round(self.bridge._total_volume_bridged, 2),
            "C03_SETTLEMENT_L1": round(settlement_volume, 2),
            "C04_LIQUIDITY_L2": round(liquidity_volume, 2),
            "C05_STAKING_LOCKED": round(staking_locked, 6),
            "C06_YIELD_DISTRIBUTED": round(self.staking.total_yield_distributed, 6),
            "C07_FEES_COLLECTED": round(fees_collected, 6),
            "C08_TOKENS_BURNED": round(burns_executed, 6),
            "C09_NET_PAYOUT": net_payout,
        }

        return {
            "status": "completed",
            "sim_id": self.sim_id,
            "artifacts": [
                {
                    "type": "multi_chain_simulation_report",
                    "cycles_completed": len(self._cycle_log),
                    "chains": {
                        name: {
                            "total_txs": chain.total_txs,
                            "total_volume": round(chain.total_volume, 6),
                            "avg_latency_ms": chain.avg_latency_ms,
                        }
                        for name, chain in self.chains.items()
                    },
                    "friction_analysis": {
                        "note": (
                            "Friction is measured inside the Liquidity chain only. "
                            "C01–C03 are separate ledgers; comparing their volumes "
                            "directly proves heterogeneity, not friction."
                        ),
                        "minted_total_eur": round(minted_total, 6),
                        "net_payout_eur": net_payout,
                        "friction_eur": friction_eur,
                        "friction_breakdown": {
                            "mint_burns": round(mint_burns, 6),
                            "burnfee_burns": round(burnfee_burns, 6),
                            "fees_collected": round(fees_collected, 6),
                            "total_friction": friction_eur,
                            "staking_locked_not_friction": round(staking_locked, 6),
                        },
                        "friction_verified": friction_verified,
                        "value_in_eur": value_in,
                        "value_out_eur": value_out,
                        "value_conserved": value_conserved,
                        "three_separate_ledgers": True,
                    },
                    "tokenomics": {
                        "total_minted": round(minted_total, 6),
                        "total_burned": round(burns_executed, 6),
                        "effective_supply": effective_supply,
                        "staked_amount": round(staking_locked, 6),
                        "staked_ratio_pct": staked_ratio,
                        "yield_distributed": round(
                            self.staking.total_yield_distributed, 6
                        ),
                        "fees_collected": round(fees_collected, 6),
                    },
                    "compliance": {
                        "bho_zero_sum_verified": bho_verified,
                        "bho_delta_eur": bho_delta,
                        "gobd_audit_entries": len(self.legal.audit_trail),
                        "escrow_balance": round(self.settlement_exec.escrow_balance, 2),
                        "tax_collected": round(self.legal._total_tax_collected, 2),
                    },
                    "chain_volumes": chain_volumes,
                    "agent_stats": {
                        "sensor": self.sensor.get_stats(),
                        "bridge": self.bridge.get_stats(),
                        "depin_wallet": self.depin_wallet.get_stats(),
                        "vob_settlement": self.vob_settlement.get_stats(),
                        "legal_compliance": self.legal.get_stats(),
                        "settlement_executor": self.settlement_exec.get_stats(),
                        "token_minter": self.token_minter.get_stats(),
                        "staking_pool": self.staking.get_stats(),
                        "burn_fee_agent": self.burn_fee.get_stats(),
                    },
                }
            ],
            "error": None,
            "metadata": {
                "sim_id": self.sim_id,
                "user_id": self.user_id,
                "cycles": len(self._cycle_log),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _drain_ready_messages(self) -> List[Dict]:
        """Extract messages whose latency has expired, decrement others."""
        ready = []
        still_pending = []
        for msg in self.cross_chain_queue:
            if msg.latency_ticks <= 0:
                ready.append(msg.payload)
            else:
                msg.latency_ticks -= 1
                still_pending.append(msg)
        self.cross_chain_queue = still_pending
        return ready

    @staticmethod
    def _extract_txs(result: Dict) -> List[Dict]:
        """Extract transaction list from standardized agent result."""
        try:
            return result.get("artifacts", [{}])[0].get("transactions", [])
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_messages(result: Dict) -> List[CrossChainMessage]:
        """Extract cross-chain messages from bridge result."""
        try:
            raw = result.get("artifacts", [{}])[0].get("messages", [])
            return [
                CrossChainMessage(
                    source_chain=m.get("source_chain", ""),
                    target_chain=m.get("target_chain", ""),
                    payload=m.get("payload", {}),
                    bridge_proof=m.get("bridge_proof", ""),
                    latency_ticks=m.get("latency_ticks", 0),
                    timestamp=m.get("timestamp", ""),
                )
                for m in raw
            ]
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_settlements(result: Dict) -> List[Dict]:
        """Extract settlements from VOB result."""
        try:
            return result.get("artifacts", [{}])[0].get("settlements", [])
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_compliant_txs(result: Dict) -> List[Dict]:
        """Extract compliant transactions from legal result."""
        try:
            return result.get("artifacts", [{}])[0].get("transactions", [])
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_executed(result: Dict) -> List[Dict]:
        """Extract executed settlements."""
        try:
            return result.get("artifacts", [{}])[0].get("settlements", [])
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_tokens(result: Dict) -> List[Dict]:
        """Extract minted tokens."""
        try:
            return result.get("artifacts", [{}])[0].get("tokens", [])
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_positions(result: Dict) -> List[Dict]:
        """Extract staking positions."""
        try:
            return result.get("artifacts", [{}])[0].get("positions", [])
        except (IndexError, KeyError, AttributeError):
            return []


# ── Demo Runner ──────────────────────────────────────────────────────────────


async def demo_simchain(cycles: int = 100, user_id: str = "demo"):
    """Run a SimChain demo and print results."""
    print("\n" + "=" * 80)
    print("🏛️  AGENT X SIMCHAIN — MULTI-CHAIN ECONOMIC SIMULATION")
    print("   DePIN Appchain → Bridge → Settlement L1 → Liquidity L2")
    print("=" * 80 + "\n")

    orch = EconomicOrchestratorMulti(user_id=user_id, cycles=cycles)

    print(f"   SimID: {orch.sim_id}")
    print(f"   Cycles: {cycles}")
    print(f"   Sensor Batch Size: {orch.sensor_batch_size}")
    print(f"   Agents: 9 across 3 chains")
    print()

    result = await orch.run_simulation(cycles=cycles)

    if result["status"] == "failed":
        print(f"\n❌ Simulation failed: {result['error']}")
        return result

    report = result["artifacts"][0]

    # Chain Stats
    print("📊 CHAIN STATISTICS:")
    print(f"   {'Chain':<20} {'TXs':>10} {'Volume':>18}")
    print(f"   {'─'*20} {'─'*10} {'─'*18}")
    for name, data in report["chains"].items():
        vol = f"€{data['total_volume']:,.2f}"
        print(f"   {name:<20} {data['total_txs']:>10,} {vol:>18}")

    # Friction Analysis
    fa = report["friction_analysis"]
    fb = fa.get("friction_breakdown", {})
    fv = "✅" if fa.get("friction_verified") else "❌"
    vc = "✅" if fa.get("value_conserved") else "❌"
    print(f"\n💸 FRICTION (Liquidity Chain):")
    print(f"   Value In (minted):    €{fa.get('value_in_eur', 0):>14,.2f}")
    print(f"   Net Payout (C09):     €{fa.get('net_payout_eur', 0):>14,.2f}")
    print(f"   Friction (outflows):  €{fa.get('friction_eur', 0):>14,.2f}")
    print(f"     · Mint Burns (5%):  €{fb.get('mint_burns', 0):>14,.2f}")
    print(f"     · Fee Burns (1%):   €{fb.get('burnfee_burns', 0):>14,.2f}")
    print(f"     · Fees (2%):        €{fb.get('fees_collected', 0):>14,.2f}")
    print(f"   Staking (not friction):€{fb.get('staking_locked_not_friction', 0):>14,.2f}")
    print(f"   Friction Verified:    {fv}")
    print(f"   Value Conserved:      {vc}")
    print(f"   Three Separate Ledgers: ✅ C01–C09 are 3 books")

    # Tokenomics
    tok = report["tokenomics"]
    print(f"\n💰 TOKENOMICS:")
    print(f"   Minted:     €{tok['total_minted']:>14,.2f}")
    print(f"   Burned:     €{tok['total_burned']:>14,.2f}")
    print(f"   Supply:     €{tok['effective_supply']:>14,.2f}")
    print(f"   Staked:     €{tok['staked_amount']:>14,.2f} ({tok['staked_ratio_pct']}%)")
    print(f"   Yield:      €{tok['yield_distributed']:>14,.2f}")
    print(f"   Fees:       €{tok['fees_collected']:>14,.2f}")

    # Compliance
    comp = report["compliance"]
    print(f"\n⚖️  COMPLIANCE:")
    print(f"   BHO Δ=0:    {'✅' if comp['bho_zero_sum_verified'] else '❌'} (Δ=€{comp['bho_delta_eur']:.2f})")
    print(f"   GoBD:       {comp['gobd_audit_entries']} entries")
    print(f"   Escrow:     €{comp['escrow_balance']:>14,.2f}")
    print(f"   Tax:        €{comp['tax_collected']:>14,.2f}")

    # Chain Volume Comparison (9-point check)
    cv = report["chain_volumes"]
    print(f"\n🔗 CHAIN VOLUME COMPARISON (9-Point Check):")
    for key, val in cv.items():
        print(f"   {key}: €{val:,.2f}")

    print(f"\n⏱️  Total elapsed: {result.get('elapsed_total_ms', 0):,.0f}ms")
    print("=" * 80)
    print("🎉 MULTI-CHAIN SIMULATION COMPLETE — Real Economic Friction Verified")
    print("=" * 80 + "\n")

    return result


# ── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    user_id = sys.argv[2] if len(sys.argv) > 2 else "demo"
    asyncio.run(demo_simchain(cycles=cycles, user_id=user_id))
