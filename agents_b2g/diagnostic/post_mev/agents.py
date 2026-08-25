"""Standard agent envelope helpers for Post-MEV."""

from __future__ import annotations

from typing import Any, Literal

AgentStatus = Literal["started", "completed", "failed", "blocked", "skipped"]


def make_response(
    status: AgentStatus,
    job_id: str,
    *,
    artifacts: list[dict[str, Any]] | None = None,
    error: str | None = None,
    logs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "job_id": job_id,
        "artifacts": artifacts or [],
        "error": error,
        "logs": logs or [],
    }
