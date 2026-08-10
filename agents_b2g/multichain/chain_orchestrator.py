"""ChainOrchestrator — Multi-Chain Coordinator for 9 Sovereign Appchains.

Coordinates 4 Chain Layers with 9 independent appchains:
  DEPIN_APPCHAIN (A1-A3): High-frequency sensor data → bridge → settlement
  SETTLEMENT_L1  (A4-A6): VOB/B milestones, Z3 proofs, multi-split
  LIQUIDITY_L2   (A7-A8): Token minting, staking, APY
  IDENTITY_CHAIN (A9):    SSI verification, ZK-proofs

Each chain maintains its own block height, state root, mempool, and
consensus interval. Cross-chain communication uses Merkle proofs.
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .subchains.sensor_aggregator import SensorAggregatorChain
from .subchains.bridge_relayer import BridgeRelayerChain
from .subchains.depin_wallet import DePINWalletChain
from .subchains.vob_settlement import VOBSettlementChain
from .subchains.legal_compliance import LegalComplianceChain
from .subchains.settlement_executor import SettlementExecutorChain
from .subchains.token_minter import TokenMinterChain
from .subchains.staking_pool import StakingPoolChain
from .subchains.identity_compliance import IdentityComplianceChain

logger = logging.getLogger("ChainOrchestrator")


@dataclass
class ChainState:
    """Runtime state of a sovereign appchain layer."""
    name: str
    block_height: int = 0
    mempool: List[Dict] = field(default_factory=list)
    state_root: str = "0x0"
    total_txs: int = 0
    total_volume: float = 0.0
    avg_block_time_ms: float = 0.0


@dataclass
class CrossChainEnvelope:
    """A message in transit between sovereign chains."""
    source: str
    target: str
    payload: List[Dict]
    merkle_root: str
    proof_path: List[str] = field(default_factory=list)
    latency_ms: int = 0
    timestamp: str = ""


class ChainOrchestrator:
    """Master coordinator for the 9 sovereign appchains."""

    def __init__(
        self,
        user_id: Optional[str] = None,
        cycles: int = 100,
        sensor_batch: Optional[int] = None,
    ):
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        self.cycles = cycles
        self.sensor_batch = sensor_batch or int(os.getenv("MC_SENSOR_BATCH", "1000"))

        # ── 9 Sovereign Appchains ──
        self.sensor = SensorAggregatorChain(user_id=self.user_id, batch_size=self.sensor_batch)
        self.bridge = BridgeRelayerChain(user_id=self.user_id)
        self.wallet = DePINWalletChain(user_id=self.user_id)
        self.vob = VOBSettlementChain(user_id=self.user_id)
        self.legal = LegalComplianceChain(user_id=self.user_id)
        self.executor = SettlementExecutorChain(user_id=self.user_id)
        self.token = TokenMinterChain(user_id=self.user_id)
        self.staking = StakingPoolChain(user_id=self.user_id)
        self.identity = IdentityComplianceChain(user_id=self.user_id)

        # ── 4 Chain Layer States ──
        self.layers = {
            "DEPIN_APPCHAIN": ChainState(name="DEPIN_APPCHAIN"),
            "SETTLEMENT_L1": ChainState(name="SETTLEMENT_L1"),
            "LIQUIDITY_L2": ChainState(name="LIQUIDITY_L2"),
            "IDENTITY_CHAIN": ChainState(name="IDENTITY_CHAIN"),
        }

        # ── Cross-Chain Message Queue ──
        self.message_queue: List[CrossChainEnvelope] = []
        self._cycle_log: List[Dict] = []

        # ── Simulation ID ──
        self.sim_id = hashlib.sha256(
            f"MC_{self.user_id}_{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        logger.info("ChainOrchestrator initialized: 4 layers, 9 chains, %s", self.sim_id)

    # ── Public API ──────────────────────────────────────────────────────────

    async def run_simulation(self, cycles: Optional[int] = None) -> Dict[str, Any]:
        """Run the multi-chain simulation."""
        cycles = cycles or self.cycles
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info("Starting multi-chain sim", extra={"job_id": job_id, "cycles": cycles})

            for cycle in range(1, cycles + 1):
                c_start = time.time()

                # ── LAYER 1: DEPIN_APPCHAIN ──
                sensor_result = await self.sensor.process_block(cycle)
                sensor_txs = self._extract_list(sensor_result, "transactions")
                self.layers["DEPIN_APPCHAIN"].total_txs += len(sensor_txs)
                depin_vol = sum(t.get("amount", 0) for t in sensor_txs)
                self.layers["DEPIN_APPCHAIN"].total_volume += depin_vol

                # Wallet payouts
                await self.wallet.process_block(sensor_txs)

                # ── BRIDGE: Cross-Chain Relay with Merkle Proof ──
                bridge_result = await self.bridge.relay(
                    source="DEPIN_APPCHAIN",
                    target="SETTLEMENT_L1",
                    payload=sensor_txs,
                    merkle_root=self.sensor.state_root,
                )
                env = self._extract_envelope(bridge_result)
                if env:
                    self.message_queue.append(env)

                # ── LAYER 4: IDENTITY_CHAIN ──
                identity_result = await self.identity.verify_credentials(cycle)
                id_valid = self._extract_first(identity_result, "valid", True)

                # ── LAYER 2: SETTLEMENT_L1 ──
                ready = self._drain_messages()
                if ready and id_valid:
                    # VOB Settlement
                    vob_result = await self.vob.process_block(ready)
                    settlements = self._extract_list(vob_result, "settlements")
                    self.layers["SETTLEMENT_L1"].total_txs += len(settlements)
                    settle_vol = sum(s.get("amount", 0) for s in settlements)
                    self.layers["SETTLEMENT_L1"].total_volume += settle_vol

                    # Legal Compliance
                    legal_result = await self.legal.process_block(settlements)
                    compliant = self._extract_list(legal_result, "transactions")

                    # Settlement Executor
                    exec_result = await self.executor.process_block(compliant)
                    executed = self._extract_list(exec_result, "settlements")

                    # ── LAYER 3: LIQUIDITY_L2 ──
                    token_result = await self.token.process_block(executed)
                    tokens = self._extract_list(token_result, "tokens")
                    liq_vol = sum(t.get("mint_amount", 0) for t in tokens)
                    self.layers["LIQUIDITY_L2"].total_volume += liq_vol
                    self.layers["LIQUIDITY_L2"].total_txs += len(tokens)

                    await self.staking.process_block(tokens)

                # ── Cycle Log ──
                c_elapsed = round((time.time() - c_start) * 1000, 2)
                self._cycle_log.append({
                    "cycle": cycle,
                    "depin_volume": round(depin_vol, 6),
                    "depin_txs": len(sensor_txs),
                    "settlement_volume": round(self.layers["SETTLEMENT_L1"].total_volume, 2),
                    "liquidity_volume": round(self.layers["LIQUIDITY_L2"].total_volume, 6),
                    "queue_depth": len(self.message_queue),
                    "identity_valid": id_valid,
                    "elapsed_ms": c_elapsed,
                })

                if cycle % 100 == 0 or cycle == 1:
                    logs.append(
                        f"[INFO] c={cycle}/{cycles} "
                        f"depin={depin_vol:.2f} settle={self.layers['SETTLEMENT_L1'].total_volume:,.0f} "
                        f"liq={self.layers['LIQUIDITY_L2'].total_volume:,.0f} q={len(self.message_queue)}"
                    )

            elapsed = round((time.time() - start_time) * 1000, 2)
            report = self.generate_report()
            report["job_id"] = job_id
            report["elapsed_total_ms"] = elapsed
            report["logs"] = logs

            logger.info("Simulation complete", extra={"job_id": job_id, "elapsed_ms": elapsed})
            return report

        except Exception as e:
            elapsed = round((time.time() - start_time) * 1000, 2)
            logger.error("Simulation failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed", "job_id": job_id, "sim_id": self.sim_id,
                "artifacts": [],
                "error": {"code": "SIM_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed, "user_id": self.user_id},
            }

    def generate_report(self) -> Dict[str, Any]:
        """Generate the multi-chain state report with honest accounting."""
        depin_vol = self.layers["DEPIN_APPCHAIN"].total_volume
        settle_vol = self.layers["SETTLEMENT_L1"].total_volume
        liq_vol = self.layers["LIQUIDITY_L2"].total_volume

        minted = self.token.total_minted
        mint_burns = self.token.total_burned
        fees = 0.0  # Not separately tracked in multichain v1 — burn_fee merged into token
        staking_locked = self.staking.total_locked
        total_liquid = self.staking.total_liquid
        net_payout = round(total_liquid, 6)  # liquid = net payout in v1 (no separate fee/burn on liquid)

        friction_eur = round(mint_burns, 6)
        value_in = round(minted, 6)
        value_out = round(net_payout + mint_burns + staking_locked, 6)
        friction_verified = 0 < friction_eur <= value_in
        value_conserved = abs(value_in - value_out) < 0.02

        bho_delta = round(abs(self.executor.escrow_balance + self.executor.total_settled - settle_vol), 2)
        bho_verified = self.executor._settlement_count > 0 and bho_delta <= 0.01

        chain_volumes = {
            "C01_DEPIN_APPCHAIN": round(depin_vol, 2),
            "C02_BRIDGE_LAYER": round(self.bridge._total_volume, 2),
            "C03_SETTLEMENT_L1": round(settle_vol, 2),
            "C04_LIQUIDITY_L2": round(liq_vol, 2),
            "C05_STAKING_LOCKED": round(staking_locked, 6),
            "C06_YIELD_DISTRIBUTED": round(self.staking.total_yield, 6),
            "C07_FEES_COLLECTED": round(fees, 6),
            "C08_TOKENS_BURNED": round(mint_burns, 6),
            "C09_NET_PAYOUT": net_payout,
        }

        return {
            "status": "completed",
            "sim_id": self.sim_id,
            "artifacts": [{
                "type": "multi_chain_report",
                "cycles_completed": len(self._cycle_log),
                "layers": {
                    "DEPIN_APPCHAIN": {
                        "total_txs": self.layers["DEPIN_APPCHAIN"].total_txs,
                        "total_volume": round(self.layers["DEPIN_APPCHAIN"].total_volume, 6),
                        "block_height": self.sensor.block_height,
                    },
                    "SETTLEMENT_L1": {
                        "total_txs": self.layers["SETTLEMENT_L1"].total_txs,
                        "total_volume": round(self.layers["SETTLEMENT_L1"].total_volume, 6),
                        "block_height": self.vob.block_height,
                    },
                    "LIQUIDITY_L2": {
                        "total_txs": self.layers["LIQUIDITY_L2"].total_txs,
                        "total_volume": round(self.layers["LIQUIDITY_L2"].total_volume, 6),
                        "block_height": self.token.block_height,
                    },
                    "IDENTITY_CHAIN": {
                        "total_txs": 0,
                        "total_volume": 0.0,
                        "block_height": self.identity.block_height,
                    },
                },
                "chain_states": {
                    "A1_sensor": self.sensor.get_chain_state(),
                    "A2_bridge": self.bridge.get_chain_state(),
                    "A3_wallet": self.wallet.get_chain_state(),
                    "A4_vob": self.vob.get_chain_state(),
                    "A5_legal": self.legal.get_chain_state(),
                    "A6_executor": self.executor.get_chain_state(),
                    "A7_token": self.token.get_chain_state(),
                    "A8_staking": self.staking.get_chain_state(),
                    "A9_identity": self.identity.get_chain_state(),
                },
                "friction_analysis": {
                    "note": "Friction measured inside the Liquidity chain. 4 layers = separate ledgers.",
                    "value_in_eur": value_in,
                    "net_payout_eur": net_payout,
                    "friction_eur": friction_eur,
                    "friction_breakdown": {
                        "mint_burns": round(mint_burns, 6),
                        "fees": round(fees, 6),
                    },
                    "staking_locked_not_friction": round(staking_locked, 6),
                    "friction_verified": friction_verified,
                    "value_conserved": value_conserved,
                    "four_separate_ledgers": True,
                },
                "compliance": {
                    "bho_zero_sum_verified": bho_verified,
                    "bho_delta_eur": bho_delta,
                    "gobd_audit_entries": len(self.legal.audit_trail),
                    "escrow_balance": round(self.executor.escrow_balance, 2),
                    "tax_collected": round(self.legal._total_tax, 2),
                    "identity_verifications": self.identity._verifications,
                    "identity_pass_rate": round(
                        self.identity._passed / max(1, self.identity._verifications) * 100, 1
                    ),
                },
                "chain_volumes": chain_volumes,
            }],
            "error": None,
            "metadata": {
                "sim_id": self.sim_id,
                "user_id": self.user_id,
                "cycles": len(self._cycle_log),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _drain_messages(self) -> List[Dict]:
        ready, pending = [], []
        for env in self.message_queue:
            if env.latency_ms <= 0:
                ready.extend(env.payload)
            else:
                env.latency_ms -= 100
                pending.append(env)
        self.message_queue = pending
        return ready

    @staticmethod
    def _extract_list(result: Dict, key: str) -> List[Dict]:
        try:
            return result.get("artifacts", [{}])[0].get(key, [])
        except (IndexError, KeyError, AttributeError):
            return []

    @staticmethod
    def _extract_first(result: Dict, key: str, default: Any = None) -> Any:
        try:
            return result.get("artifacts", [{}])[0].get(key, default)
        except (IndexError, KeyError, AttributeError):
            return default

    @staticmethod
    def _extract_envelope(result: Dict) -> Optional[CrossChainEnvelope]:
        try:
            a = result.get("artifacts", [{}])[0]
            return CrossChainEnvelope(
                source=a.get("source_chain", ""),
                target=a.get("target_chain", ""),
                payload=a.get("transactions", []),
                merkle_root=a.get("merkle_root", "0x0"),
                proof_path=a.get("proof_path", []),
                latency_ms=a.get("latency_ms", 0),
                timestamp=a.get("timestamp", ""),
            )
        except (IndexError, KeyError, AttributeError):
            return None


# ── Demo Runner ─────────────────────────────────────────────────────────────

async def demo_multichain(cycles: int = 100, user_id: str = "demo"):
    """Run a MultiChain demo and print results."""
    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  🏛️  AGENT X MULTICHAIN — 9 SOVEREIGN APPCHAINS".center(74) + "█")
    print("█" + "  4 Layers | DEPIN → Settlement → Liquidity → Identity".center(74) + "█")
    print("█" + " " * 78 + "█")
    print("█" * 80 + "\n")

    orch = ChainOrchestrator(user_id=user_id, cycles=cycles)
    print(f"  SimID: {orch.sim_id}  |  Cycles: {cycles}  |  Sensor Batch: {orch.sensor_batch}\n")
    print("  🚀 Running...\n")

    t0 = time.time()
    result = await orch.run_simulation(cycles=cycles)

    if result["status"] == "failed":
        print(f"\n  ❌ FAILED: {result['error']}")
        return result

    r = result["artifacts"][0]
    elapsed = result.get("elapsed_total_ms", 0)
    tps = (cycles * orch.sensor_batch) / (elapsed / 1000) if elapsed > 0 else 0

    # Layer Stats
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  📊 4 CHAIN LAYERS                                          │")
    print("  ├──────────────────┬──────────────┬──────────────┬────────────┤")
    print("  │ Layer            │      TXs     │    Volume    │   Blocks   │")
    print("  ├──────────────────┼──────────────┼──────────────┼────────────┤")
    for name, l in r["layers"].items():
        vol = f"€{l['total_volume']:,.2f}" if l["total_volume"] < 1e6 else f"€{l['total_volume']/1e6:,.2f}M"
        print(f"  │ {name:<17}│ {l['total_txs']:>12,} │ {vol:>12} │ {l['block_height']:>10} │")
    print("  └──────────────────┴──────────────┴──────────────┴────────────┘")

    # Friction
    fa = r["friction_analysis"]
    fv = "✅" if fa["friction_verified"] else "❌"
    vc = "✅" if fa["value_conserved"] else "❌"
    print(f"\n  💸 Friction: {fv}  |  Value Conserved: {vc}  |  Friction: €{fa['friction_eur']:,.2f}")

    # Compliance
    c = r["compliance"]
    bho = "✅" if c["bho_zero_sum_verified"] else "❌"
    print(f"  ⚖️  BHO: {bho} (Δ=€{c['bho_delta_eur']:.2f})  |  GoBD: {c['gobd_audit_entries']:,}  |  Tax: €{c['tax_collected']:,.0f}")
    print(f"  🆔 Identity: {c['identity_verifications']} checks, {c['identity_pass_rate']}% pass")

    # Chain State
    print(f"\n  📋 9 CHAIN STATES:")
    for name, state in r["chain_states"].items():
        bh = state.get("block_height", 0)
        extra = state.get("total_settled", state.get("total_minted", state.get("total_payouts", "")))
        extra_str = f"€{extra:,.0f}" if isinstance(extra, (int, float)) and extra else ""
        print(f"     {name:<12}  block={bh:>5}  {extra_str}")

    total_s = time.time() - t0
    print(f"\n  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║  ⏱️  Wall: {total_s:.1f}s  |  CPU: {elapsed:,.0f}ms  |  TPS: {tps:,.0f}  ║")
    print(f"  ╚══════════════════════════════════════════════════════════════╝")
    print(f"\n  🎉 9 SOVEREIGN APPCHAINS — SIMULATION COMPLETE\n")

    return result


if __name__ == "__main__":
    import sys
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    user_id = sys.argv[2] if len(sys.argv) > 2 else "demo"
    asyncio.run(demo_multichain(cycles=cycles, user_id=user_id))
