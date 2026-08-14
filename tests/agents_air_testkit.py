"""Shared air-layer test fixtures (MockBus, MockLedger)."""


class MockBus:
    """In-memory EventBus double."""

    def __init__(self):
        self.topics = []
        self._events = []  # (topic, payload)

    def publish(self, topic, payload):
        self.topics.append(topic)
        self._events.append((topic, payload))

    def payloads(self, topic):
        return [p for t, p in self._events if t == topic]

    def subscribe(self, topic, handler):
        pass  # stub for AWACSDatalink.attach


class MockLedger:
    """Double-entry ledger double.

    A06 books the destruction leg (debit + quarantine liability); A07 books
    the compensation leg (receivable + paid). Each leg is a balanced pair so
    the sum stays zero regardless of which agent booked.
    """

    def __init__(self):
        self.entries = []  # (dedup_key, amount, reason)
        self._compensations = 0

    def book_neutralization(self, dedup_key, state_root, reason):
        # A06: destruction (debit) + quarantine liability (credit).
        self.entries.append((dedup_key, +1.0, reason))
        self.entries.append((dedup_key, -1.0, "quarantine_liability"))

    def book_compensation(self, dedup_key, compensation_id, reason):
        # A07: compensation receivable (debit) + paid (credit).
        self._compensations += 1
        self.entries.append((dedup_key, +1.0, f"comp_recv:{reason}"))
        self.entries.append((dedup_key, -1.0, f"comp_paid:{reason}"))

    def is_balanced(self):
        return abs(sum(a for _, a, _ in self.entries)) < 1e-9

    def compensation_count(self):
        return self._compensations
