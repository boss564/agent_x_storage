"""D1–D4 suite enforcer — application-level fail-closed barriers.

Maps documented debts to runtime checks (layer 2, pragmatic):

  D1  not_investment_advice — stamp + reject advisory free-text
  D2  Red sandbox — Red may only touch sandbox paths; no gate decisions
  D3  Shell quarantine — Untrusted shell only allowed evaluate targets
  D4  Ingress/Egress exterior — exterior callers only via facade paths

Cross-cutting: every successful enforce stamps `_worm_anchor_sha256`
(for P9/WORM chaining — not a fifth debt ID).

Not a replacement for Wave-39 ScopeEnforcerAgent (scope flag); complementary.
Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"

# D1: advisory language in free-text only (not structured label/profile)
_ADVICE_RE = re.compile(
    r"\b(buy|sell|accumulate|liquidate)\b"
    r"|\b(target_price|take_profit|stop_loss)\b"
    r"|\byou should (buy|sell|hold for gain)\b",
    re.IGNORECASE,
)
_D1_SCAN_KEYS = frozenset(
    {"advice", "recommendation", "narrative", "free_text", "comment", "rationale"}
)
_D1_SKIP_KEYS = frozenset(
    {"label", "proposal_id", "profile_hint", "source", "untrusted"}
)

# D2
_RED_ROLES = frozenset({"RED", "RED_TEAM", "UNTRUSTED_RED"})
_SANDBOX_PREFIXES = ("/data/raas/sandbox/", "data/raas/sandbox/")
_DECISION_KEYS = frozenset(
    {"gate_verdict", "audit_verdict", "envelope_id", "egress_seal", "certificate_id"}
)

# D3
_SHELL_ROLES = frozenset({"UNTRUSTED_SHELL", "SHELL", "LLM_SHELL"})
_SHELL_ALLOWED_TARGETS = frozenset(
    {
        "/api/v1/raas/evaluate",
        "/api/v1/raas/runs",
        "internal://trusted_core/evaluate",
    }
)

# D4 — exterior only via ingress/egress/evaluate facade surface
_EXTERIOR_ROLES = frozenset({"EXTERNAL", "UNTRUSTED_SHELL", "SHELL", "LLM_SHELL"})
_EXTERIOR_ALLOWED_TARGETS = frozenset(
    {
        "/api/v1/raas/ingress",
        "/api/v1/raas/egress",
        "/api/v1/raas/evaluate",
        "internal://trusted_core/evaluate",
    }
)


class DSuiteViolation(Exception):
    """Fail-closed barrier trip."""

    def __init__(self, debt_id: str, reason: str) -> None:
        self.debt_id = debt_id
        self.reason = reason
        super().__init__(f"{debt_id}: {reason}")


@dataclass
class EnforcerContext:
    caller_role: str
    target_path: str
    payload: Dict[str, Any] = field(default_factory=dict)
    write_path: Optional[str] = None


@dataclass
class EnforcerResult:
    payload: Dict[str, Any]
    debts_checked: list[str]
    worm_anchor_sha256: str


class WormAnchorStore:
    """Minimal append-only hash chain for D-suite stamps (proto)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        root = Path(
            path
            or Path("data/raas/worm") / "d_suite_anchors.jsonl"
        )
        root.parent.mkdir(parents=True, exist_ok=True)
        self.path = root

    def _prev(self) -> str:
        if not self.path.exists():
            return "GENESIS"
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return "GENESIS"
        return json.loads(lines[-1]).get("hash", "GENESIS")

    def append(self, material: Mapping[str, Any]) -> str:
        prev = self._prev()
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "prev": prev,
            "material": dict(material),
        }
        digest = hashlib.sha256(
            json.dumps(line, sort_keys=True, default=str).encode()
        ).hexdigest()
        line["hash"] = digest
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
        return digest


class DSuiteEnforcer:
    """Enforce D1–D4; stamp live_execution=false and worm anchor."""

    def __init__(self, worm: Optional[WormAnchorStore] = None) -> None:
        self.worm = worm or WormAnchorStore()

    def enforce_all(self, ctx: EnforcerContext) -> Dict[str, Any]:
        payload = dict(ctx.payload)
        self._d1_not_investment_advice(payload)
        self._d2_red_sandbox(ctx, payload)
        self._d3_shell_quarantine(ctx)
        self._d4_ingress_egress(ctx)

        payload["not_investment_advice"] = True
        payload["live_execution"] = False
        payload["scope"] = SCOPE
        payload["_d_suite_checked"] = ["D1", "D2", "D3", "D4"]

        anchor = self.worm.append(
            {
                "caller_role": ctx.caller_role,
                "target_path": ctx.target_path,
                "payload_keys": sorted(payload.keys()),
            }
        )
        payload["_worm_anchor_sha256"] = anchor
        return payload

    def _d1_not_investment_advice(self, payload: Dict[str, Any]) -> None:
        for key, val in payload.items():
            if not isinstance(val, str):
                continue
            if key in _D1_SKIP_KEYS:
                continue
            if key not in _D1_SCAN_KEYS and not key.endswith("_advice"):
                continue
            if _ADVICE_RE.search(val):
                raise DSuiteViolation(
                    "D1",
                    f"advisory language in field '{key}' blocked",
                )

    def _d2_red_sandbox(self, ctx: EnforcerContext, payload: Dict[str, Any]) -> None:
        role = ctx.caller_role.upper()
        if role not in _RED_ROLES:
            return
        if ctx.write_path is not None:
            ok = any(ctx.write_path.startswith(p) for p in _SANDBOX_PREFIXES)
            if not ok:
                raise DSuiteViolation(
                    "D2",
                    f"Red write_path outside sandbox: {ctx.write_path}",
                )
        leaked = _DECISION_KEYS.intersection(payload.keys())
        if leaked:
            raise DSuiteViolation(
                "D2",
                f"Red must not set decision fields: {sorted(leaked)}",
            )

    def _d3_shell_quarantine(self, ctx: EnforcerContext) -> None:
        role = ctx.caller_role.upper()
        if role not in _SHELL_ROLES:
            return
        if ctx.target_path not in _SHELL_ALLOWED_TARGETS:
            raise DSuiteViolation(
                "D3",
                f"Shell target not allowed: {ctx.target_path}",
            )

    def _d4_ingress_egress(self, ctx: EnforcerContext) -> None:
        role = ctx.caller_role.upper()
        if role not in _EXTERIOR_ROLES:
            return
        if ctx.target_path not in _EXTERIOR_ALLOWED_TARGETS:
            raise DSuiteViolation(
                "D4",
                f"Exterior caller must use ingress/egress/evaluate: {ctx.target_path}",
            )
