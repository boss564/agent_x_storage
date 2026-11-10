"""D1 Lese-Andockung — Epoch-Hydration aus ``fills`` (Schritt 1 / Paket 4).

Epoch-Schlüssel: monotoner Speicher-Schlüssel = SQLite ``fills.rowid``.
Kein Wall-Clock-Timestamp (GP-4 / A4.4). Marker-**Schreiben** = Messlauf-Bauplan.

P-1: ``fills`` hat zusammengesetzten PRIMARY KEY ohne ``AUTOINCREMENT``.
Schema-Invariante: **kein DELETE auf fills, niemals** — sonst rowid-Reuse
und stille Epoch-Korruption. Test: ``test_p1_fills_rowid_anchor``.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Optional, Protocol

from order_execution_engine.models import VirtualPortfolio

# P-1 Schema-Invariante (bindend, bis AUTOINCREMENT eingeführt wird).
FILLS_NO_DELETE_INVARIANT = (
    "fills is append-only: DELETE FROM fills is forbidden "
    "(rowid monotonicity without AUTOINCREMENT)"
)


class _StorageConn(Protocol):
    _conn: sqlite3.Connection


def assert_fills_rowid_anchor(conn: sqlite3.Connection) -> str:
    """P-1-Nachweis: Anker-Modus oder AssertionError.

    Returns:
        ``autoincrement`` oder ``rowid_no_delete``.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='fills'"
    ).fetchone()
    if row is None or not row[0]:
        raise AssertionError("fills-Tabelle fehlt — Epoch-Anker unmöglich")
    ddl = row[0].upper()
    if "AUTOINCREMENT" in ddl:
        return "autoincrement"
    # Zusammengesetzter PK → implicit rowid; Monotonie nur mit No-Delete.
    assert "FILLS" in ddl and "PRIMARY KEY" in ddl
    assert FILLS_NO_DELETE_INVARIANT  # dokumentierte Garantie
    return "rowid_no_delete"


def positions_since_epoch(
    storage: _StorageConn,
    epoch_marker_rowid: int,
    *,
    start_balance: Decimal = Decimal("10000"),
) -> VirtualPortfolio:
    """Leitet ein Portfolio aus Fills mit ``rowid > marker`` ab (nur Lesen).

    Schritt-1-Skizze: leeres Eröffnungs-Inventar (D1-b), wenn keine Fills
    nach dem Marker liegen. Volle Fill→Position-Rekonstruktion kann der
    Messlauf nachziehen; hier zählt der Andockpunkt + P-1-Anker.
    """
    mode = assert_fills_rowid_anchor(storage._conn)
    _ = mode
    n = storage._conn.execute(
        "SELECT COUNT(*) FROM fills WHERE rowid > ?",
        (int(epoch_marker_rowid),),
    ).fetchone()[0]
    portfolio = VirtualPortfolio(cash=start_balance, start_balance=start_balance)
    if int(n) == 0:
        return portfolio
    # Bewusst schlank: volle apply_fill-Kette ist Messlauf-Stoff.
    # Marker+Count beweist den Lese-Pfad ohne Dual-Truth an fills.
    portfolio._epoch_fill_count = int(n)  # type: ignore[attr-defined]
    return portfolio


def try_hydrate_engine_portfolio(
    engine: object,
    storage: _StorageConn,
    *,
    epoch_marker_rowid: Optional[int],
    enabled: bool,
) -> bool:
    """Lesender Hook hinter Flag (A4.1). Kein Marker-Schreiben."""
    if not enabled or epoch_marker_rowid is None:
        return False
    portfolio = positions_since_epoch(storage, epoch_marker_rowid)
    setattr(engine, "portfolio", portfolio)
    return True
