"""
Agent X — Inter-Agent Communication Protocol & State Machine.

Standardisiertes Kommunikationsprotokoll für alle Agenten (Haupt- und Subagenten).
Definiert Pydantic-Modelle für Nachrichten und eine formale Zustandsmaschine.

Usage:
    from agents_b2g.protocol import AgentMessage, AgentState, StateMachine

    msg = AgentMessage(sender="P1", receiver="P2", payload_type="OFFER",
                       content={"good": "WHEAT", "quantity": 100, "price": 12.50})
    state = StateMachine.transition(agent, "NEGOTIATING")
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Message Protocol
# ═══════════════════════════════════════════════════════════════════════════════

class PayloadType(str, Enum):
    """Standardisierte Nachrichtentypen für den Inter-Agenten-Verkehr."""

    # Wirtschaftskreislauf
    OFFER           = "OFFER"           # Produzent → Markt: Angebot
    DEMAND          = "DEMAND"          # Konsument → Markt: Nachfrage
    TRADE           = "TRADE"           # Markt → Produzent/Konsument: Handel bestätigt
    SETTLEMENT      = "SETTLEMENT"      # Orchestrator → Bank: Zahlung ausführen

    # BHO / Audit
    BHO_PROOF       = "BHO_PROOF"       # Z3-Service → Orchestrator: Δ = 0 bewiesen
    BHO_VIOLATION   = "BHO_VIOLATION"   # Orchestrator → Dashboard: BHO verletzt
    AUDIT_ENTRY     = "AUDIT_ENTRY"     # Orchestrator → AuditTrail: Eintrag erstellen
    CERTIFICATE     = "CERTIFICATE"     # Orchestrator → Extern: Zertifikat ausstellen

    # Zustand & Steuerung
    STATE_CHANGE    = "STATE_CHANGE"    # Agent → Agent: Zustandswechsel melden
    HEALTH_CHECK    = "HEALTH_CHECK"    # Monitor → Agent: Heartbeat
    HEALTH_RESPONSE = "HEALTH_RESPONSE" # Agent → Monitor: Statusantwort
    ALERT           = "ALERT"           # Monitor → Orchestrator: Eskalation
    ERROR           = "ERROR"           # Jeder → Jeder: Fehlerbericht

    # Ressourcen
    RESOURCE_REQ    = "RESOURCE_REQ"    # Agent → ResourceOracle: Bedarf anmelden
    RESOURCE_ALLOC  = "RESOURCE_ALLOC"  # ResourceOracle → Agent: Zuteilung

    # Governance
    PROPOSAL        = "PROPOSAL"        # Agent → Governance: Antrag
    VOTE            = "VOTE"            # Agent → Governance: Abstimmung
    VETO            = "VETO"            # Agent → Governance: Einspruch


class AgentMessage(BaseModel):
    """Standardisierte Nachricht zwischen Agenten.

    Jede Nachricht hat einen eindeutigen Hash (Replay-Schutz) und
    einen kausalen Vorgänger (parent_msg_id) für Audit-Trails.
    """

    # Absender / Empfänger
    sender: str = Field(..., min_length=1, max_length=64,
                        description="Agent-ID des Absenders (z.B. 'P1', 'B1', 'orch')")
    receiver: str = Field(..., min_length=1, max_length=64,
                          description="Agent-ID des Empfängers oder 'broadcast'")
    payload_type: PayloadType = Field(..., description="Typ der Nutzlast")
    content: Dict[str, Any] = Field(default_factory=dict,
                                    description="Beliebige Nutzlast als Dictionary")

    # Routing & Tracing
    msg_id: str = Field(default_factory=lambda: hashlib.sha3_256(
        f"{time.time_ns()}".encode()).hexdigest()[:16],
                        description="Eindeutige Nachrichten-ID (Hash)")
    parent_msg_id: Optional[str] = Field(default=None,
                                         description="ID der Vorgängernachricht (Kausalkette)")
    correlation_id: Optional[str] = Field(default=None,
                                          description="ID für zusammengehörige Nachrichten")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(),
                           description="ISO-8601 Zeitstempel")

    # BHO / Compliance
    ttl_seconds: int = Field(default=300, ge=1, le=86400,
                             description="Time-to-Live in Sekunden")
    priority: int = Field(default=0, ge=0, le=5,
                          description="0=normal, 5=kritisch (Eskalation)")

    # Prüfsumme über die gesamte Nachricht (ohne msg_id und hash)
    hash: str = Field(default="",
                      description="SHA3-256 Hash des serialisierten Inhalts (Replay-Schutz)")

    def model_post_init(self, __context: Any) -> None:
        """Berechnet den Hash nach der Initialisierung."""
        if not self.hash:
            import json as _json
            raw = _json.dumps({
                "s": self.sender, "r": self.receiver,
                "t": str(self.payload_type),
                "c": self.content, "ts": self.timestamp,
            }, sort_keys=True, default=str)
            self.hash = hashlib.sha3_256(raw.encode()).hexdigest()[:32]

    def is_expired(self) -> bool:
        """True wenn die Nachricht älter als ttl_seconds ist."""
        try:
            sent = datetime.fromisoformat(self.timestamp)
            age = (datetime.now(timezone.utc) - sent).total_seconds()
            return age > self.ttl_seconds
        except Exception:
            return True

    def reply(self, payload_type: PayloadType, content: Dict[str, Any],
              receiver: Optional[str] = None) -> "AgentMessage":
        """Erzeugt eine Antwort-Nachricht mit korrektem parent_msg_id."""
        return AgentMessage(
            sender=self.receiver,
            receiver=receiver or self.sender,
            payload_type=payload_type,
            content=content,
            parent_msg_id=self.msg_id,
            correlation_id=self.correlation_id,
        )

    def to_bus(self) -> dict:
        """Serialisiert für den EventBus (dict-Format)."""
        return self.model_dump()

    @classmethod
    def from_bus(cls, envelope: dict) -> "AgentMessage":
        """Deserialisiert aus einem EventBus-Envelope."""
        return cls(**envelope.get("payload", envelope))


# ═══════════════════════════════════════════════════════════════════════════════
# State Machine
# ═══════════════════════════════════════════════════════════════════════════════

class AgentState(str, Enum):
    """Universelle Agenten-Zustände.

    Jeder Agent — ob Produzent, Konsument, Bank oder Regulator —
    durchläuft diesen Lebenszyklus. Subagenten können den Zyklus
    überschreiben, aber nicht die Transitionen verletzen.
    """

    IDLE         = "IDLE"          # Bereit, kein aktiver Auftrag
    NEGOTIATING  = "NEGOTIATING"   # Verhandelt mit einem anderen Agenten
    TRANSACTING  = "TRANSACTING"   # Führt eine Transaktion aus
    WAITING      = "WAITING"       # Wartet auf externe Bestätigung (Z3, HSM)
    COMMITTING   = "COMMITTING"    # Schreibt Ergebnis fest (Audit, Ledger)
    COMPLETED    = "COMPLETED"     # Zyklus erfolgreich abgeschlossen
    FAILED       = "FAILED"        # Zyklus fehlgeschlagen (BHO-Verletzung, Timeout)
    PAUSED       = "PAUSED"        # Extern pausiert (Circuit Breaker, DND)


# Erlaubte Transitionen (Zustandsgraph)
TRANSITIONS: Dict[AgentState, List[AgentState]] = {
    AgentState.IDLE:        [AgentState.NEGOTIATING, AgentState.PAUSED],
    AgentState.NEGOTIATING: [AgentState.TRANSACTING, AgentState.COMMITTING,
                            AgentState.FAILED, AgentState.IDLE],
    AgentState.TRANSACTING: [AgentState.WAITING, AgentState.COMMITTING, AgentState.FAILED],
    AgentState.WAITING:     [AgentState.COMMITTING, AgentState.FAILED, AgentState.TRANSACTING],
    AgentState.COMMITTING:  [AgentState.COMPLETED, AgentState.FAILED],
    AgentState.COMPLETED:   [AgentState.IDLE],
    AgentState.FAILED:      [AgentState.IDLE, AgentState.NEGOTIATING],
    AgentState.PAUSED:      [AgentState.IDLE],
}


class StateTransition(BaseModel):
    """Protokollierter Zustandswechsel eines Agenten."""

    agent_id: str
    from_state: AgentState
    to_state: AgentState
    triggered_by: str = Field(..., description="Ursache: msg_id, 'timeout', 'admin'")
    reason: str = Field(default="", description="Human-readable Begründung")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_valid(self) -> bool:
        """True wenn die Transition im Zustandsgraphen erlaubt ist."""
        return self.to_state in TRANSITIONS.get(self.from_state, [])


class StateMachine:
    """Formale Zustandsmaschine für Agenten.

    Usage:
        sm = StateMachine("P1", AgentState.IDLE)
        sm.transition(AgentState.NEGOTIATING, triggered_by="msg_abc")
    """

    def __init__(self, agent_id: str, initial_state: AgentState = AgentState.IDLE):
        self.agent_id = agent_id
        self.current = initial_state
        self.history: List[StateTransition] = []
        self.entered_at: str = datetime.now(timezone.utc).isoformat()

    def transition(self, to: AgentState, triggered_by: str = "internal",
                   reason: str = "") -> StateTransition:
        """Führt einen Zustandswechsel durch.

        Raises:
            ValueError: Wenn die Transition nicht erlaubt ist.
        """
        if to not in TRANSITIONS.get(self.current, []):
            raise ValueError(
                f"Ungültige Transition: {self.agent_id} {self.current.value} → "
                f"{to.value}. Erlaubt: {[s.value for s in TRANSITIONS.get(self.current, [])]}"
            )

        t = StateTransition(
            agent_id=self.agent_id,
            from_state=self.current,
            to_state=to,
            triggered_by=triggered_by,
            reason=reason,
        )
        self.current = to
        self.history.append(t)
        return t

    def can_transition(self, to: AgentState) -> bool:
        """Prüft ob eine Transition erlaubt ist, ohne sie auszuführen."""
        return to in TRANSITIONS.get(self.current, [])

    def time_in_state(self) -> float:
        """Sekunden im aktuellen Zustand."""
        try:
            entered = datetime.fromisoformat(self.entered_at)
            return (datetime.now(timezone.utc) - entered).total_seconds()
        except Exception:
            return 0.0

    def is_terminal(self) -> bool:
        """True wenn der Agent in einem Endzustand ist (COMPLETED, FAILED)."""
        return self.current in (AgentState.COMPLETED, AgentState.FAILED)

    def reset(self):
        """Setzt den Agenten auf IDLE zurück (nach COMPLETED oder FAILED)."""
        self.transition(AgentState.IDLE, triggered_by="reset")
        self.entered_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Serialisiert den aktuellen Zustand."""
        return {
            "agent_id": self.agent_id,
            "current_state": self.current.value,
            "time_in_state_s": round(self.time_in_state(), 1),
            "total_transitions": len(self.history),
            "last_transition": self.history[-1].model_dump() if self.history else None,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Built-in Message Types (Convenience Constructors)
# ═══════════════════════════════════════════════════════════════════════════════

def offer(sender: str, good: str, quantity: float, price: float) -> AgentMessage:
    """Produzent → Markt: Angebot."""
    return AgentMessage(sender=sender, receiver="market", payload_type=PayloadType.OFFER,
                        content={"good": good, "quantity": quantity, "price": price})


def demand(sender: str, good: str, quantity: float, max_price: float) -> AgentMessage:
    """Konsument → Markt: Nachfrage."""
    return AgentMessage(sender=sender, receiver="market", payload_type=PayloadType.DEMAND,
                        content={"good": good, "quantity": quantity, "max_price": max_price})


def trade_confirmed(buyer: str, seller: str, good: str, quantity: float,
                    price: float) -> AgentMessage:
    """Markt → Beide Parteien: Handel bestätigt."""
    return AgentMessage(sender="market", receiver=f"{buyer},{seller}",
                        payload_type=PayloadType.TRADE,
                        content={"good": good, "quantity": quantity, "price": price,
                                 "total": quantity * price, "buyer": buyer, "seller": seller})


def bho_proof(contract_id: str, delta_eur: float, holds: bool) -> AgentMessage:
    """Z3-Service → Orchestrator: BHO-Beweis."""
    return AgentMessage(sender="z3", receiver="orch",
                        payload_type=PayloadType.BHO_PROOF if holds else PayloadType.BHO_VIOLATION,
                        content={"contract_id": contract_id, "delta_eur": delta_eur,
                                 "invariant_holds": holds})


def alert(severity: str, component: str, message: str) -> AgentMessage:
    """Monitor → Orchestrator: Eskalation."""
    return AgentMessage(sender="monitor", receiver="orch",
                        payload_type=PayloadType.ALERT,
                        content={"severity": severity, "component": component,
                                 "message": message}, priority=5)


# ═══════════════════════════════════════════════════════════════════════════════
# BaseAgent — Minimales Agenten-Skelett (ABM Foundation)
# ═══════════════════════════════════════════════════════════════════════════════

class BaseAgent:
    """Minimales Agenten-Skelett mit perceive→decide→act→update-Loop.

    Jeder Agent — ob Produzent, Konsument oder Z3-Checker — erbt von
    dieser Klasse. Sie stellt die StateMachine, den Message-Handler und
    den standardisierten Tick-Cycle bereit.

    Subklassen überschreiben:
      - perceive(env)   → sammelt Umgebungsdaten
      - decide()        → wählt Aktion basierend auf Wahrnehmung
      - act()           → führt die gewählte Aktion aus
      - update()        → aktualisiert internen Zustand

    Usage:
        class MyAgent(BaseAgent):
            def perceive(self, env): return {"price": env.get("price")}
            def decide(self):        return "buy" if self.perception["price"] < 10 else "wait"
            def act(self):           return offer(self.id, "WHEAT", 10, 5.0)
            def update(self):        self.state["trades"] += 1
    """

    def __init__(self, agent_id: str, initial_state: AgentState = AgentState.IDLE):
        self.id = agent_id
        self.sm = StateMachine(agent_id, initial_state)
        self.perception: Dict[str, Any] = {}
        self.state: Dict[str, Any] = {}       # Agent-spezifischer Zustand
        self.outbox: List[AgentMessage] = []  # Ausgehende Nachrichten
        self.inbox: List[AgentMessage] = []   # Eingehende Nachrichten (vom Bus)
        self.tick_count = 0
        self.decision_log: List[Dict] = []    # Entscheidungs-Historie

    def perceive(self, environment: Dict[str, Any]) -> Dict[str, Any]:
        """Sammelt Umgebungsdaten. Überschreiben in Subklasse."""
        self.perception = environment
        return self.perception

    def decide(self) -> str:
        """Wählt Aktion basierend auf self.perception. Überschreiben in Subklasse."""
        return "noop"

    def act(self) -> List[AgentMessage]:
        """Führt die gewählte Aktion aus. Überschreiben in Subklasse."""
        return []

    def update_internal_state(self):
        """Aktualisiert internen Zustand nach der Aktion. Überschreiben in Subklasse."""
        pass

    def tick(self, environment: Dict[str, Any]) -> List[AgentMessage]:
        """Führt einen vollständigen Tick-Cycle aus: perceive → decide → act → update."""
        self.tick_count += 1

        # 1. Perceive
        self.perceive(environment)

        # 2. Decide
        decision = self.decide()

        # 3. Act
        messages = self.act()

        # 4. Update
        self.update_internal_state()

        # Log decision
        self.decision_log.append({
            "tick": self.tick_count, "decision": decision,
            "messages_sent": len(messages),
            "state": self.sm.current.value,
        })

        self.outbox.extend(messages)
        return messages

    def receive(self, msg: AgentMessage):
        """Empfängt eine Nachricht vom Event-Bus."""
        self.inbox.append(msg)

    def to_dict(self) -> dict:
        """Serialisiert den Agenten-Zustand."""
        return {
            "id": self.id,
            "tick": self.tick_count,
            "state_machine": self.sm.to_dict(),
            "perception_keys": list(self.perception.keys()),
            "outbox_len": len(self.outbox),
            "inbox_len": len(self.inbox),
            "last_decision": self.decision_log[-1] if self.decision_log else None,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TickController — Deterministischer Event-Loop für Multi-Agenten-Systeme
# ═══════════════════════════════════════════════════════════════════════════════

class TickController:
    """Deterministischer Event-Loop für agentenbasierte Simulationen.

    Steuert die Reihenfolge, in der Agenten wahrnehmen und handeln.
    Garantiert reproduzierbare Abläufe durch feste Agenten-Ordnung
    und explizite Synchronisationspunkte.

    Phasen pro Tick:
      1. Alle Agenten nehmen Umgebung wahr (parallel möglich)
      2. Alle Agenten entscheiden (sequentiell, deterministisch)
      3. Alle Agenten handeln (sequentiell)
      4. Nachrichten werden zugestellt (Message-Passing)
      5. Agenten aktualisieren internen Zustand

    Usage:
        tc = TickController()
        tc.register(producer)
        tc.register(consumer)
        report = tc.run(cycles=100)
    """

    def __init__(self, seed: int = 42):
        self.agents: List[BaseAgent] = []
        self.environment: Dict[str, Any] = {}
        self.cycle = 0
        self.total_messages = 0
        self.history: List[Dict] = []

    def register(self, agent: BaseAgent):
        """Registriert einen Agenten im Controller."""
        self.agents.append(agent)

    def run(self, cycles: int = 100, environment: Dict[str, Any] = None) -> Dict:
        """Führt N Tick-Cycles aus.

        Args:
            cycles: Anzahl der Zyklen
            environment: Optionale Start-Umgebung (wird pro Tick aktualisiert)
        """
        if environment:
            self.environment = environment

        for _ in range(cycles):
            self.cycle += 1
            tick_msgs = 0

            # Phase 1+2+3: Jeder Agent durchläuft perceive→decide→act
            for agent in self.agents:
                env_for_agent = {
                    **self.environment,
                    "cycle": self.cycle,
                    "agent_count": len(self.agents),
                }
                msgs = agent.tick(env_for_agent)
                tick_msgs += len(msgs)

            # Phase 4: Message-Passing (Nachrichten zustellen)
            # Alle ausgehenden Nachrichten einsammeln
            all_outbox = []
            for agent in self.agents:
                all_outbox.extend(agent.outbox)
                agent.outbox.clear()

            # Zustellen: receiver bekommt Nachrichten
            for msg in all_outbox:
                for agent in self.agents:
                    if agent.id == msg.receiver or msg.receiver == "broadcast":
                        agent.receive(msg)

            # Phase 5: Update (bereits in agent.tick() via update_internal_state())

            self.total_messages += tick_msgs
            self.history.append({
                "cycle": self.cycle,
                "messages": tick_msgs,
                "agents_active": sum(1 for a in self.agents if a.outbox or a.inbox),
            })

        return {
            "cycles": self.cycle,
            "total_messages": self.total_messages,
            "agents": [a.to_dict() for a in self.agents],
            "history": self.history[-10:],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Surface ↔ Subsurface Protocol Extension (v3.0)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Message types for D01/D02/D03 diver communication via NATS JetStream.
# All messages carry TEE attestation hashes and follow the envelope pattern.
#
# Topic hierarchy:
#   agentx.settlement.zk_proof   — D01 → C09 (ZK settlement proofs)
#   agentx.forensic.repair       — D02 → C05 (historical DAG repair)
#   agentx.emergency.freeze      — C06 → D03 (freeze command)
#   agentx.emergency.rescue      — D03 → C01 (rescue confirmation)
#   agentx.crew.action           — Crew → EventBus
#   agentx.valhalla.honor        — Any → Valhalla

import hashlib as _hl
import json as _json
import time as _time
from dataclasses import dataclass as _dc, field as _field
from enum import Enum as _Enum
from typing import Any, Dict, List, Optional


PROTOCOL_VERSION_V3 = "v3.0-agentx"
MAX_TICK_DRIFT = 50
NATS_PREFIX = "agentx"


class SurfaceMsgType(_Enum):
    ZK_SETTLEMENT_PROOF = "zk_settlement_proof"
    FORENSIC_REPAIR = "forensic_repair"
    EMERGENCY_FREEZE = "emergency_freeze"
    EMERGENCY_RESCUE = "emergency_rescue"
    CREW_ACTION = "crew_action"
    VALHALLA_HONOR = "valhalla_honor"
    POST_MORTEM = "post_mortem"


TOPICS: Dict[SurfaceMsgType, str] = {
    SurfaceMsgType.ZK_SETTLEMENT_PROOF: f"{NATS_PREFIX}.settlement.zk_proof",
    SurfaceMsgType.FORENSIC_REPAIR:      f"{NATS_PREFIX}.forensic.repair",
    SurfaceMsgType.EMERGENCY_FREEZE:     f"{NATS_PREFIX}.emergency.freeze",
    SurfaceMsgType.EMERGENCY_RESCUE:     f"{NATS_PREFIX}.emergency.rescue",
    SurfaceMsgType.CREW_ACTION:          f"{NATS_PREFIX}.crew.action",
    SurfaceMsgType.VALHALLA_HONOR:       f"{NATS_PREFIX}.valhalla.honor",
    SurfaceMsgType.POST_MORTEM:          f"{NATS_PREFIX}.emergency.post_mortem",
}


@_dc
class SurfaceEnvelope:
    """NATS message envelope for surface↔subsurface communication."""
    protocol_version: str = PROTOCOL_VERSION_V3
    msg_type: str = ""
    msg_id: str = ""
    source: str = ""
    target: str = ""
    tick: int = 0
    created_at: str = ""
    payload_json: str = ""
    tee_attestation: str = ""
    signature: str = ""

    @classmethod
    def wrap(cls, msg_type: SurfaceMsgType, source: str, target: str,
             payload: Any, tick: int = 0) -> "SurfaceEnvelope":
        payload_json = _json.dumps(
            payload if isinstance(payload, dict) else payload.__dict__,
            sort_keys=True, default=str,
        )
        msg_id = _hl.sha256(
            f"{msg_type.value}{source}{target}{tick}{payload_json}".encode()
        ).hexdigest()[:16]
        return cls(
            msg_type=msg_type.value, msg_id=msg_id,
            source=source, target=target,
            tick=tick or int(_time.time()),
            created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            payload_json=payload_json,
            tee_attestation=_hl.sha256(payload_json.encode()).hexdigest()[:32],
            signature=_hl.sha256(f"{msg_id}{payload_json}".encode()).hexdigest()[:32],
        )

    def topic(self) -> str:
        try:
            return TOPICS.get(SurfaceMsgType(self.msg_type), f"{NATS_PREFIX}.unknown")
        except ValueError:
            return f"{NATS_PREFIX}.unknown"


@_dc
class RangeProofSettlement:
    """D01 → C09: ZK proof with sliding-window range proof.

    Surface never waits: event_tick marks when settlement was initiated,
    proof_tick marks when D01 completed the ZK proof. C09 verifies:
      proof_tick − event_tick ≤ MAX_TICK_DRIFT (50 ticks)
    Nullifier uniqueness prevents double-spend regardless of drift.
    """
    event_tick: int = 0
    proof_tick: int = 0
    proof_type: str = "Groth16_BN254"
    proof: Dict[str, List[str]] = _field(default_factory=dict)
    public_inputs: Dict[str, str] = _field(default_factory=dict)
    nullifier_hash: str = ""
    commitment_hash: str = ""
    settlement_net_eur_cents: int = 0
    valhalla_stamp: str = ""
    tee_quote: str = ""

    def within_drift(self, current_tick: int, max_drift: int = MAX_TICK_DRIFT) -> bool:
        return 0 <= (current_tick - self.event_tick) <= max_drift


@_dc
class ForensicRepair:
    """D02 → C05: Historical Merkle-DAG repair with ZK reconciliation proof."""
    incident_id: str = ""
    corrupted_block_height: int = 0
    invalid_state_root: str = ""
    healed_state_root: str = ""
    zk_reconciliation_proof: str = ""
    bho_invariant_status: str = ""
    forensic_signature: str = ""
    valhalla_stamp: str = ""


@_dc
class EmergencyFreeze:
    """C06 → D03: Freeze escrow and bridges. Requires ≥ 2 multi-sig approvals."""
    incident_id: str = ""
    trigger_reason: str = ""
    freeze_targets: List[str] = _field(default_factory=list)
    severity: str = "CRITICAL"
    multi_sig_approvals: List[str] = _field(default_factory=list)
    detecting_tick: int = 0

    def has_quorum(self, threshold: int = 2) -> bool:
        return len(self.multi_sig_approvals) >= threshold


@_dc
class RescueConfirmation:
    """D03 → C01: Funds rescued to L1 backup vault."""
    incident_id: str = ""
    fund_eur: float = 0.0
    l1_target: str = "L1_BACKUP_VAULT"
    l1_tx_hash: str = ""
    rescue_tick: int = 0


@_dc
class CrewAction:
    """Crew decision broadcast to EventBus."""
    agent_id: str = ""
    role: str = ""
    action: str = ""
    gas_balance: float = 0.0
    block_height: int = 0
    reason: str = ""
    latency_us: float = 0.0


@_dc
class ValhallaHonor:
    """Credit honor to anonymous Valhalla stamp."""
    valhalla_stamp: str = ""
    honor_earned: int = 0
    reason: str = ""
    source_incident: str = ""


# ─── Demo ───────────────────────────────────────────────────────────────────

def demo_surface_protocol():
    """Route demo messages through the envelope → topic pipeline."""
    W = 70
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  📡 SURFACE ↔ SUBSURFACE PROTOCOL".center(W - 2) + "█")
    print("█" + f"  v{PROTOCOL_VERSION_V3} | Δt_max={MAX_TICK_DRIFT} ticks".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W + "\n")

    tick = int(_time.time())

    # D01 → C09: ZK Settlement with Range-Proof
    zk = RangeProofSettlement(
        event_tick=tick - 12, proof_tick=tick,  # 12 tick drift (within 50)
        proof_type="Groth16_BN254",
        proof={"pi_a": ["0xabc"], "pi_b": [["0xdef", "0x123"]], "pi_c": ["0x456"]},
        public_inputs={"state_root_before": "0xaaa", "state_root_after": "0xbbb",
                       "nullifier_hash": "0x7e3a", "commitment_hash": "0x12ab",
                       "settlement_net_eur": "2500000"},
        nullifier_hash="0x7e3a", commitment_hash="0x12ab",
        settlement_net_eur_cents=2500000, valhalla_stamp="did:valhalla:7e3a",
    )
    env = SurfaceEnvelope.wrap(SurfaceMsgType.ZK_SETTLEMENT_PROOF, "D01", "C09", zk, tick)
    drift_ok = "✅" if zk.within_drift(tick) else "❌ DRIFT"
    print(f"  {env.source}→{env.target} {env.msg_type:<30} topic={env.topic()}")
    print(f"     event_tick={zk.event_tick} proof_tick={zk.proof_tick} Δ={tick - zk.event_tick} {drift_ok}")

    # D02 → C05: Forensic Repair
    fr = ForensicRepair(
        incident_id="INC-DAG-004200", corrupted_block_height=4200,
        invalid_state_root="0xTAMPERED", healed_state_root="0xHEALED",
        zk_reconciliation_proof="0xZK_PROOF", bho_invariant_status="42/42_CHECKS_VERIFIED",
        forensic_signature="0xSIG", valhalla_stamp="did:valhalla:deep_guardian",
    )
    env2 = SurfaceEnvelope.wrap(SurfaceMsgType.FORENSIC_REPAIR, "D02", "C05", fr, tick)
    print(f"  {env2.source}→{env2.target} {env2.msg_type:<30} topic={env2.topic()}")

    # C06 → D03: Emergency Freeze (with quorum check)
    ef = EmergencyFreeze(
        incident_id="EMERG-0042", trigger_reason="BHO_VIOLATION_Δ=0.03€",
        freeze_targets=["ESCROW", "BRIDGE_ETH"],
        multi_sig_approvals=["kaemmerer_mueller", "bauleiter_schmidt"],
        detecting_tick=tick,
    )
    env3 = SurfaceEnvelope.wrap(SurfaceMsgType.EMERGENCY_FREEZE, "C06", "D03", ef, tick)
    q = "✅" if ef.has_quorum(2) else "❌ NO_QUORUM"
    print(f"  {env3.source}→{env3.target} {env3.msg_type:<30} topic={env3.topic()} quorum={q}")

    # Crew action
    ca = CrewAction(agent_id="C03", role="COMPLIANCE", action="PROCEED",
                    gas_balance=9.99, block_height=42, reason="SIG_OK")
    env4 = SurfaceEnvelope.wrap(SurfaceMsgType.CREW_ACTION, "C03", "EventBus", ca, tick)
    print(f"  {env4.source}→{env4.target} {env4.msg_type:<30} topic={env4.topic()} action={ca.action}")

    # Valhalla honor
    vh = ValhallaHonor(valhalla_stamp="did:valhalla:7e3a", honor_earned=50,
                       reason="ZK_PROOF_VALID", source_incident="INC-0042")
    env5 = SurfaceEnvelope.wrap(SurfaceMsgType.VALHALLA_HONOR, "C09", "Valhalla", vh, tick)
    print(f"  {env5.source}→{env5.target} {env5.msg_type:<30} topic={env5.topic()} honor=+{vh.honor_earned}")

    print(f"\n  ✅ Protocol routing: 5 messages, 7 topics defined")
    print(f"     Surface tick: {tick} | Drift window: ±{MAX_TICK_DRIFT} ticks\n")
