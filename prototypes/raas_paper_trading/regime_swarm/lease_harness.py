"""Kubernetes Lease harness for Infra-Guardian T-S1a/T-S2b (test-only, gate-closed).

Reference implementation of coordination.k8s.io/v1 Lease acquire/renew/release.
NOT wired into run_regime_swarm_daemon.py until §6 GATE OPEN.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _micros(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond:06d}Z"


@dataclass(frozen=True)
class LeaseSpec:
    name: str
    namespace: str
    lease_duration_seconds: int = 15
    renew_interval_seconds: int = 5


@dataclass
class LeaseSnapshot:
    holder: str
    resource_version: str
    lease_duration_seconds: int
    renew_time: Optional[datetime]
    acquire_time: Optional[datetime]

    @property
    def is_expired(self) -> bool:
        if not self.holder or self.renew_time is None:
            return True
        age = (_utc_now() - self.renew_time).total_seconds()
        return age >= float(self.lease_duration_seconds)

    @property
    def seconds_since_renew(self) -> float:
        if self.renew_time is None:
            return float("inf")
        return (_utc_now() - self.renew_time).total_seconds()


class KubectlLeaseClient:
    """Minimal Lease client via kubectl (no kubernetes-python dependency)."""

    def __init__(self, spec: LeaseSpec, *, context: Optional[str] = None) -> None:
        self.spec = spec
        self._context = context

    def _kubectl(
        self, *args: str, check: bool = True, input_text: Optional[str] = None
    ) -> subprocess.CompletedProcess[str]:
        cmd = ["kubectl"]
        if self._context:
            cmd.extend(["--context", self._context])
        cmd.extend(args)
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check, input=input_text
        )

    def ensure_lease_object(self) -> None:
        manifest = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {"name": self.spec.name, "namespace": self.spec.namespace},
            "spec": {"leaseDurationSeconds": self.spec.lease_duration_seconds},
        }
        self._kubectl(
            "apply",
            "-f",
            "-",
            "-n",
            self.spec.namespace,
            input_text=json.dumps(manifest),
        )

    def read(self) -> Optional[LeaseSnapshot]:
        proc = self._kubectl(
            "get",
            "lease",
            self.spec.name,
            "-n",
            self.spec.namespace,
            "-o",
            "json",
            check=False,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        spec = data.get("spec") or {}
        renew_raw = spec.get("renewTime")
        acquire_raw = spec.get("acquireTime")
        return LeaseSnapshot(
            holder=str(spec.get("holderIdentity") or ""),
            resource_version=str(data["metadata"]["resourceVersion"]),
            lease_duration_seconds=int(
                spec.get("leaseDurationSeconds") or self.spec.lease_duration_seconds
            ),
            renew_time=_parse_k8s_time(renew_raw) if renew_raw else None,
            acquire_time=_parse_k8s_time(acquire_raw) if acquire_raw else None,
        )

    def try_acquire(self, identity: str) -> bool:
        snap = self.read()
        if snap is None:
            self.ensure_lease_object()
            snap = self.read()
        if snap is None:
            return False

        now = _utc_now()
        if snap.holder and snap.holder != identity and not snap.is_expired:
            return snap.holder == identity

        body: Dict[str, Any] = {
            "spec": {
                "holderIdentity": identity,
                "leaseDurationSeconds": self.spec.lease_duration_seconds,
                "renewTime": _micros(now),
            }
        }
        if not snap.holder or snap.is_expired:
            body["spec"]["acquireTime"] = _micros(now)

        proc = self._kubectl(
            "patch",
            "lease",
            self.spec.name,
            "-n",
            self.spec.namespace,
            "--type=merge",
            "-p",
            json.dumps(body),
            check=False,
        )
        if proc.returncode != 0:
            return False
        updated = self.read()
        return updated is not None and updated.holder == identity

    def renew(self, identity: str) -> bool:
        snap = self.read()
        if snap is None or snap.holder != identity:
            return False
        if snap.is_expired:
            return self.try_acquire(identity)
        now = _utc_now()
        body = {
            "spec": {
                "holderIdentity": identity,
                "leaseDurationSeconds": self.spec.lease_duration_seconds,
                "renewTime": _micros(now),
            }
        }
        proc = self._kubectl(
            "patch",
            "lease",
            self.spec.name,
            "-n",
            self.spec.namespace,
            "--type=merge",
            "-p",
            json.dumps(body),
            check=False,
        )
        if proc.returncode != 0:
            return False
        updated = self.read()
        return updated is not None and updated.holder == identity

    def release(self, identity: str) -> bool:
        snap = self.read()
        if snap is None or snap.holder != identity:
            return True
        body = {
            "spec": {
                "holderIdentity": "",
                "renewTime": None,
                "acquireTime": None,
            }
        }
        proc = self._kubectl(
            "patch",
            "lease",
            self.spec.name,
            "-n",
            self.spec.namespace,
            "--type=merge",
            "-p",
            json.dumps(body),
            check=False,
        )
        return proc.returncode == 0

    def wait_for_acquire(
        self,
        identity: str,
        *,
        timeout_s: float,
        poll_s: float = 0.25,
    ) -> tuple[bool, float]:
        """Poll try_acquire until success or timeout. Returns (ok, monotonic_ts)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.try_acquire(identity):
                return True, time.monotonic()
            time.sleep(poll_s)
        return False, time.monotonic()


def _parse_k8s_time(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def race_acquire(
    client: KubectlLeaseClient,
    identity: str,
    *,
    rounds: int,
    delay_s: float = 0.0,
) -> Dict[str, Any]:
    wins = 0
    for _ in range(rounds):
        if client.try_acquire(identity):
            wins += 1
        if delay_s:
            time.sleep(delay_s)
    snap = client.read()
    return {
        "identity": identity,
        "wins": wins,
        "holder_after": snap.holder if snap else "",
    }
