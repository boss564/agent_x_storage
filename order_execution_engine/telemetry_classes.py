"""Telemetrie-Klassen außerhalb des Reject-Trichters (Schritt 1 / GP-5).

Kein ``RejectReason``: Alt-Queries ``WHERE reject_reason IS NOT NULL`` dürfen
D2-Zeilen nicht als Risk-Fail zählen. Persistenz: Spalte ``telemetry_class``.
"""

from __future__ import annotations

from enum import Enum


class TelemetryClass(str, Enum):
    """Eigener Konstantenraum — Meta-Anker (P-2) wacht über Produzenten."""

    UNACTIONABLE_SELL_NO_INVENTORY = "UNACTIONABLE_SELL_NO_INVENTORY"


# Alias für kurze Lesepfade / Report-Kopf.
UNACTIONABLE_SELL_NO_INVENTORY = TelemetryClass.UNACTIONABLE_SELL_NO_INVENTORY.value
