#!/usr/bin/env python3
"""HA leader election smoke — ordinal fallback + lease identity (unit-level)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_swarm.leader import (  # noqa: E402
    is_leader_pod,
    resolve_leader_identity,
    resolve_leader_with_lease,
    resolve_pod_identity,
)


def main() -> int:
    failed = 0

    if not is_leader_pod("regime-swarm-0", election_enabled=True, leader_ordinal=0):
        print("FAIL ordinal leader pod-0")
        failed += 1
    if is_leader_pod("regime-swarm-1", election_enabled=True, leader_ordinal=0):
        print("FAIL ordinal standby pod-1")
        failed += 1

    with mock.patch.dict(
        os.environ,
        {
            "POD_NAME": "local",
            "SWARM_LEADER_ELECTION_ENABLED": "true",
            "SWARM_LEASE_ENABLED": "false",
        },
        clear=False,
    ):
        ident = resolve_leader_identity()
        if ident.mode != "ordinal_0_static" or not ident.is_leader:
            print(f"FAIL local ordinal fallback: {ident}")
            failed += 1

    with mock.patch.dict(
        os.environ,
        {
            "POD_NAME": "regime-swarm-shadow-1",
            "SWARM_LEADER_ELECTION_ENABLED": "true",
            "SWARM_LEASE_ENABLED": "false",
        },
        clear=False,
    ):
        _, ordinal, is_leader = resolve_pod_identity()
        if ordinal != 1 or is_leader:
            print(f"FAIL standby ordinal identity: {ordinal} leader={is_leader}")
            failed += 1

    with mock.patch.dict(
        os.environ,
        {
            "POD_NAME": "regime-swarm-shadow-0",
            "SWARM_LEASE_ENABLED": "true",
            "SWARM_LEADER_ELECTION_ENABLED": "true",
            "POD_NAMESPACE": "regime-swarm-shadow",
        },
        clear=False,
    ), mock.patch(
        "prototypes.raas_paper_trading.regime_swarm.leader.InClusterLeaseClient.in_cluster",
        return_value=False,
    ):
        ident, lease = resolve_leader_with_lease()
        if ident.mode != "ordinal_0_static" or lease is not None:
            print(f"FAIL lease disabled outside cluster: {ident.mode} lease={lease}")
            failed += 1

    if failed:
        print(f"REGIME_SWARM_HA_FAIL ({failed})")
        return 1
    print("REGIME_SWARM_HA_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
