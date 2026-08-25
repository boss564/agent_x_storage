"""JSONLogger and _safe_call for Wave 38 diagnostic agents."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agents_b2g.diagnostic.config import DiagnosticConfig


class JSONLogger:
    """Structured JSONL logging — no print()."""

    def __init__(self, agent_name: str = "wave38", user_id: str = "default"):
        self.agent_name = agent_name
        self.user_id = user_id
        self.log_path = (
            DiagnosticConfig.LOG_DIR
            / f"wave38_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, msg: str, **extra: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "agent": self.agent_name,
            "user_id": self.user_id,
            "message": msg,
            **extra,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def info(self, msg: str, **kw: Any) -> None:
        self._write("INFO", msg, **kw)

    def warn(self, msg: str, **kw: Any) -> None:
        self._write("WARN", msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._write("ERROR", msg, **kw)


def _safe_call(
    logger: JSONLogger,
    node: str,
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """try/except wrapper with bounded retries."""
    job_id = str(uuid.uuid4())[:12]
    start = time.monotonic()
    logger.info(f"[{node}] started", job_id=job_id)
    last: Exception | None = None
    for attempt in range(1, DiagnosticConfig.MAX_RETRIES + 1):
        try:
            result = fn(*args, **kwargs)
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.info(
                f"[{node}] completed",
                job_id=job_id,
                duration_ms=duration_ms,
                attempt=attempt,
            )
            if isinstance(result, dict) and result.get("status") in {
                "started",
                "completed",
                "failed",
                "skipped",
            }:
                result.setdefault("job_id", job_id)
                return result
            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [result] if result is not None else [],
                "error": None,
                "logs": [],
            }
        except Exception as exc:  # noqa: BLE001 — agent boundary
            last = exc
            logger.warn(f"[{node}] attempt {attempt} failed: {exc}", job_id=job_id)
            if attempt < DiagnosticConfig.MAX_RETRIES:
                time.sleep(DiagnosticConfig.RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
    logger.error(f"[{node}] failed: {last}", job_id=job_id)
    return {
        "status": "failed",
        "job_id": job_id,
        "artifacts": [],
        "error": str(last),
        "logs": [{"level": "ERROR", "message": str(last)}],
    }
