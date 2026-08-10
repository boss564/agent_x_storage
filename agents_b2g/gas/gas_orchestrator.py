"""GasOrchestrator — Autonomous fuel management for all 9 agents.

Monitors tank levels, triggers refuel from central treasury, executes
OUT_OF_GAS protocol (pause agent → security check → emergency refuel).

Usage:
  from agents_b2g.gas import GasOrchestrator
  orch = GasOrchestrator()
  orch.consume("A1", 100)           # Consume 100 actions worth of gas
  orch.drain_and_trigger("A1")      # Demo: force OUT_OF_GAS
  print(orch.summary())
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .gas_profiles import AGENT_GAS_PROFILES, GasProfile

logger = logging.getLogger("GasOrchestrator")


class GasOrchestrator:
    """Master fuel controller: monitors, refuels, handles OUT_OF_GAS."""

    def __init__(self, treasury: float = 1000.0):
        self.profiles: Dict[str, GasProfile] = {
            aid: GasProfile.create(aid, p.initial_balance, p.fee_per_action)
            for aid, p in AGENT_GAS_PROFILES.items()
        }
        self.treasury = treasury
        self.refuel_count = 0
        self.out_of_gas_events = 0
        self.event_log: List[Dict] = []

    # ── Public API ──────────────────────────────────────────────────────────

    def consume(self, agent_id: str, actions: int = 1) -> bool:
        """Consume gas for an agent. Returns False if OUT_OF_GAS."""
        if agent_id not in self.profiles:
            return False
        ok = self.profiles[agent_id].consume(actions)
        if not ok:
            self.out_of_gas_events += 1
            self._handle_out_of_gas(agent_id)
        return ok

    def refuel(self, agent_id: str, amount: Optional[float] = None) -> float:
        """Refuel an agent from treasury."""
        if agent_id not in self.profiles:
            return 0.0
        profile = self.profiles[agent_id]
        needed = round(profile.initial_balance - profile.balance, 6)
        if amount is None:
            amount = min(needed, self.treasury * 0.05)
        available = min(amount, needed, self.treasury)
        if available <= 0:
            return 0.0
        self.treasury = round(self.treasury - available, 6)
        refilled = profile.refuel(available)
        self.refuel_count += 1
        self.event_log.append({
            "type": "REFUEL", "agent": agent_id, "amount": refilled,
            "treasury_left": self.treasury,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return refilled

    def drain_and_trigger(self, agent_id: str) -> Dict[str, Any]:
        """Demo: force an agent into OUT_OF_GAS and observe the autonomous response."""
        if agent_id not in self.profiles:
            return {"error": f"Unknown agent: {agent_id}"}

        profile = self.profiles[agent_id]
        before = profile.balance

        # 1. Drain to near-empty
        profile.drain_to(0.001)
        drained = round(before - profile.balance, 6)

        # 2. Force one more consumption → OUT_OF_GAS
        had_gas = profile.consume(1)

        # 3. Autonomous response: emergency refuel
        emergency_amount = min(2.0, self.treasury)  # €2 emergency
        refilled = self.refuel(agent_id, emergency_amount)

        self.event_log.append({
            "type": "OUT_OF_GAS_RESOLVED", "agent": agent_id,
            "drained": drained, "emergency_refuel": refilled,
            "auto_resolved": refilled > 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "agent_id": agent_id,
            "before_balance": before,
            "drained": drained,
            "had_gas_after_drain": had_gas,
            "status": profile.status,
            "emergency_refuel_eur": refilled,
            "final_balance": profile.balance,
            "autonomous_resolution": refilled > 0,
            "message": (
                f"⛽ {agent_id} drained to €{profile.balance:.4f}. "
                f"{'✅ Autonomous refuel: +€' + str(refilled) if refilled > 0 else '❌ No treasury gas left!'}"
            ),
        }

    def summary(self) -> Dict[str, Any]:
        """Return gas system summary."""
        agents = {aid: p.get_status() for aid, p in self.profiles.items()}
        total_balance = sum(p.balance for p in self.profiles.values())
        total_initial = sum(p.initial_balance for p in self.profiles.values())
        out_of_gas = [aid for aid, p in self.profiles.items() if p.status == "OUT_OF_GAS"]

        return {
            "total_balance_eur": round(total_balance, 6),
            "total_initial_eur": round(total_initial, 6),
            "utilization_pct": round((1 - total_balance / total_initial) * 100, 1) if total_initial > 0 else 0,
            "treasury_eur": round(self.treasury, 6),
            "out_of_gas_agents": out_of_gas,
            "refuel_count": self.refuel_count,
            "out_of_gas_events": self.out_of_gas_events,
            "agents": agents,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Internal ────────────────────────────────────────────────────────────

    def _handle_out_of_gas(self, agent_id: str):
        """Autonomous OUT_OF_GAS protocol."""
        profile = self.profiles[agent_id]
        logger.warning("🚨 OUT_OF_GAS: %s — initiating autonomous protocol", agent_id)

        # Emergency refuel from treasury
        emergency = min(2.0, self.treasury)
        if emergency > 0:
            self.refuel(agent_id, emergency)
            logger.info("⛽ %s: emergency refuel +€%.2f", agent_id, emergency)
        else:
            logger.error("⛽❌ %s: no treasury gas — agent stays paused", agent_id)
