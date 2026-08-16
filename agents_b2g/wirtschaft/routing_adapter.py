"""Routing adapter for the Wirtschaftsagenten (Baustein 4).

Bridges the wirtschaft MessageBus (topic-addressed envelopes) to the
protocol.AgentMessage used by the ABM TickController. Provides the
KlassenResolver, which resolves klasse.A/B/C addresses to concrete agents.

NOTE: agents/surface/predictive_router.PredictiveHealthRouter is a
D01 replica-health shunt, NOT a class dispatcher, so class resolution
needs its own resolver (member list + optional health + crc32 tie-break).
"""
from __future__ import annotations

import zlib
from typing import Any, Dict, List, Optional

from agents_b2g.protocol import AgentMessage
from agents_b2g.wirtschaft.base import KompetenzKlasse


# --- KlassenResolver ---------------------------------------------------------

class KlassenResolver:
    """Resolves klasse.A/B/C addresses to a concrete agent id.

    Selection: class member list, optionally weighted by health score,
    deterministic tie-break via zlib.crc32 (avoids the TIER-0 hash()
    reproducibility bug).
    """

    def __init__(self):
        self._members: Dict[KompetenzKlasse, List[str]] = {k: [] for k in KompetenzKlasse}
        self._health: Dict[str, float] = {}

    def register(self, klasse: KompetenzKlasse, agent_id: str) -> None:
        if agent_id not in self._members[klasse]:
            self._members[klasse].append(agent_id)

    def set_health(self, agent_id: str, score: float) -> None:
        self._health[agent_id] = float(score)

    def members(self, klasse: KompetenzKlasse) -> List[str]:
        return list(self._members.get(klasse, []))

    def resolve(self, klasse: KompetenzKlasse, tie_break_seed: str = "") -> Optional[str]:
        """Pick a concrete agent for klasse. Deterministic."""
        candidates = self._members.get(klasse, [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        def key(agent_id: str):
            health = self._health.get(agent_id, 0.0)
            tie = zlib.crc32(f"{tie_break_seed}:{agent_id}".encode())
            return (-health, tie)   # highest health first, crc32 breaks ties

        return sorted(candidates, key=key)[0]

    @staticmethod
    def parse_klasse(target: str) -> Optional[KompetenzKlasse]:
        """Parse 'klasse.A/B/C' (or a bare 'A/B/C') into a KompetenzKlasse."""
        if not isinstance(target, str):
            return None
        value = target.split(".")[-1]
        try:
            return KompetenzKlasse(value)
        except ValueError:
            return None


# --- Envelope <-> AgentMessage ----------------------------------------------

def envelope_to_agent_message(envelope: Dict[str, Any], payload_type) -> AgentMessage:
    """Translate a MessageBus envelope to a protocol.AgentMessage.

    The wirtschaft kind/topic/payload are preserved in content so the
    receiver can reconstruct the envelope. payload_type must be a valid
    protocol.PayloadType member (chosen by the routing layer).
    """
    return AgentMessage(
        sender=envelope.get("sender", ""),
        receiver=envelope.get("target", ""),
        payload_type=payload_type,
        content={
            "wirtschaft_kind": envelope.get("kind"),
            "wirtschaft_topic": envelope.get("topic"),
            "payload": envelope.get("payload"),
        },
    )


def agent_message_to_envelope(msg: AgentMessage) -> Dict[str, Any]:
    """Translate a protocol.AgentMessage back to a MessageBus envelope."""
    content = msg.content if isinstance(msg.content, dict) else {}
    return {
        "topic": content.get("wirtschaft_topic", ""),
        "sender": msg.sender,
        "target": msg.receiver,
        "kind": content.get("wirtschaft_kind", "request"),
        "payload": content.get("payload", {}),
    }


# --- WirtschaftsRouter -------------------------------------------------------

class WirtschaftsRouter:
    """Routes wirtschaft envelopes to concrete agents via the KlassenResolver
    and delivers them as protocol.AgentMessage.

    Inject as a WirtschaftAgent's message_bus.transport to replace the
    in-process loopback with real addressed routing.
    """

    def __init__(self, resolver: KlassenResolver, agents: Dict[str, Any],
                 payload_type):
        self.resolver = resolver
        self.agents = agents            # agent_id -> WirtschaftAgent
        self.payload_type = payload_type
        self.delivered: List[AgentMessage] = []   # inspection/testing

    def route(self, envelope: Dict[str, Any]) -> Optional[AgentMessage]:
        """Resolve the envelope's target and deliver as AgentMessage."""
        klasse = KlassenResolver.parse_klasse(envelope.get("target", ""))
        if klasse is None:
            target_id = envelope.get("target")          # direct agent address
        else:
            target_id = self.resolver.resolve(
                klasse, tie_break_seed=envelope.get("sender", ""))
        if target_id is None or target_id not in self.agents:
            return None
        resolved = dict(envelope)
        resolved["target"] = target_id                  # class -> concrete agent
        msg = envelope_to_agent_message(resolved, self.payload_type)
        self.agents[target_id].receive(msg)
        self.delivered.append(msg)
        return msg
