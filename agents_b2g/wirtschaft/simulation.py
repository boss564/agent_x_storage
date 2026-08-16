"""Wirtschafts-Simulation for emergence measurement (Baustein 5).

Drives the 9-agent Wirtschafts-Schwarm over N ticks. Agents act at
different natural frequencies; the Gewaltenteilung (Freigabe flow,
periodically re-armed so it keeps coupling) ties the classes together.
The per-agent event timestamps feed the AstroCore Kuramoto evaluator.
"""
from __future__ import annotations

from typing import Dict, List

from agents_b2g.wirtschaft.schwarm import build_schwarm


class WirtschaftsSimulation:
    def __init__(self, ticks: int = 200, gas_tank: float = 10000.0,
                 reset_freigaben_every: int = 10):
        self.schwarm, self.agents_by_name = build_schwarm()
        self.agents_by_id = {a.id: a for a in self.agents_by_name.values()}
        self.ticks = ticks
        self.reset_freigaben_every = reset_freigaben_every
        self.events: Dict[str, List[int]] = {aid: [] for aid in self.agents_by_id}
        # enough gas so the coupling loop never starves mid-run
        for agent in self.agents_by_id.values():
            agent.gas_monitor.tank_capacity = gas_tank
            agent.gas_monitor.gas = gas_tank
        self._freq = self._assign_frequencies()

    def _assign_frequencies(self) -> Dict[str, int]:
        # deterministic per-agent natural frequency (2, 3 or 4 ticks)
        freq = {}
        for i, aid in enumerate(sorted(self.agents_by_id)):
            freq[aid] = 2 + (i % 3)
        return freq

    def _pick_action(self, agent, tick: int):
        rechte = agent.competence.exklusive_rechte if agent.competence else []
        if not rechte:
            return None
        return rechte[tick % len(rechte)]

    def run(self) -> Dict[str, List[int]]:
        """Run the loop; returns {agent_id: [event_tick, ...]}."""
        for tick in range(self.ticks):
            # re-arm the Freigabe flow so coupling keeps happening
            if self.reset_freigaben_every and tick % self.reset_freigaben_every == 0:
                for agent in self.agents_by_id.values():
                    agent._freigaben.clear()
            for aid, agent in self.agents_by_id.items():
                if tick % self._freq[aid] == 0:
                    aktion = self._pick_action(agent, tick)
                    if aktion:
                        self.schwarm.execute(aid, aktion)
                        self.events[aid].append(tick)
        return self.events
