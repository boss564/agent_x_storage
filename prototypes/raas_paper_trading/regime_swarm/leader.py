"""StatefulSet leader election — ordinal-0 active, higher ordinals standby (monitoring only)."""
from __future__ import annotations

import os


def pod_ordinal(pod_name: str) -> int:
    """Extract StatefulSet ordinal from pod name (e.g. regime-swarm-0 → 0)."""
    if not pod_name or pod_name in ("unknown", "local"):
        return 0
    tail = pod_name.rsplit("-", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return 0


def is_leader_pod(
    pod_name: str,
    *,
    election_enabled: bool,
    leader_ordinal: int = 0,
) -> bool:
    """Return True when this pod may run the full A1→A9 decision cycle."""
    if not election_enabled:
        return True
    return pod_ordinal(pod_name) == leader_ordinal


def resolve_pod_identity() -> tuple[str, int, bool]:
    """Read K8s Downward API env and return (pod_name, ordinal, is_leader)."""
    pod_name = os.environ.get("POD_NAME", "local")
    election = os.environ.get("SWARM_LEADER_ELECTION_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    leader_ordinal = int(os.environ.get("SWARM_LEADER_ORDINAL", "0"))
    ordinal = pod_ordinal(pod_name)
    leader = is_leader_pod(
        pod_name,
        election_enabled=election,
        leader_ordinal=leader_ordinal,
    )
    return pod_name, ordinal, leader
