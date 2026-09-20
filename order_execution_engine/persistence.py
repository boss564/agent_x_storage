"""Persistenz für die Shadow Execution Engine (Charter-konform, lokal).

Speichert TelemetryRecords, Fills und Portfolio-Snapshots in der Hub-DB
unter data/{user_id}/shadow/. Kein Netzwerkpfad — die Charter bleibt
unberührt (diagnostic_only, order_send=false).

Vorgaben (Vereinbarung aus dem Review):
    1. Migrationsweg: Storage-Protokoll mit expliziter schema_version;
       SQLite als Default, Hub-DB-Adapter später austauschbar.
    2. Decimal wird als TEXT persistiert (kein REAL) — exakte GoBD-Spur,
       Zero-Sum-Prüfung bleibt auf Delta <= 0,01 € genau.
    3. Schreibpfad-Härtung: user_id wird validiert, path traversal
       (z. B. '../../') wird abgelehnt.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from order_execution_engine.models import FillResult, RejectReason, VirtualPortfolio
from order_execution_engine.shadow_execution_engine import TelemetryRecord

_LOG = logging.getLogger(__name__)

SCHEMA_VERSION = 2
_USER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class InvalidUserIdError(ValueError):
    """Wird geworfen, wenn eine user_id den Pfad-Validierungsregeln widerspricht."""


def validate_user_id(user_id: str) -> str:
    """Validiert eine user_id gegen Path-Traversal und ungültige Zeichen.

    Args:
        user_id: Die zu prüfende Benutzer-ID.

    Returns:
        Die validierte ID (unverändert).

    Raises:
        InvalidUserIdError: Bei Leerstring, Sonderzeichen oder Traversal-Mustern.
    """
    if not _USER_ID_RE.match(user_id):
        raise InvalidUserIdError(
            f"Ungültige user_id '{user_id}': nur [A-Za-z0-9_-], "
            "max. 64 Zeichen, kein Pfad-Trenner."
        )
    if ".." in user_id:
        raise InvalidUserIdError(f"Ungültige user_id '{user_id}': Traversal verboten.")
    return user_id


def shadow_data_dir(base_dir: Path, user_id: str) -> Path:
    """Ermittelt das validierte Persistenzverzeichnis für einen Benutzer.

    Args:
        base_dir: Hub-Daten-Root (z. B. data/).
        user_id: Validierungsgeprüfte Benutzer-ID.

    Returns:
        Absoluter Pfad data/{user_id}/shadow/ (wird nicht erzeugt).
    """
    uid = validate_user_id(user_id)
    return (base_dir / uid / "shadow").resolve()


def _dec_to_text(value: Decimal) -> str:
    """Serialisiert Decimal verlustfrei als TEXT."""
    return format(value, "f")


def _text_to_dec(value: str) -> Decimal:
    """Deserialisiert TEXT zurück zu Decimal."""
    return Decimal(value)


@runtime_checkable
class ShadowStorage(Protocol):
    """Austauschbares Speicher-Protokoll (Migrationsweg zu Hub-DB)."""

    def write_telemetry(self, record: TelemetryRecord) -> None:
        """Persistiert einen Telemetrie-Eintrag."""
        ...

    def write_fill(self, fill: FillResult) -> None:
        """Persistiert einen simulierten Fill."""
        ...

    def write_portfolio(self, portfolio: VirtualPortfolio, user_id: str) -> None:
        """Persistiert einen Portfolio-Snapshot."""
        ...

    def close(self) -> None:
        """Gibt Ressourcen frei."""
        ...


class SQLiteShadowStorage:
    """SQLite-Implementierung unter data/{user_id}/shadow/shadow.db.

    Transaktionsgrenze: ein COMMIT pro geschriebenem Datensatz (Autocommit).
    `INSERT OR REPLACE` wird bewusst vermieden — Telemetrie ist append-only,
    Fills sind durch order_id+idx eindeutig.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS telemetry (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id TEXT NOT NULL,
        order_id TEXT,
        latency_ms REAL NOT NULL,
        approved INTEGER NOT NULL,
        reject_reason TEXT,  -- NULL bei genehmigten Signalen (Normalfall)
        status TEXT,
        requested_size TEXT,  -- NULL = vor Messbeginn, nicht: fehlend
        decision_seq INTEGER   -- NULL = vor Messbeginn, nicht: fehlend
    );
    CREATE TABLE IF NOT EXISTS fills (
        order_id TEXT NOT NULL,
        fill_idx INTEGER NOT NULL,
        execution_price TEXT NOT NULL,
        executed_size TEXT NOT NULL,
        slippage TEXT NOT NULL,
        fee TEXT NOT NULL,
        filled_at TEXT NOT NULL,
        latency_ms REAL,
        requested_size TEXT,
        PRIMARY KEY (order_id, fill_idx)
    );
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        taken_at TEXT NOT NULL,
        cash TEXT NOT NULL,
        start_balance TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        peak_equity TEXT NOT NULL,
        positions_json TEXT NOT NULL
    );
    """

    # Migration v1 -> v2 (F1, VM3). Drei Spalten, zwei Backfill-Semantiken.
    # Idempotent: ADD COLUMN schlägt fehl, wenn die Spalte existiert; das
    # wird gefangen, weil SQLite kein "IF NOT EXISTS" für Spalten kennt.
    _MIGRATIONS_V2 = (
        # requested_size (telemetry): nie persistiert, nicht rekonstruierbar.
        # NULL heisst "vor Messbeginn", NICHT "fehlend". Ins Schema, nicht nur
        # ins Ticket: ein undokumentiertes NULL lädt den Nächsten dazu ein,
        # es per Join aus fills zu "reparieren" — Scheingenauigkeit.
        "ALTER TABLE telemetry ADD COLUMN requested_size TEXT",
        # decision_seq (telemetry): existierte nicht; "vor der Messung".
        "ALTER TABLE telemetry ADD COLUMN decision_seq INTEGER",
        # requested_size (fills): hier ist der Backfill `:= executed_size`
        # HISTORISCH WAHR, keine Näherung. In der Vergangenheit wurde nur eine
        # Größe erfasst, und sie war definitionsgemäß die ausgeführte: Die
        # Engine orderte die Konstante (max_order_size_shares) und lehnte
        # alles darüber ab, statt zu kappen. Also kein Platzhalter.
        "ALTER TABLE fills ADD COLUMN requested_size TEXT",
        "UPDATE fills SET requested_size = executed_size WHERE requested_size IS NULL",
    )

    def __init__(self, db_path: Path) -> None:
        """Öffnet (und initialisiert/migriert) die SQLite-Datei.

        Args:
            db_path: Zieldatei, z. B. data/{user_id}/shadow/shadow.db.
                Elternverzeichnis wird angelegt; db_path wird resolved.
        """
        self._db_path = db_path.resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.executescript(self._DDL)
        self._migrate_v2()
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()

    def _migrate_v2(self) -> None:
        """Bringt eine v1-Datei auf v2 (idempotent, additiv)."""
        existing = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM pragma_table_info('telemetry')"
            ).fetchall()
        }
        fill_cols = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM pragma_table_info('fills')"
            ).fetchall()
        }
        for stmt in self._MIGRATIONS_V2:
            table = "fills" if "fills" in stmt else "telemetry"
            cols = fill_cols if table == "fills" else existing
            # ADD COLUMN nur, wenn die Spalte fehlt; das UPDATE immer (es ist
            # idempotent, weil es nur NULL-Zeilen anfasst).
            if stmt.startswith("ALTER TABLE"):
                col = stmt.rsplit("ADD COLUMN ", 1)[1].split()[0]
                if col in cols:
                    continue
            self._conn.execute(stmt)

    def latest_decision_seq(self) -> int:
        """Höchster persistierter `decision_seq` (0, wenn keiner existiert).

        Für die Zähler-Initialisierung nach Prozessneustart: Ohne sie beginnt
        jeder Start wieder bei 1, und die Korrelation Snapshot<->Record
        kollidiert über Sessions hinweg still. `decision_seq` ist nur
        replaysicher, solange der Zähler die Historie kennt.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(decision_seq) FROM telemetry WHERE decision_seq IS NOT NULL"
            ).fetchone()
        value = row[0] if row and row[0] is not None else 0
        return int(value)

    @classmethod
    def for_user(cls, base_dir: Path, user_id: str) -> "SQLiteShadowStorage":
        """Factory mit validiertem Benutzerpfad.

        Args:
            base_dir: Hub-Daten-Root.
            user_id: Benutzer-ID (wird validiert).

        Returns:
            Geöffnete Storage-Instanz.
        """
        directory = shadow_data_dir(base_dir, user_id)
        return cls(directory / "shadow.db")

    def write_telemetry(self, record: TelemetryRecord) -> None:
        """Persistiert einen Telemetrie-Eintrag (append-only).

        Defensive Normalisierung: `TelemetryRecord` verhindert None bereits
        an der Konstruktion (siehe `__post_init__`), aber ein typ-ignorierender
        Aufrufer kann die Wache umgehen. Charter `diagnostic_only=true` heisst:
        Telemetrie darf den Engine-Loop nie crashen. Die Boundary ist der
        letzte Punkt, an dem das garantiert werden kann.

        Die Normalisierung ist bewusst NICHT still — sie loggt eine Warnung,
        sonst maskiert sie genau die Bugs, die sie ueberleben laesst.
        Zielwert ist `RejectReason.NONE` (Semantik: "kein Reject erfasst"),
        nicht NULL: die Spalte ist NOT NULL per Vertrag.
        """
        reason = record.reject_reason
        if not isinstance(reason, RejectReason):
            _LOG.warning(
                "TelemetryRecord.reject_reason ist kein RejectReason (%r) — "
                "normalisiert zu NONE. Der Aufrufer ignoriert den Typvertrag; "
                "produktiv ist das unerreichbar.",
                reason,
            )
            reason = RejectReason.NONE
        with self._lock:
            self._conn.execute(
                "INSERT INTO telemetry (signal_id, order_id, latency_ms, approved,"
                " reject_reason, status, requested_size, decision_seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(record.signal_id),
                    str(record.order_id) if record.order_id else None,
                    record.latency_ms,
                    1 if record.approved else 0,
                    reason.value,
                    record.status.value if record.status else None,
                    _dec_to_text(record.requested_size)
                    if record.requested_size is not None else None,
                    record.decision_seq if record.decision_seq else None,
                ),
            )
            self._conn.commit()

    def write_fill(self, fill: FillResult, fill_idx: int = 0,
                   requested_size: Optional[Decimal] = None) -> None:
        """Persistiert einen Fill (Decimal als TEXT).

        Args:
            fill: Das FillResult.
            fill_idx: Index bei Partial Fills einer Order (Default 0).
            requested_size: Ungekappte angeforderte Größe. `None` = vor
                Messbeginn. Ohne Angabe wird der ausgeführte Wert verwendet —
                das ist für neue Fills korrekt (der Default-Adapter kappt
                nicht) und macht den Aufruf rückwärtskompatibel.
        """
        req = requested_size if requested_size is not None else fill.executed_size
        with self._lock:
            self._conn.execute(
                "INSERT INTO fills (order_id, fill_idx, execution_price, executed_size,"
                " slippage, fee, filled_at, latency_ms, requested_size)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(fill.order_id),
                    fill_idx,
                    _dec_to_text(fill.execution_price),
                    _dec_to_text(fill.executed_size),
                    _dec_to_text(fill.slippage),
                    _dec_to_text(fill.fee),
                    fill.filled_at.isoformat(),
                    fill.latency_ms,
                    _dec_to_text(req),
                ),
            )
            self._conn.commit()

    def write_portfolio(self, portfolio: VirtualPortfolio, user_id: str) -> None:
        """Persistiert einen Portfolio-Snapshot (Positions als JSON, Decimal als TEXT)."""
        validate_user_id(user_id)
        positions = {
            tid: {k: (str(v) if isinstance(v, Decimal) else v)
                  for k, v in pos.model_dump().items()}
            for tid, pos in portfolio.positions.items()
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO portfolio_snapshots (taken_at, cash, start_balance,"
                " realized_pnl, peak_equity, positions_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                    _dec_to_text(portfolio.cash),
                    _dec_to_text(portfolio.start_balance),
                    _dec_to_text(portfolio.realized_pnl),
                    _dec_to_text(portfolio.peak_equity),
                    json.dumps(positions),
                ),
            )
            self._conn.commit()

    def read_fills(self, order_id: str) -> list[tuple[str, str, str, str]]:
        """Liest Fill-Beträge zurück (Decimal-TEXT, exakt) — für Zero-Sum-Prüfung.

        Args:
            order_id: Order-UUID als String.

        Returns:
            Liste von (execution_price, executed_size, slippage, fee) als TEXT.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT execution_price, executed_size, slippage, fee FROM fills"
                " WHERE order_id = ? ORDER BY fill_idx",
                (order_id,),
            ).fetchall()
        return rows

    def close(self) -> None:
        """Schließt die Datenbankverbindung."""
        with self._lock:
            self._conn.close()


class TelemetrySink:
    """Schlanke Senke: leitet TelemetryLogger-Einträge ins Storage um.

    Bindet sich an ShadowExecutionEngine.telemetry, ohne die Engine
    zu ändern — Polling-basiert, idempotent (kein Record wird doppelt
    persistiert).
    """

    def __init__(self, storage: ShadowStorage, telemetry, fills_provider=None) -> None:
        """Initialisiert die Senke.

        Args:
            storage: Ziel-Storage (Protokoll).
            telemetry: TelemetryLogger-Instanz der Engine.
            fills_provider: Optional; Callable(order_id) -> Iterable[FillResult],
                liefert Fills zu einer Order fuer die Persistenz.
        """
        self._storage = storage
        self._telemetry = telemetry
        self._fills_provider = fills_provider
        self._drained = 0

    def drain(self) -> int:
        """Persistiert alle neuen Telemetrie-Einträge (idempotent).

        Returns:
            Anzahl neu persistierter Einträge.
        """
        records = self._telemetry._records  # bewusst intern: Senke- Kopplung
        written = 0
        for record in records[self._drained:]:
            self._storage.write_telemetry(record)
            if self._fills_provider is not None and record.order_id is not None:
                for idx, fill in enumerate(self._fills_provider(record.order_id)):
                    self._storage.write_fill(fill, fill_idx=idx)
            written += 1
        self._drained += written
        return written
