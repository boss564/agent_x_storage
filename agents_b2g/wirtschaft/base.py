"""Wirtschaftsagenten foundation (Baustein 1).

Extends agents_b2g.protocol.BaseAgent with the five base subagent modules
from the 9-Wirtschaftsagenten design: StateKeeper, GasFrictionMonitor,
LogSubagent (WORM), CryptoModule, MessageBus (addressed topics).

Foundation only. Competence-barrier ENFORCEMENT (Baustein 2), the nine
concrete agents (Baustein 3), market routing via
agents.surface.PredictiveHealthRouter (Baustein 4), and the full
VALHALLA_DRAIN state machine are deliberately deferred. No parallel
foundation to protocol.BaseAgent -- this is a subclass.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from agents_b2g.protocol import AgentState, BaseAgent


# --- Competence classes (data only; enforcement is Baustein 2) ----------

class KompetenzKlasse(str, Enum):
    KAPITAL = "A"        # Kapital & Liquiditaet
    AUSFUEHRUNG = "B"    # Ausfuehrung & Abwicklung
    GOVERNANCE = "C"     # Governance & Risiko


@dataclass
class KompetenzProfil:
    """Separation-of-powers profile. Baustein 2 adds enforcement hooks."""
    klasse: Optional[KompetenzKlasse] = None
    exklusive_rechte: List[str] = field(default_factory=list)
    defizite: List[str] = field(default_factory=list)
    freigabe_pfad: Optional[KompetenzKlasse] = None
    # Baustein 2: rights that need prior approval + per-deficit routing
    genehmigungspflichtig: List[str] = field(default_factory=list)
    defizit_routing: Dict[str, KompetenzKlasse] = field(default_factory=dict)

    def needs_freigabe(self, aktion: str) -> bool:
        """True if aktion is a deficit OR an approval-required right."""
        return aktion in self.defizite or aktion in self.genehmigungspflichtig

    def freigabe_klasse_fuer(self, aktion: str) -> Optional[KompetenzKlasse]:
        """Resolve the class that must approve/handle aktion."""
        return self.defizit_routing.get(aktion, self.freigabe_pfad)


# --- StateKeeper -----------------------------------------------------------

class StateKeeper:
    """Local economic state on top of BaseAgent.state. Decimal balances,
    no global objects (BHO zero-sum requires Decimal arithmetic)."""

    def __init__(self, state: Dict[str, Any],
                 initial_balances: Optional[Dict[str, Any]] = None):
        self._state = state
        self._state.setdefault("balances", {})
        self._state.setdefault("tx_history", [])
        if initial_balances:
            for token, amount in initial_balances.items():
                self._state["balances"][token] = Decimal(str(amount))

    def credit(self, token: str, amount: Any) -> Decimal:
        amt = Decimal(str(amount))
        b = self._state["balances"]
        b[token] = b.get(token, Decimal("0")) + amt
        self._state["tx_history"].append(
            {"op": "credit", "token": token, "amount": str(amt)})
        return b[token]

    def debit(self, token: str, amount: Any) -> Decimal:
        amt = Decimal(str(amount))
        b = self._state["balances"]
        current = b.get(token, Decimal("0"))
        if current < amt:
            raise ValueError(
                f"insufficient balance {token}: have {current}, need {amt}")
        b[token] = current - amt
        self._state["tx_history"].append(
            {"op": "debit", "token": token, "amount": str(amt)})
        return b[token]

    def balance(self, token: str) -> Decimal:
        return self._state["balances"].get(token, Decimal("0"))

    def balances(self) -> Dict[str, Decimal]:
        return dict(self._state["balances"])


# --- GasFrictionMonitor -----------------------------------------------------

class GasFrictionMonitor:
    """Deducts G_tx gas per sent message. At 0 -> on_depleted hook
    (VALHALLA_DRAIN wiring lands in a later Baustein)."""

    def __init__(self, tank_capacity: float, g_tx: float = 1.0,
                 on_depleted: Optional[Callable[[], None]] = None):
        self.tank_capacity = float(tank_capacity)
        self.gas = float(tank_capacity)
        self.g_tx = float(g_tx)
        self.on_depleted = on_depleted
        self.drained = False

    def deduct(self, n_messages: int = 1) -> bool:
        # The message that brings gas to exactly 0 is still allowed;
        # everything after is blocked until refuel.
        if self.drained:
            return False
        cost = self.g_tx * n_messages
        if self.gas < cost:
            self.gas = 0.0
            self.drained = True
            if self.on_depleted:
                self.on_depleted()
            return False
        self.gas -= cost
        if self.gas <= 0.0:
            self.gas = 0.0
            self.drained = True
            if self.on_depleted:
                self.on_depleted()
        return True

    def refuel(self, amount: float) -> None:
        self.gas = min(self.tank_capacity, self.gas + float(amount))
        if self.gas > 0.0:
            self.drained = False


# --- WormLog (LogSubagent) --------------------------------------------------

class WormLog:
    """Append-only, hash-chained WORM audit log (tamper-evident).
    Same integrity pattern as finale/subagents/audit_trail.py."""

    GENESIS = "0" * 64

    def __init__(self):
        self._entries: List[dict] = []
        self._last_hash = self.GENESIS

    @staticmethod
    def _hash_entry(entry: dict) -> str:
        canonical = {k: v for k, v in entry.items() if k != "hash"}
        blob = json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def append(self, action: str, payload: Optional[Dict[str, Any]] = None) -> dict:
        entry = {
            "seq": len(self._entries),
            "ts": time.time(),
            "action": action,
            "payload": payload or {},
            "prev_hash": self._last_hash,
        }
        entry["hash"] = self._hash_entry(entry)
        self._last_hash = entry["hash"]
        self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        prev = self.GENESIS
        for e in self._entries:
            if e["prev_hash"] != prev:
                return False
            if self._hash_entry(e) != e["hash"]:
                return False
            prev = e["hash"]
        return True

    @property
    def entries(self) -> List[dict]:
        return list(self._entries)   # copy: WORM, no external mutation

    def __len__(self) -> int:
        return len(self._entries)


# --- CryptoModule -----------------------------------------------------------

class CryptoModule:
    """Optional message integrity/signing. SHA-256 digest now; real ECDSA
    via bunker/hsm_adapter.UnifiedPKCS11HSM attaches later."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._signer: Optional[Callable[[Any], str]] = None

    def digest(self, payload: Dict[str, Any]) -> Optional[str]:
        if not self.enabled:
            return None
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def sign(self, payload: Dict[str, Any]) -> Optional[str]:
        if not self.enabled:
            return None
        if self._signer is not None:
            return self._signer(payload)
        return self.digest(payload)   # Baustein 1 fallback: digest as pseudo-sig

    def attach_signer(self, signer: Callable[[Any], str]) -> None:
        self._signer = signer


