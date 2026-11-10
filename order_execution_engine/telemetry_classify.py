"""N-4 telemetry row classification (Schritt 2 / GP report split).

approved=1                         → approval
approved=0 ∧ telemetry_class set   → unactionable  (D2 etc.; not a reject)
approved=0 ∧ telemetry_class NULL  → reject
"""

from __future__ import annotations

from typing import Any, Literal, Optional

TelemetryKind = Literal["approval", "unactionable", "reject"]


def classify_telemetry_row(
    *,
    approved: Any,
    telemetry_class: Any = None,
    reject_reason: Any = None,
) -> TelemetryKind:
    """Classify one telemetry observation for reports (A-C1/A-C2)."""
    is_approved = int(approved or 0) == 1
    if is_approved:
        return "approval"
    tc = telemetry_class
    if tc is not None and str(tc).strip() not in ("", "None", "null"):
        return "unactionable"
    return "reject"


def row_get(row: Any, key: str, default: Any = None) -> Any:
    """Tolerant column access — Alt-DB without ``telemetry_class`` (A-C2/A-C3)."""
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return default
