"""Standard agent envelope helpers for Wave 39."""

from __future__ import annotations

from typing import Any, Literal

AgentStatus = Literal["started", "completed", "failed", "blocked", "skipped"]


class AgentEnvelope(dict[str, Any]):
    """Typed dict-like envelope for Wave 39 subagents."""


def make_response(
    status: AgentStatus,
    job_id: str,
    *,
    artifacts: list[dict[str, Any]] | None = None,
    error: str | None = None,
    logs: list[str] | None = None,
) -> AgentEnvelope:
    return AgentEnvelope(
        status=status,
        job_id=job_id,
        artifacts=artifacts or [],
        error=error,
        logs=logs or [],
    )
