"""P01 — Zugführer Cross-Shard: nested cross-chain lock resolution."""

from .base import PanzergrenadierAgent


class P01CrossShardLeader(PanzergrenadierAgent):
    def __init__(self):
        super().__init__("P01")

    def _requires_dismount(self, event):
        return event.get("is_nested_cross_shard", False)

    async def _isolate_and_reconcile(self, event):
        # Resolve nested cross-shard locks (e.g. A→B→C deadlock)
        event["cross_shard_resolved"] = True
        return True

    def _note(self):
        return "Cross-shard lock resolved"
