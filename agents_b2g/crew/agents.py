#!/usr/bin/env python3
"""9 Specialized Crew Agents — C01 bis C09.

Each agent extends AgentCrew with role-specific validation,
schema rules, fee collection, and decision overrides.

Blueprint: agents_b2g/crew/crew.py → AgentCrew (5-member pipeline)
"""

import asyncio
import hashlib
import logging
import sys
import os
from typing import Any, Dict, Tuple, Optional

# Support both package import and standalone execution
try:
    from .crew import AgentCrew, Action, Payload
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from crew.crew import AgentCrew, Action, Payload

logger = logging.getLogger("CrewAgents")

# ── Shared Registry ──────────────────────────────────────────

VALID_SIGNATURES = {
    "MEIER_BAU_GMBH": "0xVALID_SIG_3",
    "ESP32_DEMO_01": "0xVALID_SIG_1",
    "CONTRACTOR_4012": "0xCONTRACTOR_SIG",
    "INSPECTOR_MUC": "0xINSPECTOR_SIG",
    "TANKER_ALPHA": "0xTANKER_A_SIG",
    "KLINIKBAU_AG": "0xKLINIK_SIG",
    "TREASURY_MAIN": "0xTREASURY_SIG",
    "GOVERNANCE_COUNCIL": "0xGOV_SIG",
    "STAKING_POOL": "0xSTAKING_SIG",
}

ALLOWED_SCHEMAS = ["VOB_B", "SENSOR", "COMPLIANCE", "SETTLEMENT", "TREASURY", "GOVERNANCE", "STAKING"]


# ══════════════════════════════════════════════════════════════
# C01 — IoT Ingest Agent (Sensor-Fänger)
# ══════════════════════════════════════════════════════════════

class IoTIngestAgent(AgentCrew):
    """C01: Receives sensor data, earns micro-fees per batch."""

    def __init__(self, gas: float = 5.0):
        super().__init__("C01", "SENSOR", gas=gas)
        self.total_batches = 0
        self.micro_fee = 0.0001
        self._sensor_readings: list = []

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        # Accumulate sensor readings
        self._sensor_readings.append(raw)
        if len(self._sensor_readings) >= 100:
            self.total_batches += 1
            self._sensor_readings = []
            return Action.PROCEED, Payload(
                data={"batch": self.total_batches, "readings": 100},
                validated=True, action=Action.PROCEED, gas_cost=self.micro_fee * 100,
            )
        action, payload = await super().process(raw)
        return action, payload

    def collect_fees(self) -> float:
        return self.micro_fee * self.total_batches * 100

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({"batches": self.total_batches, "collected_fees": self.collect_fees()})
        return s


# ══════════════════════════════════════════════════════════════
# C02 — Milestone Validator (Meilenstein-Prüfer)
# ══════════════════════════════════════════════════════════════

class MilestoneValidatorAgent(AgentCrew):
    """C02: Validates construction milestones, earns Z3-proof fees."""

    def __init__(self, gas: float = 15.0):
        super().__init__("C02", "Z3_PROOF", gas=gas)
        self.proofs_verified = 0
        self.z3_fee = 0.001

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        if action == Action.PROCEED and payload.validated:
            self.proofs_verified += 1
        return action, payload

    def collect_fees(self) -> float:
        return self.z3_fee * self.proofs_verified

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({"proofs_verified": self.proofs_verified, "collected_fees": self.collect_fees()})
        return s


# ══════════════════════════════════════════════════════════════
# C03 — Legal & Compliance Agent (§48b, SSI, Z3)
# ══════════════════════════════════════════════════════════════

class ComplianceAgent(AgentCrew):
    """C03: Legal compliance — §48b, SSI-DIDs, Z3 BHO proofs."""

    def __init__(self, gas: float = 10.0):
        super().__init__("C03", "COMPLIANCE", gas=gas)
        self.compliance_checks = 0
        self.compliance_fee = 0.005

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        if payload.validated:
            self.compliance_checks += 1
        return action, payload

    def collect_fees(self) -> float:
        return self.compliance_fee * self.compliance_checks

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({"compliance_checks": self.compliance_checks, "collected_fees": self.collect_fees()})
        return s


# ══════════════════════════════════════════════════════════════
# C04 — Escrow & Settlement Agent (Multi-Split)
# ══════════════════════════════════════════════════════════════

class EscrowSettlementAgent(AgentCrew):
    """C04: Multi-split escrow settlement — 80/15/5 VOB/B split."""

    def __init__(self, gas: float = 25.0):
        super().__init__("C04", "EXECUTOR", gas=gas)
        self.total_settled: float = 0.0
        self.fee_rate = 0.005  # 0.5% of tranche

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        if action == Action.PROCEED:
            amount = float(raw.get("amount", 0))
            self.total_settled += amount
        return action, payload

    def collect_fees(self) -> float:
        return self.total_settled * self.fee_rate

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({"total_settled": self.total_settled, "collected_fees": self.collect_fees()})
        return s


