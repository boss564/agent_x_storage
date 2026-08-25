"""W39-A4-S2 — append-only GoBD WORM JSONL writer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class AuditWriteError(OSError):
    """Raised when WORM append fails — fail-closed for Agent 4."""


@dataclass(frozen=True)
class WORMAppendResult:
    line_number: int
    entry_hash: str


class WORMWriter:
    subagent_id = "W39-A4-S2"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def line_count(self) -> int:
        if not self.path.is_file():
            return 0
        with self.path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def last_entry_hash(self, *, genesis: str) -> str:
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return genesis
        last_line = ""
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last_line = line
        if not last_line:
            return genesis
        try:
            data = json.loads(last_line)
        except json.JSONDecodeError as exc:
            raise AuditWriteError(f"WORM chain corrupt: invalid JSON at {self.path}") from exc
        entry_hash = data.get("entry_hash")
        if not isinstance(entry_hash, str) or not entry_hash:
            raise AuditWriteError(f"WORM chain corrupt: missing entry_hash at {self.path}")
        return entry_hash

    def append_entry(self, entry: Mapping[str, Any]) -> WORMAppendResult:
        line = json.dumps(dict(entry), sort_keys=True, default=str)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
        except OSError as exc:
            raise AuditWriteError(f"WORM append failed: {self.path}: {exc}") from exc
        return WORMAppendResult(
            line_number=self.line_count(),
            entry_hash=str(entry.get("entry_hash", "")),
        )

    def verify_chain(self, *, genesis: str) -> tuple[bool, str | None]:
        if not self.path.is_file():
            return True, None
        prev = genesis
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return False, f"line {line_no}: invalid JSON"
                if entry.get("prev_hash") != prev:
                    return False, f"line {line_no}: prev_hash mismatch"
                body = {k: v for k, v in entry.items() if k not in {"prev_hash", "entry_hash"}}
                from agents_b2g.ethical_boundary.subagents.audit.audit_trail_hasher import (
                    AuditTrailHasher,
                )

                expected = AuditTrailHasher().hash_entry(prev, body)
                actual = entry.get("entry_hash")
                if actual != expected:
                    return False, f"line {line_no}: entry_hash mismatch"
                prev = str(actual)
        return True, None
