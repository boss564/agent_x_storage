"""StatefulSet leader election — ordinal-0 or Kubernetes Lease (§6 gate-open)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from prototypes.raas_paper_trading.regime_swarm.lease_harness import LeaseSpec
from prototypes.raas_paper_trading.regime_swarm.lease_k8s import InClusterLeaseClient


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
    """Return True when this pod may run the full A1→A9 decision cycle (ordinal mode)."""
    if not election_enabled:
        return True
    return pod_ordinal(pod_name) == leader_ordinal


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class LeaderIdentity:
    pod_name: str
    pod_ordinal: int
    is_leader: bool
    mode: str  # election_disabled | ordinal_0_static | kubernetes_lease


class KubernetesLeaseLeader:
    """Acquire / renew / release coordination.k8s.io Lease (in-cluster only)."""

    def __init__(
        self,
        identity: str,
        *,
        lease_name: str,
        namespace: str,
        lease_duration_seconds: int = 15,
    ) -> None:
        spec = LeaseSpec(
            name=lease_name,
            namespace=namespace,
            lease_duration_seconds=lease_duration_seconds,
            renew_interval_seconds=int(os.environ.get("SWARM_LEASE_RENEW_INTERVAL_SECONDS", "5")),
        )
        self.identity = identity
        self._client = InClusterLeaseClient(spec)
        self._holder = False

    def acquire(self) -> bool:
        self._holder = self._client.try_acquire(self.identity)
        return self._holder

    def renew(self) -> bool:
        if self._holder:
            self._holder = self._client.renew(self.identity)
        else:
            self._holder = self._client.try_acquire(self.identity)
        return self._holder

    def release(self) -> None:
        released = self._client.release(self.identity)
        self._holder = False
        print(
            json.dumps(
                {
                    "event": "lease_released",
                    "identity": self.identity,
                    "released": released,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            ),
            flush=True,
        )

    @property
    def is_holder(self) -> bool:
        return self._holder


def build_lease_leader(pod_name: str) -> Optional[KubernetesLeaseLeader]:
    if not _env_bool("SWARM_LEASE_ENABLED"):
        return None
    if not InClusterLeaseClient.in_cluster():
        return None
    namespace = os.environ.get("POD_NAMESPACE", "default")
    lease_name = os.environ.get("SWARM_LEASE_NAME", "regime-swarm-leader")
    duration = int(os.environ.get("SWARM_LEASE_DURATION_SECONDS", "15"))
    return KubernetesLeaseLeader(
        pod_name,
        lease_name=lease_name,
        namespace=namespace,
        lease_duration_seconds=duration,
    )


def resolve_leader_with_lease() -> tuple[LeaderIdentity, Optional[KubernetesLeaseLeader]]:
    """Resolve identity and return optional lease handle for renewal loop."""
    pod_name = os.environ.get("POD_NAME", "local")
    ordinal = pod_ordinal(pod_name)
    election = _env_bool("SWARM_LEADER_ELECTION_ENABLED")
    leader_ordinal = int(os.environ.get("SWARM_LEADER_ORDINAL", "0"))

    lease = build_lease_leader(pod_name)
    if lease is not None:
        is_leader = lease.acquire()
        return (
            LeaderIdentity(pod_name, ordinal, is_leader, "kubernetes_lease"),
            lease,
        )

    if not election:
        return LeaderIdentity(pod_name, ordinal, True, "election_disabled"), None

    is_leader = is_leader_pod(
        pod_name,
        election_enabled=True,
        leader_ordinal=leader_ordinal,
    )
    return LeaderIdentity(pod_name, ordinal, is_leader, "ordinal_0_static"), None


def resolve_leader_identity() -> LeaderIdentity:
    identity, _ = resolve_leader_with_lease()
    return identity


def resolve_pod_identity() -> tuple[str, int, bool]:
    """Backward-compatible tuple API used by the daemon."""
    ident = resolve_leader_identity()
    return ident.pod_name, ident.pod_ordinal, ident.is_leader
