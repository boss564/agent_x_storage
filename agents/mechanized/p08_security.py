"""P08 — Subagent Sicherung: sandbox monitoring + tamper-proof audit."""

from .base import PanzergrenadierAgent


class P08Security(PanzergrenadierAgent):
    def __init__(self):
        super().__init__("P08")
        self.attack_aborts = 0

    async def _isolate_and_reconcile(self, event):
        # Fail-secure: abort on attack suspicion
        if event.get("attack_suspected"):
            self.attack_aborts += 1
            return False  # not cleared — fail secure
        event["audit_logged"] = True
        return True

    def _note(self):
        return "Tamper-proof audit logged"

    def stats(self):
        s = super().stats()
        s["attack_aborts"] = self.attack_aborts
        return s
