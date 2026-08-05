"""
Lightweight In-Process Event Bus for Agent X B2G.

In production: NATS JetStream or Redis PubSub.
For MVP/bootstrap: in-process publish/subscribe with JSON logging.
Every message is logged to an append-only audit file.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class EventBus:
    """In-process pub/sub with audit logging."""

    def __init__(self, audit_log: Path | None = None):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._audit_log = audit_log or Path("logs/b2g_event_bus.jsonl")
        self._audit_log.parent.mkdir(parents=True, exist_ok=True)
        self._message_count = 0

    def subscribe(self, subject: str, callback: Callable) -> None:
        self._subscribers[subject].append(callback)

    def publish(self, subject: str, payload: dict[str, Any]) -> None:
        self._message_count += 1
        envelope = {
            "msg_id": self._message_count,
            "subject": subject,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        # Audit log
        with open(self._audit_log, "a") as f:
            f.write(json.dumps(envelope, default=str) + "\n")

        # Deliver to subscribers
        for callback in self._subscribers.get(subject, []):
            try:
                callback(envelope)
            except Exception as exc:
                print(f"  [EventBus] ERROR in subscriber {subject}: {exc}")

    @property
    def message_count(self) -> int:
        return self._message_count
