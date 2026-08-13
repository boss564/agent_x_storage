"""P02 — Zugführer State-Conflict: state inconsistency resolution."""

from .base import PanzergrenadierAgent


class P02StateConflictLeader(PanzergrenadierAgent):
    def __init__(self):
        super().__init__("P02")

    def _requires_dismount(self, event):
        return event.get("state_conflict", False)

    async def _isolate_and_reconcile(self, event):
        event["state_conflict_resolved"] = True
        return True

    def _note(self):
        return "State conflict resolved"
