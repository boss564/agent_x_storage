# agents_b2g/shadow/subagents/lifecycle_state_engine.py
"""
Agent 18.1.1 — LifecycleStateEngine

Deterministischer Zustandsautomat für den Shadow Contract.
Steuert Übergänge: CREATED → FUNDED → ACTIVE → SETTLED
mit DISPUTED als Querzustand (Freeze).
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger("LifecycleStateEngine")


class ContractState(Enum):
    CREATED = "CREATED"       # Vertrag angelegt, noch nicht finanziert
    FUNDED = "FUNDED"         # SEPA-Gelder eingegangen, EURe gemintet
    ACTIVE = "ACTIVE"         # Bauphase, Milestones werden freigegeben
    PAUSED = "PAUSED"         # Angehalten (Dispute, Force Majeure)
    DISPUTED = "DISPUTED"     # Mängelrüge aktiv, Tranchen eingefroren
    SETTLED = "SETTLED"       # Alle Milestones bezahlt, Retention läuft
    COMPLETED = "COMPLETED"   # Retention abgelaufen, Projekt beendet


# Erlaubte Übergänge
ALLOWED_TRANSITIONS = {
    ContractState.CREATED:    [ContractState.FUNDED],
    ContractState.FUNDED:     [ContractState.ACTIVE, ContractState.PAUSED],
    ContractState.ACTIVE:     [ContractState.SETTLED, ContractState.DISPUTED, ContractState.PAUSED],
    ContractState.PAUSED:     [ContractState.ACTIVE, ContractState.DISPUTED, ContractState.SETTLED],
    ContractState.DISPUTED:   [ContractState.ACTIVE, ContractState.SETTLED],
    ContractState.SETTLED:    [ContractState.COMPLETED],
    ContractState.COMPLETED:  [],  # Endzustand
}


class LifecycleStateEngine:
    """Subagent 18.1.1: Zustandsautomat für VOB Shadow Contracts."""

    def __init__(self):
        self.current_state = ContractState.CREATED
        self.state_history: list[Dict[str, Any]] = []
        self._log_transition(None, ContractState.CREATED)

    def transition_to(self, new_state: ContractState, reason: str = "") -> bool:
        """
        Führt einen Zustandsübergang durch. Validiert gegen erlaubte Transitionen.

        Returns:
            True wenn Transition erlaubt und ausgeführt, False bei Regelverstoß.
        """
        if new_state not in ALLOWED_TRANSITIONS.get(self.current_state, []):
            logger.error(
                f"Unerlaubte Transition: {self.current_state.value} → {new_state.value}. "
                f"Erlaubt: {[s.value for s in ALLOWED_TRANSITIONS.get(self.current_state, [])]}"
            )
            return False

        old = self.current_state
        self.current_state = new_state
        self._log_transition(old, new_state, reason)
        logger.info(f"State: {old.value} → {new_state.value}" + (f" ({reason})" if reason else ""))
        return True

    def can_transition_to(self, target: ContractState) -> bool:
        """Prüft, ob ein Übergang erlaubt wäre, ohne ihn auszuführen."""
        return target in ALLOWED_TRANSITIONS.get(self.current_state, [])

    def is_terminal(self) -> bool:
        return self.current_state == ContractState.COMPLETED

    def is_frozen(self) -> bool:
        return self.current_state in (ContractState.PAUSED, ContractState.DISPUTED)

    def get_state(self) -> Dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "is_terminal": self.is_terminal(),
            "is_frozen": self.is_frozen(),
            "history_length": len(self.state_history),
            "last_transition": self.state_history[-1] if self.state_history else None,
        }

    def _log_transition(self, old: Optional[ContractState], new: ContractState, reason: str = ""):
        self.state_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "from": old.value if old else None,
            "to": new.value,
            "reason": reason,
        })
