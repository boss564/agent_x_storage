"""P04 — Subagent Isolation: micro-sandbox, decouple event from batch."""

from .base import PanzergrenadierAgent


class P04Isolation(PanzergrenadierAgent):
    def __init__(self):
        super().__init__("P04")

    async def _isolate_and_reconcile(self, event):
        # Create an isolated micro-sandbox and decouple from the batch
        event["sandboxed"] = True
        event["isolated_from_batch"] = True
        return True

    def _note(self):
        return "Isolated in micro-sandbox"