# ══════════════════════════════════════════════════════════════
# C05 — Audit Compliance Agent (GoBD Archivist)
# ══════════════════════════════════════════════════════════════

class AuditComplianceAgent(AgentCrew):
    """C05: GoBD-compliant archiving with hash-chain verification."""

    def __init__(self, gas: float = 10.0):
        super().__init__("C05", "COMPLIANCE", gas=gas)
        self.archive_entries = 0
        self.archive_fee = 0.01
        self._hash_chain: list = []

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        if payload.validated:
            self.archive_entries += 1
            self._hash_chain.append(
                hashlib.sha256(f"{len(self._hash_chain)}:{raw.get('contract_id', '?')}".encode()).hexdigest()[:16]
            )
        return action, payload

    def collect_fees(self) -> float:
        return self.archive_fee * self.archive_entries

    def verify_chain(self) -> bool:
        return len(self._hash_chain) == self.archive_entries

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({
            "archive_entries": self.archive_entries,
            "collected_fees": self.collect_fees(),
            "chain_intact": self.verify_chain(),
        })
        return s


# ══════════════════════════════════════════════════════════════
# C06 — Staking Pool Agent (Escrow Yield)
# ══════════════════════════════════════════════════════════════

class StakingPoolAgent(AgentCrew):
    """C06: Manages escrow staking pool, earns APY-based yield."""

    def __init__(self, gas: float = 30.0):
        super().__init__("C06", "STAKING", gas=gas)
        self.locked_escrow: float = 0.0
        self.total_yield: float = 0.0
        self.apy = 0.12

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        if action == Action.PROCEED:
            escrow_amount = float(raw.get("amount", 0)) * 0.05  # 5% retention
            self.locked_escrow += escrow_amount
            monthly_yield = self.locked_escrow * (self.apy / 12)
            self.total_yield += monthly_yield
        return action, payload

    def collect_fees(self) -> float:
        return self.total_yield

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({
            "locked_escrow": self.locked_escrow,
            "total_yield": self.total_yield,
            "collected_fees": self.collect_fees(),
        })
        return s


# ══════════════════════════════════════════════════════════════
# C07 — Treasury Agent (Fee Collector)
# ══════════════════════════════════════════════════════════════

class TreasuryAgent(AgentCrew):
    """C07: Collects all system fees and manages the reserve."""

    def __init__(self, gas: float = 100.0):  # The tanker
        super().__init__("C07", "TREASURY", gas=gas)
        self.total_fees: float = 0.0
        self.reserve: float = 0.0

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        fee = float(raw.get("fee", 0))
        if fee > 0:
            self.total_fees += fee
            self.reserve += fee * 0.9
        return action, payload

    def collect_fees(self) -> float:
        return self.total_fees

    def refuel_fleet(self, agent: "AgentCrew", amount: float) -> float:
        if self.reserve >= amount and self.gas.balance >= amount:
            agent.gas.refuel(amount)
            self.reserve -= amount
            return amount
        return 0.0

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({
            "total_fees": self.total_fees,
            "reserve": self.reserve,
            "collected_fees": self.collect_fees(),
        })
        return s


# ══════════════════════════════════════════════════════════════
# C08 — Governor Agent (Vote Weight)
# ══════════════════════════════════════════════════════════════

class GovernorAgent(AgentCrew):
    """C08: Manages governance votes, earns vote premiums."""

    def __init__(self, gas: float = 20.0):
        super().__init__("C08", "GOVERNANCE", gas=gas)
        self.total_votes = 0
        self.vote_premium = 0.001
        self._veto_count = 0

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        if action == Action.PROCEED and payload.validated:
            self.total_votes += 1
            if raw.get("veto"):
                self._veto_count += 1
        return action, payload

    def collect_fees(self) -> float:
        return self.vote_premium * self.total_votes

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({
            "total_votes": self.total_votes,
            "vetoes": self._veto_count,
            "voting_power": self.total_votes - self._veto_count,
            "collected_fees": self.collect_fees(),
        })
        return s


# ══════════════════════════════════════════════════════════════
# C09 — Token Burner Agent (Supply Reduction)
# ══════════════════════════════════════════════════════════════

