"""L4 role authorization — gatectl/lease policy (not persistence schema).

Policy lives here / optional JSON via ``CONTROL_PLANE_AUTHZ_POLICY`` —
never as a SQLite schema change (would thaw the frozen persistence module).

## Defaults (L4-b / L4-C1)

* Authz is **always enforced** in gatectl (unset ``CONTROL_PLANE_AUTHZ_ENFORCE``
  ⇒ enforce). Explicit ``0`` / ``false`` / ``off`` is refused in production
  paths; only the pytest suite may set it for isolation experiments.
* Missing role ⇒ **Deny** (no Operator fallback — L4-C3).
* Unknown role ⇒ **Deny**.
* Unknown operation ⇒ **Deny**.

## Operations matrix (L4-a / L4-C2) — Soll

| Operation              | runner | watchdog | auditor | operator |
|------------------------|:------:|:--------:|:-------:|:--------:|
| issue-token            |   ✓    |          |         |    ✓     |
| abort-run              |   ✓    |          |         |    ✓     |
| revoke-token           |   ✓    |          |         |    ✓     |
| claim-run              |   ✓    |          |         |          |
| watchdog-check         |        |    ✓     |         |    ✓     |
| status                 |        |    ✓     |    ✓    |    ✓     |
| integrity-check        |        |    ✓     |    ✓    |    ✓     |
| verify-snapshot        |        |          |    ✓    |    ✓     |
| verify-mirror          |        |          |    ✓    |    ✓     |
| post-run-check         |        |          |    ✓    |    ✓     |
| audit-read             |        |          |    ✓    |    ✓     |
| migrate                |        |          |         |    ✓     |
| retire-run-lock        |        |          |         |    ✓     |
| restore-run-lock       |        |          |         |    ✓     |
| restore-db-artefact    |        |          |         |    ✓     |
| launchctl-register     |        |          |         |    ✓     |

Least privilege (L4-c): ``runner`` = lease ops only; ``watchdog`` = lease/status
reads; ``auditor`` = audit reads; ``operator`` = documented mutations only.
No allmacht role alias.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

# L4-c: least privilege — no allmacht alias.
ROLES = frozenset({"runner", "watchdog", "auditor", "operator"})

# L4-a: every gatectl / control-plane operation maps to an allowed role set.
# launchctl-register is documented but not a gatectl subcommand yet —
# listed so unknown callers cannot invent a silent allow.
OPERATIONS: dict[str, frozenset[str]] = {
    # Lease ops (runner hot path + operator recovery)
    "issue-token": frozenset({"runner", "operator"}),
    "abort-run": frozenset({"runner", "operator"}),
    "revoke-token": frozenset({"runner", "operator"}),
    "claim-run": frozenset({"runner"}),
    # Lease / integrity reads
    "watchdog-check": frozenset({"watchdog", "operator"}),
    "status": frozenset({"watchdog", "auditor", "operator"}),
    "integrity-check": frozenset({"auditor", "operator", "watchdog"}),
    # Audit reads
    "verify-snapshot": frozenset({"auditor", "operator"}),
    "verify-mirror": frozenset({"auditor", "operator"}),
    "post-run-check": frozenset({"auditor", "operator"}),
    "audit-read": frozenset({"auditor", "operator"}),
    # Mutations (operator only)
    "migrate": frozenset({"operator"}),
    "retire-run-lock": frozenset({"operator"}),
    "restore-run-lock": frozenset({"operator"}),
    "restore-db-artefact": frozenset({"operator"}),
    "launchctl-register": frozenset({"operator"}),
}

# Optional JSON override path (gatectl-config, not persistence).
_ENV_POLICY = "CONTROL_PLANE_AUTHZ_POLICY"
_ENV_ROLE = "CONTROL_PLANE_ROLE"
_ENV_ENFORCE = "CONTROL_PLANE_AUTHZ_ENFORCE"
_ENV_AUDIT_LOG = "CONTROL_PLANE_AUTHZ_AUDIT_LOG"


class AuthzError(PermissionError):
    """Role denied or missing — fail-closed."""


@dataclass(frozen=True)
class AuthzDecision:
    role: str
    operation: str
    target: str
    allowed: bool
    ts: float
    reason: str


_AuditSink = Callable[[AuthzDecision], None]


def authz_enforced() -> bool:
    """L4-C1: unset ⇒ enforce. Only explicit 0/false/off disables (suite only)."""
    raw = os.environ.get(_ENV_ENFORCE, "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    # unset, "1", "true", "yes", "on", or any other value → enforce
    return True


def _default_audit_sink(decision: AuthzDecision) -> None:
    path_raw = os.environ.get(_ENV_AUDIT_LOG, "").strip()
    if not path_raw:
        return
    path = Path(path_raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": decision.ts,
        "role": decision.role,
        "operation": decision.operation,
        "target": decision.target,
        "allowed": decision.allowed,
        "reason": decision.reason,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def load_operations_matrix() -> dict[str, frozenset[str]]:
    """L4-e: policy from module + optional JSON file (never SQLite schema)."""
    matrix = {k: frozenset(v) for k, v in OPERATIONS.items()}
    path_raw = os.environ.get(_ENV_POLICY, "").strip()
    if not path_raw:
        return matrix
    path = Path(path_raw)
    if not path.is_file():
        raise AuthzError(f"authz policy file missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AuthzError("authz policy must be a JSON object")
    for op, roles in raw.items():
        if not isinstance(op, str) or not isinstance(roles, list):
            raise AuthzError(f"authz policy entry invalid: {op!r}")
        matrix[op] = frozenset(str(r) for r in roles)
    return matrix


def resolve_role(explicit: Optional[str] = None) -> str:
    """Resolve role once per process call — no silent Operator default (L4-C3)."""
    if explicit is not None:
        return str(explicit).strip()
    return os.environ.get(_ENV_ROLE, "").strip()


def authorize(
    role: Optional[str],
    operation: str,
    *,
    target: str = "",
    audit: Optional[_AuditSink] = None,
) -> AuthzDecision:
    """L4-b/d: allow or deny; always audit (Deny is first-class)."""
    sink = audit if audit is not None else _default_audit_sink
    op = str(operation).strip()
    r = resolve_role(role)
    ts = time.time()
    matrix = load_operations_matrix()

    if not r:
        dec = AuthzDecision(
            role="",
            operation=op,
            target=target,
            allowed=False,
            ts=ts,
            reason="missing role (deny-by-default)",
        )
        sink(dec)
        raise AuthzError(dec.reason)

    if r not in ROLES:
        dec = AuthzDecision(
            role=r,
            operation=op,
            target=target,
            allowed=False,
            ts=ts,
            reason=f"unknown role {r!r} (deny-by-default)",
        )
        sink(dec)
        raise AuthzError(dec.reason)

    allowed_roles = matrix.get(op)
    if allowed_roles is None:
        dec = AuthzDecision(
            role=r,
            operation=op,
            target=target,
            allowed=False,
            ts=ts,
            reason=f"unknown operation {op!r} (deny-by-default)",
        )
        sink(dec)
        raise AuthzError(dec.reason)

    if r not in allowed_roles:
        dec = AuthzDecision(
            role=r,
            operation=op,
            target=target,
            allowed=False,
            ts=ts,
            reason=f"role {r!r} denied for {op!r}",
        )
        sink(dec)
        raise AuthzError(dec.reason)

    dec = AuthzDecision(
        role=r,
        operation=op,
        target=target,
        allowed=True,
        ts=ts,
        reason="allow",
    )
    sink(dec)
    return dec


def assert_no_persistence_schema_touch() -> dict[str, Any]:
    """L4-f(5): authz module must not import / mutate persistence schema."""
    import ast

    import order_execution_engine.control_plane_authz as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
    banned_mods = (
        "order_execution_engine.persistence",
        "order_execution_engine.control_plane_lease",
    )
    hits = [m for m in banned_mods if m in imported]
    return {"ok": not hits, "banned_hits": hits, "imports": imported}


def operations_matrix_markdown() -> str:
    """Stable Soll table for audits / L5 runbook embedding."""
    roles = ("runner", "watchdog", "auditor", "operator")
    lines = [
        "| Operation | " + " | ".join(roles) + " |",
        "|" + "|".join(["---"] * (len(roles) + 1)) + "|",
    ]
    for op, allowed in OPERATIONS.items():
        cells = ["✓" if r in allowed else "" for r in roles]
        lines.append(f"| {op} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
