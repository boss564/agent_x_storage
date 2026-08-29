"""B2 sample eligibility for paper edges — freeze-k only, clean hold window.

Estimand: distribution of the *k-step* return at frozen PAPER_HOLD_SECONDS.
Mixing different k values (e.g. superseded 433 vs 4966) yields no valid estimand.
Late exits (feed gap after hold expiry) stretch the horizon — exclude via delta.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Align with PAPER_EXIT_GAP_DT_S default — beyond this, horizon ≠ k
DEFAULT_HOLD_CLEAN_MAX_DELTA_S = 30.0
DEFAULT_FREEZE_K = int(os.environ.get("PAPER_HOLD_SECONDS", "4966"))


def hold_seconds_delta(edge: Dict[str, Any]) -> Optional[float]:
    if "hold_seconds_delta" in edge and edge["hold_seconds_delta"] is not None:
        return float(edge["hold_seconds_delta"])
    try:
        return float(edge["hold_seconds_actual"]) - float(edge["hold_seconds_target"])
    except (KeyError, TypeError, ValueError):
        return None


def edge_sample_eligible(
    edge: Dict[str, Any],
    *,
    freeze_k: int = DEFAULT_FREEZE_K,
    max_delta_s: float = DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
) -> Tuple[bool, str]:
    """Return (eligible, reason_code)."""
    try:
        target = int(edge.get("hold_seconds_target"))
    except (TypeError, ValueError):
        return False, "missing_hold_seconds_target"
    if target != int(freeze_k):
        return False, "wrong_k"
    reason = str(edge.get("exit_reason") or "")
    if reason != "hold_expired":
        # force_exit / other → different horizon estimand
        return False, f"exit_reason_{reason or 'missing'}"
    delta = hold_seconds_delta(edge)
    if delta is None:
        return False, "missing_hold_duration"
    if abs(delta) > float(max_delta_s):
        return False, "hold_delta_exceeded"
    return True, "ok"


def load_edges(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def count_eligible(
    edges: Iterable[Dict[str, Any]],
    *,
    freeze_k: int = DEFAULT_FREEZE_K,
    max_delta_s: float = DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
) -> Dict[str, Any]:
    total = 0
    eligible = 0
    by_reason: Dict[str, int] = {}
    for e in edges:
        total += 1
        ok, code = edge_sample_eligible(e, freeze_k=freeze_k, max_delta_s=max_delta_s)
        if ok:
            eligible += 1
        by_reason[code] = by_reason.get(code, 0) + 1
    return {
        "freeze_k": int(freeze_k),
        "max_delta_s": float(max_delta_s),
        "n_edges_total": total,
        "n_eligible_at_freeze_k": eligible,
        "n_ineligible": total - eligible,
        "by_reason": by_reason,
        "gate_n_min": 50,
        "b2_ready": eligible >= 50,
        "note": (
            "B2 counts only edges with hold_seconds_target==freeze_k, "
            "exit_reason=hold_expired, |hold_actual−target|≤max_delta_s. "
            "Do not count raw SELL lines or mixed-k samples."
        ),
    }
