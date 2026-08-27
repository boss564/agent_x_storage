"""Sandbox path confinement for Red-Team plugin (D2 app layer)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

# Must match DSuiteEnforcer _SANDBOX_PREFIXES (relative form)
SANDBOX_REL = Path("data/raas/sandbox/mev_latency_redteam")
SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


class SandboxPathError(ValueError):
    """Write attempted outside Red sandbox."""


def sandbox_root(repo_root: Path | None = None) -> Path:
    # Container OS-isolation: SANDBOX_DIR=/sandbox (rw tmpfs/volume only)
    env = os.environ.get("SANDBOX_DIR")
    if env:
        return Path(env).resolve()
    root = repo_root or Path.cwd()
    return (root / SANDBOX_REL).resolve()


def resolve_sandbox_path(rel: str, *, repo_root: Path | None = None) -> Path:
    """Resolve a relative path under the Red sandbox; reject escapes."""
    base = sandbox_root(repo_root)
    # Strip leading slashes so Path join stays under base
    clean = rel.lstrip("/").replace("\\", "/")
    if ".." in Path(clean).parts:
        raise SandboxPathError(f"path escape blocked: {rel}")
    target = (base / clean).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise SandboxPathError(f"path outside sandbox: {rel}") from exc
    return target


def write_sandbox_json(
    rel: str,
    payload: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> Path:
    path = resolve_sandbox_path(rel, repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    material = dict(payload)
    material.setdefault("scope", SCOPE)
    material.setdefault("live_execution", False)
    # Never persist decision fields even if caller slipped them in
    for key in ("gate_verdict", "audit_verdict", "envelope_id", "egress_seal", "certificate_id"):
        material.pop(key, None)
    path.write_text(json.dumps(material, indent=2, sort_keys=True), encoding="utf-8")
    return path
