"""In-cluster Kubernetes Lease client (stdlib only, no kubectl)."""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from prototypes.raas_paper_trading.regime_swarm.lease_harness import (
    LeaseSnapshot,
    LeaseSpec,
    _micros,
    _parse_k8s_time,
)


class InClusterLeaseClient:
    """coordination.k8s.io/v1 Lease via ServiceAccount token."""

    def __init__(self, spec: LeaseSpec) -> None:
        self.spec = spec
        self._token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        self._ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        self._host = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        self._port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")

    @staticmethod
    def in_cluster() -> bool:
        return os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/token")

    def _url(self, subpath: str = "") -> str:
        base = (
            f"https://{self._host}:{self._port}/apis/coordination.k8s.io/v1/"
            f"namespaces/{self.spec.namespace}/leases/{self.spec.name}"
        )
        return base + subpath

    def _request(
        self,
        method: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        patch_type: Optional[str] = None,
    ) -> tuple[int, str]:
        token = open(self._token_path, encoding="utf-8").read().strip()
        headers = {"Authorization": f"Bearer {token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/merge-patch+json" if patch_type == "merge" else "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self._url(), data=data, headers=headers, method=method)
        ctx = ssl.create_default_context(cafile=self._ca_path)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")

    def read(self) -> Optional[LeaseSnapshot]:
        status, text = self._request("GET")
        if status != 200:
            return None
        data = json.loads(text)
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
            self._create_lease()
            snap = self.read()
        if snap is None:
            return False
        now = datetime.now(timezone.utc)
        if snap.holder and snap.holder != identity and not snap.is_expired:
            return False
        if snap.holder and snap.holder != identity and snap.is_expired:
            print(
                json.dumps(
                    {
                        "event": "lease_takeover_expired",
                        "identity": identity,
                        "previous_holder": snap.holder,
                        "seconds_since_renew": round(snap.seconds_since_renew, 3),
                        "ts": now.isoformat(),
                    }
                ),
                flush=True,
            )
        body: Dict[str, Any] = {
            "spec": {
                "holderIdentity": identity,
                "leaseDurationSeconds": self.spec.lease_duration_seconds,
                "renewTime": _micros(now),
            }
        }
        if not snap.holder or snap.is_expired:
            body["spec"]["acquireTime"] = _micros(now)
        status, _ = self._request("PATCH", body=body, patch_type="merge")
        if status not in (200, 201):
            return False
        updated = self.read()
        ok = updated is not None and updated.holder == identity
        if ok:
            print(
                json.dumps(
                    {
                        "event": "lease_acquired",
                        "identity": identity,
                        "previous_holder": snap.holder or None,
                        "previous_renew_age_s": round(snap.seconds_since_renew, 3)
                        if snap.holder
                        else None,
                        "via": "expired" if snap.holder and snap.is_expired else "empty",
                        "ts": now.isoformat(),
                    }
                ),
                flush=True,
            )
        return ok

    def renew(self, identity: str) -> bool:
        snap = self.read()
        if snap is None or snap.holder != identity:
            return False
        if snap.is_expired:
            return self.try_acquire(identity)
        now = datetime.now(timezone.utc)
        body = {
            "spec": {
                "holderIdentity": identity,
                "leaseDurationSeconds": self.spec.lease_duration_seconds,
                "renewTime": _micros(now),
            }
        }
        status, _ = self._request("PATCH", body=body, patch_type="merge")
        if status not in (200, 201):
            return False
        updated = self.read()
        return updated is not None and updated.holder == identity

    def release(self, identity: str) -> bool:
        snap = self.read()
        if snap is None or snap.holder != identity:
            return True
        body = {"spec": {"holderIdentity": "", "renewTime": None, "acquireTime": None}}
        status, _ = self._request("PATCH", body=body, patch_type="merge")
        ok = status in (200, 201)
        if ok:
            print(
                json.dumps(
                    {
                        "event": "lease_release_patch",
                        "identity": identity,
                        "previous_renew_age_s": round(snap.seconds_since_renew, 3),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                flush=True,
            )
        return ok

    def _create_lease(self) -> None:
        collection = (
            f"https://{self._host}:{self._port}/apis/coordination.k8s.io/v1/"
            f"namespaces/{self.spec.namespace}/leases"
        )
        token = open(self._token_path, encoding="utf-8").read().strip()
        body = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {"name": self.spec.name, "namespace": self.spec.namespace},
            "spec": {"leaseDurationSeconds": self.spec.lease_duration_seconds},
        }
        req = urllib.request.Request(
            collection,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        ctx = ssl.create_default_context(cafile=self._ca_path)
        try:
            urllib.request.urlopen(req, context=ctx, timeout=10)
        except urllib.error.HTTPError:
            pass
