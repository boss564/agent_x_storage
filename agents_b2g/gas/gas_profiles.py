"""Gas Profiles — Per-agent fuel management with tank, consumption, and reserve."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict

logger = logging.getLogger("GasProfiles")


@dataclass
class GasProfile:
    """Fuel profile for one agent: tank balance, consumption rate, refuel logic."""

    agent_id: str
    balance: float = 0.0
    initial_balance: float = 0.0
    fee_per_action: float = 0.0
    min_reserve: float = 0.0
    refuel_threshold: float = 0.0
    total_consumed: float = 0.0
    total_refueled: float = 0.0
    status: str = "ACTIVE"  # ACTIVE, LOW_FUEL, OUT_OF_GAS, REFUELING
    actions: int = 0

    @classmethod
    def create(cls, agent_id: str, initial: float, fee: float) -> "GasProfile":
        return cls(
            agent_id=agent_id,
            balance=initial,
            initial_balance=initial,
            fee_per_action=fee,
            min_reserve=round(initial * 0.10, 6),
            refuel_threshold=round(initial * 0.20, 6),
            status="ACTIVE",
        )

    def consume(self, n: int = 1) -> bool:
        """Consume gas for n actions. Returns False if OUT_OF_GAS."""
        cost = self.fee_per_action * n
        if self.balance < cost:
            self.status = "OUT_OF_GAS"
            logger.warning("⛽ %s: OUT_OF_GAS (balance=%.4f, needed=%.4f)", self.agent_id, self.balance, cost)
            return False
        self.balance = round(self.balance - cost, 6)
        self.total_consumed = round(self.total_consumed + cost, 6)
        self.actions += n
        if self.balance < self.refuel_threshold:
            self.status = "LOW_FUEL"
        return True

    def refuel(self, amount: float) -> float:
        """Refill tank up to initial_balance. Returns actual amount refilled."""
        refill = min(amount, round(self.initial_balance - self.balance, 6))
        if refill <= 0:
            return 0.0
        self.balance = round(self.balance + refill, 6)
        self.total_refueled = round(self.total_refueled + refill, 6)
        self.status = "ACTIVE"
        return refill

    def needs_refuel(self) -> bool:
        return self.balance < self.refuel_threshold and self.status != "OUT_OF_GAS"

    def drain_to(self, target: float) -> None:
        """Force drain to a target balance (for demo scenarios)."""
        self.balance = target
        if target < self.min_reserve:
            self.status = "LOW_FUEL"
        if target <= 0:
            self.status = "OUT_OF_GAS"

    def get_status(self) -> Dict[str, Any]:
        pct = round(self.balance / self.initial_balance * 100, 1) if self.initial_balance > 0 else 0
        return {
            "agent_id": self.agent_id,
            "balance": self.balance,
            "initial": self.initial_balance,
            "percent": pct,
            "fee_per_action": self.fee_per_action,
            "min_reserve": self.min_reserve,
            "status": self.status,
            "total_consumed": self.total_consumed,
            "total_refueled": self.total_refueled,
            "actions": self.actions,
            "needs_refuel": self.needs_refuel(),
        }


# ── 9 Agent Gas Profiles ────────────────────────────────────────────────────

AGENT_GAS_PROFILES: Dict[str, GasProfile] = {
    "A1": GasProfile.create("A1", initial=5.00, fee=0.0001),
    "A2": GasProfile.create("A2", initial=3.00, fee=0.0005),
    "A3": GasProfile.create("A3", initial=2.00, fee=0.001),
    "A4": GasProfile.create("A4", initial=50.00, fee=0.005),
    "A5": GasProfile.create("A5", initial=10.00, fee=0.001),
    "A6": GasProfile.create("A6", initial=25.00, fee=0.01),
    "A7": GasProfile.create("A7", initial=20.00, fee=0.01),
    "A8": GasProfile.create("A8", initial=30.00, fee=0.02),
    "A9": GasProfile.create("A9", initial=100.00, fee=0.05),
}
