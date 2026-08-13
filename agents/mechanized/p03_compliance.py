"""P03 — Zugführer Compliance: §48b exceptions and regulatory edge cases."""

from .base import PanzergrenadierAgent


class P03ComplianceLeader(PanzergrenadierAgent):
    def __init__(self):
        super().__init__("P03")

    def _requires_dismount(self, event):
        return event.get("compliance_edge", False)

    async def _isolate_and_reconcile(self, event):
        event["compliance_cleared"] = True
        return True

    def _note(self):
        return "Compliance edge cleared"
