"""W39-A5-S1 — analyze output-side execution calls and audit-linked routes."""

from __future__ import annotations

from typing import Any, Mapping

from agents_b2g.ethical_boundary.subagents.integrity.types import ExecutionCallRecord


class ExecutionCallAnalyzer:
    subagent_id = "W39-A5-S1"

    _OUTPUT_FIELDS: tuple[str, ...] = (
        "execution_calls",
        "output_execution_calls",
        "audit_execution_calls",
        "routed_outputs",
    )

    def analyze(self, payload: Mapping[str, Any]) -> tuple[ExecutionCallRecord, ...]:
        records: list[ExecutionCallRecord] = []
        for field in self._OUTPUT_FIELDS:
            raw_items = payload.get(field)
            if raw_items is None:
                continue
            if isinstance(raw_items, Mapping):
                raw_items = [raw_items]
            if not isinstance(raw_items, (list, tuple)):
                continue
            for index, item in enumerate(raw_items):
                if not isinstance(item, Mapping):
                    continue
                purpose = str(item.get("purpose") or item.get("action") or "").upper()
                records.append(
                    ExecutionCallRecord(
                        purpose=purpose,
                        raw=item,
                        source_field=field,
                        index=index,
                    )
                )
        return tuple(records)
