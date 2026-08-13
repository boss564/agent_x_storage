#!/usr/bin/env python3
"""Panzergrenadier Base — mechanized infantry edge-clearance layer.

9 agents (P01–P09) handle complex edge cases that would slow the
high-throughput surface (C01–C09) or submarine (D01–D08) layers.
The core idea: the main batch stays "mounted" (fast path); only
events that need special handling "dismount" into a slow, careful
reconciliation path.

The PanzergrenadierAgent base class implements the state machine;
each P0x subclass overrides _requires_dismount (when to dismount)
and _isolate_and_reconcile (what to do when dismounted).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Panzergrenadier")


class DeploymentState(Enum):
    MOUNTED = "AUFGESESSEN"
    DISMOUNTED = "ABGESESSEN"


@dataclass
class ClearanceResult:
    """Outcome of one edge-clearance operation."""
    event_id: str
    dismounted: bool
    cleared: bool
    elapsed_ms: float = 0.0
    agent_id: str = ""
    note: str = ""


class PanzergrenadierAgent:
    """Base mechanized agent: mounted fast path vs. dismounted clearance."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.state = DeploymentState.MOUNTED
        self.dismount_count = 0
        self.clear_count = 0
        self._total_clear_ms = 0.0

    async def process_payload(self, event: Dict) -> ClearanceResult:
        """Route an event through the fast path or dismounted clearance."""
        t0 = time.time()
        if self._requires_dismount(event):
            result = await self._dismount_and_clear(event)
        else:
            result = ClearanceResult(
                event_id=event.get("id", "?"),
                dismounted=False,
                cleared=False,
                agent_id=self.agent_id,
            )
        result.elapsed_ms = round((time.time() - t0) * 1000, 3)
        return result

    def _requires_dismount(self, event: Dict) -> bool:
        """Heuristic: does this event need dismounting? Overridden by subclasses."""
        return False

    async def _dismount_and_clear(self, event: Dict) -> ClearanceResult:
        self.state = DeploymentState.DISMOUNTED
        self.dismount_count += 1
        logger.warning("⚔️ %s SITZT AB! Event %s", self.agent_id, event.get("id"))
        t0 = time.time()
        try:
            cleared = await self._isolate_and_reconcile(event)
            self.clear_count += 1
            logger.info("✅ %s SITZT AUF — Event %s bereinigt.", self.agent_id, event.get("id"))
            return ClearanceResult(
                event_id=event.get("id", "?"),
                dismounted=True,
                cleared=cleared,
                agent_id=self.agent_id,
                note=self._note(),
            )
        finally:
            self.state = DeploymentState.MOUNTED
            self._total_clear_ms += (time.time() - t0) * 1000

    async def _isolate_and_reconcile(self, event: Dict) -> bool:
        """Default reconciliation. Overridden by subagents."""
        await asyncio.sleep(0.001)
        event["pzg_cleared"] = True
        return True

    def _note(self) -> str:
        return f"{self.agent_id} clearance"

    def stats(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "dismount_count": self.dismount_count,
            "clear_count": self.clear_count,
            "avg_clear_ms": round(self._total_clear_ms / max(1, self.clear_count), 3),
        }


class PanzergrenadierCoordinator:
    """Routes events from P09 (recon) to the appropriate platoon leader (P01–P03).

    The three platoon leaders delegate to their subagent teams (P04–P07),
    with P08 (security) monitoring and P09 (recon) marking events.
    """

    def __init__(self):
        self.leaders: Dict[str, PanzergrenadierAgent] = {}
        self.subagents: Dict[str, PanzergrenadierAgent] = {}
        self.security: Optional[PanzergrenadierAgent] = None
        self.recon: Optional[PanzergrenadierAgent] = None
        self.total_routed = 0
        self.total_dismounted = 0

    def register_leader(self, leader: PanzergrenadierAgent) -> None:
        self.leaders[leader.agent_id] = leader

    def register_subagent(self, sub: PanzergrenadierAgent) -> None:
        self.subagents[sub.agent_id] = sub

    def set_security(self, agent: PanzergrenadierAgent) -> None:
        self.security = agent

    def set_recon(self, agent: PanzergrenadierAgent) -> None:
        self.recon = agent

    def route(self, event: Dict) -> str:
        """Route an event to the appropriate platoon leader based on complexity."""
        self.total_routed += 1
        if event.get("is_nested_cross_shard"):
            return "P01"
        if event.get("state_conflict"):
            return "P02"
        if event.get("compliance_edge"):
            return "P03"
        return ""  # no special handling — stay mounted

    async def process(self, event: Dict) -> ClearanceResult:
        """Full pipeline: recon marks → route → leader → subagents → security."""
        leader_id = self.route(event)
        if not leader_id:
            return ClearanceResult(
                event_id=event.get("id", "?"), dismounted=False, cleared=False,
                agent_id="P09", note="no special handling",
            )
        leader = self.leaders.get(leader_id)
        if leader is None:
            return ClearanceResult(event_id=event.get("id", "?"), dismounted=False, cleared=False)
        result = await leader.process_payload(event)
        if result.dismounted:
            self.total_dismounted += 1
        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "total_routed": self.total_routed,
            "total_dismounted": self.total_dismounted,
            "leaders": {k: v.stats() for k, v in self.leaders.items()},
            "subagents": {k: v.stats() for k, v in self.subagents.items()},
        }