# --- MessageBus -------------------------------------------------------------

class MessageBus:
    """Addressed P2P messaging. Topic: agent.<sender>.<target>.<kind>.

    transport=None -> record-only (loopback/tests); inject NATS in
    Baustein 4. A market dispatcher would be new there, not here."""

    def __init__(self, agent_id: str,
                 transport: Optional[Callable[[dict], None]] = None):
        self.agent_id = agent_id
        self.transport = transport
        self.published: List[dict] = []

    def topic(self, target: str, kind: str = "request") -> str:
        return f"agent.{self.agent_id}.{target}.{kind}"

    def publish(self, target: str, payload: Dict[str, Any],
                kind: str = "request") -> dict:
        envelope = {
            "topic": self.topic(target, kind),
            "sender": self.agent_id,
            "target": target,
            "kind": kind,
            "payload": payload,
        }
        self.published.append(envelope)
        if self.transport is not None:
            self.transport(envelope)
        return envelope


# --- WirtschaftAgent --------------------------------------------------------

class WirtschaftAgent(BaseAgent):
    """BaseAgent + the five economic base modules (composition, not
    inheritance). Economic messaging goes through send() (gas -> topic ->
    sign -> WORM). Bridging message_bus envelopes to protocol.AgentMessage
    and PredictiveHealthRouter is Baustein 4."""

    def __init__(self, agent_id: str,
                 klasse: Optional[KompetenzKlasse] = None,
                 gas_tank: float = 100.0,
                 g_tx: float = 1.0,
                 crypto_enabled: bool = True,
                 initial_balances: Optional[Dict[str, Any]] = None,
                 initial_state: AgentState = AgentState.IDLE):
        super().__init__(agent_id, initial_state)
        self.competence = KompetenzProfil(klasse=klasse) if klasse is not None else None
        self.state_keeper = StateKeeper(self.state, initial_balances=initial_balances)
        self.gas_monitor = GasFrictionMonitor(
            tank_capacity=gas_tank, g_tx=g_tx, on_depleted=self._enter_drain)
        self.worm_log = WormLog()
        self.crypto = CryptoModule(enabled=crypto_enabled)
        self.message_bus = MessageBus(agent_id)
        self._drained = False
        self._freigaben: set = set()   # granted approvals (Baustein 2)

    # -- VALHALLA_DRAIN hook (full state machine = later Baustein) --

    def _enter_drain(self) -> None:
        self._drained = True
        self.worm_log.append("GAS_DEPLETED", {"agent": self.id})

    @property
    def drained(self) -> bool:
        return self._drained

    def send(self, target: str, payload: Dict[str, Any],
             kind: str = "request") -> Optional[dict]:
        """Economic send: gas deduction -> topic addressing -> sign -> WORM."""
        if self._drained:
            self.worm_log.append("SEND_BLOCKED_DRAIN", {"target": target})
            return None
        if not self.gas_monitor.deduct(1):
            self.worm_log.append("SEND_BLOCKED_NO_GAS", {"target": target})
            return None
        envelope = self.message_bus.publish(target, payload, kind)
        if self.crypto.enabled:
            envelope["digest"] = self.crypto.digest(payload)
            envelope["signature"] = self.crypto.sign(payload)
        self.worm_log.append("SEND", {"topic": envelope["topic"], "kind": kind})
        return envelope

    # --- Baustein 2: Funktionsschranken (Gewaltenteilung) -----------------

    def may(self, aktion: str) -> bool:
        """Default-deny: allowed only if aktion is an explicit exclusive right."""
        if self.competence is None:
            return False
        return aktion in self.competence.exklusive_rechte

    def needs_freigabe(self, aktion: str) -> bool:
        if self.competence is None:
            return False
        return self.competence.needs_freigabe(aktion)

    def grant_freigabe(self, aktion: str) -> None:
        """Record an approval issued by the responsible class.
        Distributed approval-message handling lands in Baustein 3."""
        self._freigaben.add(aktion)

    def request_freigabe(self, aktion: str,
                         payload: Optional[Dict[str, Any]] = None) -> Optional[dict]:
        """Send an approval/delegation request to the responsible class."""
        if self.competence is None:
            return None
        target_klasse = self.competence.freigabe_klasse_fuer(aktion)
        if target_klasse is None:
            self.worm_log.append("FREIGABE_NO_PATH", {"aktion": aktion})
            return None
        return self.send(
            target=f"klasse.{target_klasse.value}",
            payload={
                "typ": "FREIGABE_REQUEST",
                "aktion": aktion,
                "requester": self.id,
                "requester_klasse": (self.competence.klasse.value
                                     if self.competence.klasse else None),
                "details": payload or {},
            },
            kind="request",
        )

    def execute(self, aktion: str,
                payload: Optional[Dict[str, Any]] = None) -> dict:
        """Gewaltenteilung gate: execute, request approval, or delegate."""
        payload = payload or {}
        if self.competence is None:
            self.worm_log.append("EXECUTE_BLOCKED",
                                 {"aktion": aktion, "grund": "NO_PROFILE"})
            return {"status": "blocked", "aktion": aktion,
                    "grund": "no_competence_profile"}
        if self.may(aktion):
            needs = self.competence.needs_freigabe(aktion)
            if needs and aktion not in self._freigaben:
                freigabe = self.request_freigabe(aktion, payload)
                self.worm_log.append("EXECUTE_PENDING_FREIGABE", {"aktion": aktion})
                return {"status": "freigabe_required", "aktion": aktion,
                        "freigabe_request": freigabe}
            self.worm_log.append("EXECUTE",
                                 {"aktion": aktion, "mit_freigabe": needs})
            return {"status": "executed", "aktion": aktion, "mit_freigabe": needs}
        # Not an exclusive right -> deficit -> delegate to responsible class
        freigabe = self.request_freigabe(aktion, payload)
        self.worm_log.append("EXECUTE_DELEGATED", {"aktion": aktion})
        return {"status": "delegated", "aktion": aktion,
                "freigabe_request": freigabe}

    def tick(self, environment: Dict[str, Any]) -> List[Any]:
        outgoing = super().tick(environment)
        self.worm_log.append("TICK", {"tick": self.tick_count})
        return outgoing

    def receive(self, msg: Any) -> None:
        super().receive(msg)
        try:
            topic = getattr(msg, "topic", None) or type(msg).__name__
            self.worm_log.append("RECEIVE", {"topic": str(topic)})
        except Exception:
            pass   # logging must never break the receive path

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["balances"] = {k: str(v) for k, v in self.state_keeper.balances().items()}
        base["gas"] = self.gas_monitor.gas
        base["drained"] = self._drained
        return base
