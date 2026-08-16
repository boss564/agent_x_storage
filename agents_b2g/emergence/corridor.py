#!/usr/bin/env python3
"""TIER 2c — DID-Lock Feuer-Korridor (Buendelung, keine Warteschlange).

Der Korridor entsteht aus Lock-Erwerb (DID-Registry-Ereignis), nicht aus einer
globalen Uhr. Innerhalb des Fensters duerfen alle Agenten mit ausreichender
Ladung feuern (Buendelung). Ausserhalb akkumuliert Ladung weiter — kein Reset.

Kritisch: nach dem Fenster folgt eine Cooldown-Luecke (gap), sonst oeffnet der
Lock sofort wieder und das Feuer-Muster kollabiert auf freies Integrate-and-Fire.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CorridorStats:
    openings: int = 0
    fires_in_corridor: int = 0
    firers_per_opening: List[int] = field(default_factory=list)
    lock_holders: List[str] = field(default_factory=list)
    closed_ticks: int = 0
    open_ticks: int = 0

    @property
    def mean_utilization(self) -> float:
        if not self.firers_per_opening:
            return 0.0
        return float(sum(self.firers_per_opening) / len(self.firers_per_opening))


class FireCorridor:
    """Emergent fire window opened by DID lock acquisition.

    width == 0  -> always open (free integrate-and-fire control).
    width >= 1  -> lock acquisition opens a bundling window; afterwards a
                   cooldown ``gap`` keeps the corridor closed so charge can
                   pile up above threshold (true burst when it reopens).
    """

    def __init__(self, width: int = 0, gap: Optional[int] = None, registry: Any = None):
        self.width = max(0, int(width))
        # gap defaults to width (symmetric closed period); min 1 when width>0
        if gap is None:
            self.gap = self.width if self.width > 0 else 0
        else:
            self.gap = max(0, int(gap))
        if self.width > 0 and self.gap < 1:
            self.gap = 1
        self.registry = registry
        self.open_until: Optional[int] = None
        self.opened_at: Optional[int] = None
        self.cooldown_until: Optional[int] = None
        self.holder: Optional[str] = None
        self.stats = CorridorStats()
        self._current_firers = 0
        self._closing_recorded = True

    def in_cooldown(self, cycle: int) -> bool:
        return self.cooldown_until is not None and cycle <= self.cooldown_until

    def is_open(self, cycle: int) -> bool:
        if self.width <= 0:
            return True
        if self.open_until is None:
            return False
        if cycle > self.open_until:
            self._close(at_cycle=cycle)
            return False
        return True

    def _close(self, at_cycle: int) -> None:
        if self.opened_at is not None and not self._closing_recorded:
            self.stats.firers_per_opening.append(self._current_firers)
            self._closing_recorded = True
        # Cooldown starts after the last open tick
        last_open = self.open_until if self.open_until is not None else (at_cycle - 1)
        self.cooldown_until = int(last_open) + self.gap
        self.open_until = None
        self.opened_at = None
        self.holder = None
        self._current_firers = 0

    def try_acquire(self, agent_id: str, cycle: int) -> bool:
        """Lock acquisition opens a new corridor (emergent, not a global clock)."""
        if self.width <= 0:
            return False
        if self.in_cooldown(cycle):
            return False
        if self.is_open(cycle):
            return False

        did = f"did:agx:corridor:{agent_id}"
        if self.registry is not None:
            if not self.registry.is_active(did):
                self.registry.register(
                    did,
                    public_key=f"0xCORR_{agent_id}",
                    metadata={"role": "CORRIDOR_LOCK", "agent": agent_id},
                )
            rec = self.registry.get(did)
            if rec is not None:
                rec.metadata["corridor_acquired_cycle"] = cycle
                rec.metadata["corridor_width"] = self.width
                rec.metadata["corridor_gap"] = self.gap
                rec.last_seen = time.time()

        if self.opened_at is not None and not self._closing_recorded:
            self.stats.firers_per_opening.append(self._current_firers)

        self.holder = agent_id
        self.opened_at = cycle
        self.open_until = cycle + self.width - 1
        self.cooldown_until = None  # clear any stale cooldown
        self._current_firers = 0
        self._closing_recorded = False
        self.stats.openings += 1
        self.stats.lock_holders.append(agent_id)
        return True

    def record_fire(self) -> None:
        self.stats.fires_in_corridor += 1
        self._current_firers += 1

    def note_tick(self, cycle: int) -> None:
        if self.width <= 0:
            return
        if self.is_open(cycle):
            self.stats.open_ticks += 1
        else:
            self.stats.closed_ticks += 1

    def finalize(self, cycle: int) -> None:
        if self.width > 0 and self.opened_at is not None and not self._closing_recorded:
            self.stats.firers_per_opening.append(self._current_firers)
            self._closing_recorded = True

    def summary(self, n_agents: int) -> Dict[str, Any]:
        util = self.stats.mean_utilization
        return {
            "width": self.width,
            "gap": self.gap,
            "openings": self.stats.openings,
            "fires_in_corridor": self.stats.fires_in_corridor,
            "mean_firers_per_opening": round(util, 3),
            "utilization_frac": round(util / max(n_agents, 1), 4),
            "n_unique_holders": len(set(self.stats.lock_holders)),
            "open_ticks": self.stats.open_ticks,
            "closed_ticks": self.stats.closed_ticks,
        }


def corridor_step(
    osc: Any,
    corridor: FireCorridor,
    agent_id: str,
    cycle: int,
) -> bool:
    """Accumulate → optional lock → optional fire.

    Outside an open corridor (width>0): charge piles up past threshold, no fire.
    Cooldown after each window prevents instant re-open (IF-collapse).
    """
    osc.charge += float(osc.base_rate)

    threshold = float(osc.threshold)
    lock_trigger = float(getattr(osc, "lock_trigger", 0.90 * threshold))

    if corridor.width > 0 and not corridor.is_open(cycle) and not corridor.in_cooldown(cycle):
        if osc.charge >= lock_trigger:
            corridor.try_acquire(agent_id, cycle)

    if corridor.is_open(cycle) and osc.charge >= threshold:
        osc.charge = 0.0
        if corridor.width > 0:
            corridor.record_fire()
        return True
    return False
