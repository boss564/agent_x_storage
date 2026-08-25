"""JSONLogger and _safe_call for Wave 40 resilience agents."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from agents_b2g.resilience.config import ResilienceConfig


class JSONLogger:
    """Structured JSONL logging — no print()."""

    def __init__(self, agent_name: str = "wave40", user_id: str = "default"):
        self.agent_name = agent_name
        self.user_id = user_id
        self.log_path = (
            ResilienceConfig.load().log_dir
            / f"wave40_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
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

    def alert(self, msg: str, **kw: Any) -> None:
        self._write("ALERT", msg, **kw)


def _safe_call(
    logger: JSONLogger,
    node: str,
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """try/except wrapper with exponential backoff."""
    job_id = str(uuid.uuid4())[:12]
    start = time.monotonic()
    logger.info(f"[{node}] started", job_id=job_id)
    cfg = ResilienceConfig.load()
    last: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
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
                "blocked",
                "skipped",
            }:
                result.setdefault("job_id", job_id)
                return result
            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{"type": "raw", "payload": result}],
                "error": None,
                "logs": [],
            }
        except Exception as exc:
            last = exc
            logger.error(
                f"[{node}] attempt {attempt} failed",
                job_id=job_id,
                error=str(exc),
            )
            if attempt < cfg.max_retries:
                time.sleep(cfg.retry_backoff_base_s * (2 ** (attempt - 1)))
    return {
        "status": "failed",
        "job_id": job_id,
        "artifacts": [],
        "error": str(last),
        "logs": [f"{node} failed after {cfg.max_retries} attempts"],
    }
