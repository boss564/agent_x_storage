#!/usr/bin/env python3
"""AgentCrew — 5-member internal crew for autonomous agent operation.

Pipeline: CommsDispatcher → Navigator → TacticalOfficer → GasManager → DecisionEngine

Each agent has a 5-person crew:
  5. Funker (CommsDispatcher)    — I/O interface
  2. Navigator                    — State ingestion, dedup
  3. Tactical Officer             — Signature & schema verification
  4. Leitender Ingenieur (Gas)    — Fuel management
  1. Kommandant (DecisionEngine)  — Action decision (PROCEED/BLOCK/REFUEL/IDLE)

Usage:
  from agents_b2g.crew import AgentCrew, FLOTTE, demo_crew_pipeline
  await demo_crew_pipeline()
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("AgentCrew")


# ─── Enums & Data Classes ───────────────────────────────────────────────────

class Action(Enum):
    IDLE = "IDLE"            # Waiting / no action
    PROCEED = "PROCEED"      # Execute settlement / payout
    BLOCK = "BLOCK"          # Security violation detected
    REFUEL = "REFUEL"        # Request gas from tanker
    REPORT = "REPORT"        # Status to fleet admiral


class CrewStatus(Enum):
    IDLE = "IDLE"
    RECEIVING = "RECEIVING"
    PROCESSING = "PROCESSING"
    DECIDING = "DECIDING"
    TRANSMITTING = "TRANSMITTING"


@dataclass
class Payload:
    """Data packet processed by the crew."""
    data: Dict[str, Any]
    validated: bool = False
    action: Optional[Action] = None
    gas_cost: float = 0.0
    latency_ms: float = 0.0
    reason: str = ""


# ─── Crew Members ───────────────────────────────────────────────────────────

class CommsDispatcher:
    """5. Funker — external I/O interface."""
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.sent: int = 0
        self.received: int = 0

    def receive(self, raw: Dict) -> Payload:
        self.received += 1
        return Payload(data=raw)


class Navigator:
    """2. Navigator — state ingestion and deduplication."""
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.block_height: int = 0
        self.seen: Set[str] = set()

    def ingest(self, payload: Payload) -> bool:
        h = hashlib.sha256(str(payload.data).encode()).hexdigest()
        if h in self.seen:
            return False
        self.seen.add(h)
        self.block_height += 1
        return True


class TacticalOfficer:
    """3. Tactical Officer — signature and schema verification via DIDRegistry.

    Default-deny: reject unless device is registered AND signature matches.
    The registry can be in demo mode (pre-loaded DIDs) or production mode
    (synced from Identity Chain / HSM).
    """
    ALLOWED_SCHEMAS = {"VOB_B", "SENSOR", "COMPLIANCE", "SETTLEMENT", "STAKING", "TREASURY", "GOVERNANCE"}

    def __init__(self, agent_id: str, registry=None):
        self.agent_id = agent_id
        if registry is None:
            from .did_registry import get_registry
            registry = get_registry(demo_mode=True)
        self.registry = registry

    def verify(self, payload: Payload) -> Tuple[bool, str]:
        """Default-deny via DIDRegistry: registered device + matching signature."""
        data = payload.data
        # 1. Schema must be allowed
        schema = data.get("schema", "UNKNOWN")
        if schema not in self.ALLOWED_SCHEMAS:
            return False, f"INVALID_SCHEMA:{schema}"
        # 2. Device must be registered AND signature must match
        device_id = data.get("device_id", "")
        sig = data.get("signature", "")
        result = self.registry.verify(device_id, sig, data)
        if not result.valid:
            return False, result.reason
        return True, "SIG_OK"


class GasManager:
    """4. Leitender Ingenieur — fuel and resource management."""
    def __init__(self, agent_id: str, initial: float = 10.0):
        self.agent_id = agent_id
        self.balance = initial
        self.initial = initial
        self.consumed = 0.0
        self.refueled = 0.0

    def can_afford(self, cost: float) -> bool:
        return self.balance >= cost

    def consume(self, cost: float) -> bool:
        if not self.can_afford(cost):
            return False
        self.balance = round(self.balance - cost, 6)
        self.consumed = round(self.consumed + cost, 6)
        return True

    def refuel(self, amount: float) -> float:
        refill = min(amount, round(self.initial - self.balance, 6))
        self.balance = round(self.balance + refill, 6)
        self.refueled = round(self.refueled + refill, 6)
        return refill

    def needs_refuel(self) -> bool:
        return self.balance < self.initial * 0.20


class DecisionEngine:
    """1. Kommandant — decides PROCEED, BLOCK, REFUEL, or IDLE."""
    def __init__(self, agent_id: str, role: str):
        self.agent_id = agent_id
        self.role = role
        self.decisions: int = 0

    def decide(self, payload: Payload, gas_ok: bool, verified: bool) -> Action:
        self.decisions += 1
        if not verified:
            return Action.BLOCK
        if not gas_ok:
            return Action.REFUEL
        if payload.validated:
            return Action.PROCEED
        return Action.IDLE


# ─── AgentCrew — The Complete Ship ──────────────────────────────────────────

class AgentCrew:
    """A fully crewed autonomous agent with 5 internal roles."""

    def __init__(self, agent_id: str, role: str, gas: float = 10.0):
        self.agent_id = agent_id
        self.role = role
        self.comms = CommsDispatcher(agent_id)
        self.navigator = Navigator(agent_id)
        self.tactical = TacticalOfficer(agent_id)
        self.gas = GasManager(agent_id, gas)
        self.decider = DecisionEngine(agent_id, role)
        self.status: CrewStatus = CrewStatus.IDLE
        self.processed: int = 0
        self.rejected: int = 0
        self.total_latency: float = 0.0

    async def process(self, raw: Dict[str, Any]) -> Tuple[Action, Payload]:
        """Execute one tick: Funker → Navigator → Tactical → Gas → Command."""
        t0 = time.time()
        self.status = CrewStatus.RECEIVING

        # 5. Funker — receive
        payload = self.comms.receive(raw)

        # 2. Navigator — ingest, dedup
        self.status = CrewStatus.PROCESSING
        if not self.navigator.ingest(payload):
            self.status = CrewStatus.IDLE
            return Action.IDLE, payload

        # 3. Tactical Officer — verify
        valid, reason = self.tactical.verify(payload)
        if not valid:
            self.rejected += 1
            payload.reason = reason
            self.status = CrewStatus.IDLE
            self.total_latency += (time.time() - t0) * 1000
            return Action.BLOCK, payload

        payload.validated = True

        # 4. GasManager — fuel check (must pass threshold, not just afford single action)
        self.status = CrewStatus.DECIDING
        if self.gas.needs_refuel():
            self.status = CrewStatus.IDLE
            self.total_latency += (time.time() - t0) * 1000
            return Action.REFUEL, payload

        gas_cost = 0.005 if raw.get("z3_proof") else 0.0001
        self.gas.consume(gas_cost)
        payload.gas_cost = gas_cost

        # 1. Kommandant — decide
        action = self.decider.decide(payload, True, valid)
        payload.action = action
        self.processed += 1

        self.status = CrewStatus.TRANSMITTING
        self.status = CrewStatus.IDLE
        latency = (time.time() - t0) * 1000
        self.total_latency += latency
        payload.latency_ms = latency
        return action, payload

    def snapshot(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "status": self.status.value,
            "gas_balance": self.gas.balance,
            "gas_pct": round(self.gas.balance / self.gas.initial * 100, 1),
            "block_height": self.navigator.block_height,
            "processed": self.processed,
            "rejected": self.rejected,
            "avg_latency_ms": round(self.total_latency / max(1, self.processed + self.rejected), 2),
            "decisions": self.decider.decisions,
            "needs_refuel": self.gas.needs_refuel(),
        }


# ─── The 9-Agent Fleet ──────────────────────────────────────────────────────

FLOTTE: Dict[str, AgentCrew] = {
    "A1": AgentCrew("A1", "SENSOR", gas=5.0),
    "A2": AgentCrew("A2", "BRIDGE", gas=3.0),
    "A3": AgentCrew("A3", "WALLET", gas=2.0),
    "A4": AgentCrew("A4", "Z3_PROOF", gas=50.0),
    "A5": AgentCrew("A5", "COMPLIANCE", gas=10.0),
    "A6": AgentCrew("A6", "EXECUTOR", gas=25.0),
    "A7": AgentCrew("A7", "TREASURY", gas=100.0),  # Der Tanker
    "A8": AgentCrew("A8", "STAKING", gas=30.0),
    "A9": AgentCrew("A9", "GOVERNANCE", gas=20.0),
}


# ─── Demo Runner ────────────────────────────────────────────────────────────

async def demo_crew_pipeline():
    """Demonstrate the crew pipeline: normal → block (unmarked) → block (unknown) → refuel."""
    print("\n" + "=" * 70)
    print("🚢 AGENT CREW — 5-köpfige Mannschaft in Aktion (Default-Deny)")
    print("=" * 70 + "\n")

    crew = AgentCrew("A5", "COMPLIANCE", gas=10.0)
    events: List[Tuple[str, Dict, str]] = [
        ("Legitim", {"schema": "COMPLIANCE", "device_id": "MEIER_BAU_GMBH", "signature": "0xSIG_3", "amount": 45000.0}, "PROCEED"),
        ("Unbekanntes Gerät", {"schema": "COMPLIANCE", "device_id": "0xUNREGISTERED", "signature": "0xa7b3c91d4e", "amount": 999999.0}, "BLOCK"),
        ("Fehlende Signatur", {"schema": "COMPLIANCE", "device_id": "MEIER_BAU_GMBH", "amount": 999999.0}, "BLOCK"),
        ("Refuel-Trigger", {"schema": "COMPLIANCE", "device_id": "MEIER_BAU_GMBH", "signature": "0xSIG_3", "amount": 10000.0}, "REFUEL"),
    ]

    for label, raw, expected in events:
        if label == "Refuel-Trigger":
            crew.gas.balance = 1.0  # Force low fuel
        action, p = await crew.process(raw)
        icon = "✅" if action.value == expected else "⚠️"
        expected_mark = f"(expected {expected})" if action.value != expected else ""
        print(f"  {icon} {label:<22} → {action.value:<8} ({p.latency_ms:.2f} ms) {p.reason} {expected_mark}")

    ss = crew.snapshot()
    print(f"\n  📊 Crew-Status: gas={ss['gas_balance']:.1f}€ ({ss['gas_pct']}%) "
          f"blocks={ss['block_height']} ok={ss['processed']} rej={ss['rejected']} "
          f"Ø={ss['avg_latency_ms']}ms")
    print("  ✅ Default-Deny: unbekannte Geräte + fehlende Signaturen werden abgewiesen\n")


if __name__ == "__main__":
    asyncio.run(demo_crew_pipeline())