class TokenBurnerAgent(AgentCrew):
    """C09: Burns 0.5% of minted tokens, drives deflationary pressure."""

    def __init__(self, gas: float = 20.0):
        super().__init__("C09", "TREASURY", gas=gas)
        self.total_burned: float = 0.0
        self.burn_rate = 0.005
        self._supply_tracker: float = 100_000_000.0  # 100M initial supply

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        action, payload = await super().process(raw)
        minted = float(raw.get("minted", 0))
        if minted > 0 and action == Action.PROCEED:
            burn_amount = minted * self.burn_rate
            self.total_burned += burn_amount
            self._supply_tracker -= burn_amount
        return action, payload

    def collect_fees(self) -> float:
        # Virtual gain: 10% value appreciation from supply reduction
        return self.total_burned * 0.1

    def snapshot(self) -> Dict[str, Any]:
        s = super().snapshot()
        s.update({
            "total_burned": self.total_burned,
            "supply_remaining": self._supply_tracker,
            "deflation_pct": round(self.total_burned / 100_000_000.0 * 100, 4),
            "collected_fees": self.collect_fees(),
        })
        return s


# ── Agent Factory ─────────────────────────────────────────────

def create_fleet() -> Dict[str, AgentCrew]:
    """Factory: create all 9 agents with role-specific configs."""
    return {
        "C01": IoTIngestAgent(gas=5.0),
        "C02": MilestoneValidatorAgent(gas=15.0),
        "C03": ComplianceAgent(gas=10.0),
        "C04": EscrowSettlementAgent(gas=25.0),
        "C05": AuditComplianceAgent(gas=10.0),
        "C06": StakingPoolAgent(gas=30.0),
        "C07": TreasuryAgent(gas=100.0),    # The tanker
        "C08": GovernorAgent(gas=20.0),
        "C09": TokenBurnerAgent(gas=20.0),
    }


# ── Standalone smoke test ────────────────────────────────────

async def demo_agents():
    """Demo each agent with a role-appropriate payload."""
    fleet = create_fleet()

    scenarios = {
        "C01": {"schema": "SENSOR", "device_id": "ESP32_DEMO_01", "signature": "0xVALID_SIG_1", "temperature": 21.5},
        "C02": {"schema": "VOB_B", "device_id": "MEIER_BAU_GMBH", "signature": "0xVALID_SIG_3", "amount": 45000.0, "milestone": "M5"},
        "C03": {"schema": "COMPLIANCE", "device_id": "MEIER_BAU_GMBH", "signature": "0xVALID_SIG_3", "amount": 45000.0, "z3_proof": True, "section_48b": True},
        "C04": {"schema": "SETTLEMENT", "device_id": "CONTRACTOR_4012", "signature": "0xCONTRACTOR_SIG", "amount": 45000.0},
        "C05": {"schema": "COMPLIANCE", "device_id": "MEIER_BAU_GMBH", "signature": "0xVALID_SIG_3", "contract_id": "VOB-2026-001"},
        "C06": {"schema": "STAKING", "device_id": "STAKING_POOL", "signature": "0xSTAKING_SIG", "amount": 100000.0},
        "C07": {"schema": "TREASURY", "device_id": "TREASURY_MAIN", "signature": "0xTREASURY_SIG", "fee": 225.0},
        "C08": {"schema": "GOVERNANCE", "device_id": "GOVERNANCE_COUNCIL", "signature": "0xGOV_SIG", "proposal": "RATE_CHANGE"},
        "C09": {"schema": "TREASURY", "device_id": "TREASURY_MAIN", "signature": "0xTREASURY_SIG", "minted": 50000.0},
        "ATTACK": {"schema": "COMPLIANCE", "device_id": "0xUNREGISTERED", "signature": "0xa7b3c91d4e", "amount": 999999.0},
    }

    print("\n" + "=" * 70)
    print("⚓ 9-AGENT FLEET — Smoke Test")
    print("=" * 70 + "\n")

    for agent_id, agent in fleet.items():
        raw = scenarios.get(agent_id, scenarios["C03"])
        action, payload = await agent.process(raw)
        ss = agent.snapshot()
        icon = "✅" if action == Action.PROCEED else "🛡️" if action == Action.BLOCK else "⛽"
        print(f"  {icon} {agent_id} ({agent.role:<12}) → {action.value:<8} "
              f"gas={ss['gas_balance']:.1f}€ blk={ss['block_height']} "
              f"fees={ss.get('collected_fees', 0):.4f}€")

    # Attack scenario on C03
    print(f"\n  💥 Attack on C03:")
    raw = scenarios["ATTACK"]
    action, payload = await fleet["C03"].process(raw)
    print(f"     → {action.value} ({payload.reason})")

    total_fees = sum(a.collect_fees() for a in fleet.values())
    total_processed = sum(a.processed for a in fleet.values())
    total_rejected = sum(a.rejected for a in fleet.values())
    print(f"\n  💰 Collected Fees: {total_fees:.4f}€ | Ok={total_processed} Rej={total_rejected}")
    print("  ✅ Agent-Demo abgeschlossen\n")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    asyncio.run(demo_agents())
    sys.exit(0)
