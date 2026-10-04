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
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from order_execution_engine.models import (
    FillResult,
    OrderStatus,
    PeakEvent,
    RejectReason,
    VirtualPortfolio,
)
from order_execution_engine.shadow_execution_engine import TelemetryRecord

_LOG = logging.getLogger(__name__)

SCHEMA_VERSION = 5
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


def _json_dec_as_text(value: object) -> Optional[str]:
    """Cast an der Spaltengrenze: JSON-Mode-Decimal (str) → kanonisches TEXT.

    ``model_dump(mode="json")`` serialisiert Decimal ggf. als ``"1E-16"``.
    Die Spalten sind TEXT (nicht REAL) — Faustregel: JSON-Mode als Transport,
    an der Grenze ``Decimal(str) → format(..., "f")``, Spaltentypen unverändert.
    ``float()`` waere Schema-Bruch und Praezisionsverlust.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return _dec_to_text(value)
    return _dec_to_text(Decimal(str(value)))


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
        side TEXT,
        token_id TEXT,
        market_id TEXT,
        decision_seq INTEGER,
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
    CREATE TABLE IF NOT EXISTS peak_events (
        seq INTEGER PRIMARY KEY,
        raised_at TEXT NOT NULL,
        journal_pos INTEGER NOT NULL,
        peak_equity TEXT NOT NULL,
        marks_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS telemetry_fill_metrics (
        telemetry_seq INTEGER PRIMARY KEY REFERENCES telemetry(seq),
        fill_ratio TEXT,
        levels_consumed INTEGER,
        vwap TEXT,
        vs_touch_ref_bps TEXT,
        vs_signal_bps TEXT,
        capped INTEGER,
        staleness_applied TEXT,
        queue_ahead_at_rest TEXT,
        payload_json TEXT NOT NULL
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

    # Migration v2 -> v3 (Replay-Ledger): Fold-Felder + as_of-Anker auf fills.
    # NULL = Legacy / unfaltbar — Replay raet nicht.
    _MIGRATIONS_V3 = (
        "ALTER TABLE fills ADD COLUMN side TEXT",
        "ALTER TABLE fills ADD COLUMN token_id TEXT",
        "ALTER TABLE fills ADD COLUMN market_id TEXT",
        "ALTER TABLE fills ADD COLUMN decision_seq INTEGER",
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
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._DDL)
        self._migrate_v2()
        self._migrate_v3()
        self._migrate_v4()
        self._migrate_v5()
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

    def _migrate_v3(self) -> None:
        """Bringt eine v2-Datei auf v3 (idempotent): Fold-Spalten auf fills."""
        fill_cols = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM pragma_table_info('fills')"
            ).fetchall()
        }
        for stmt in self._MIGRATIONS_V3:
            col = stmt.rsplit("ADD COLUMN ", 1)[1].split()[0]
            if col in fill_cols:
                continue
            self._conn.execute(stmt)

    def _migrate_v4(self) -> None:
        """Bringt eine v3-Datei auf v4: peak_events-Tabelle (Befund 4).

        CREATE TABLE IF NOT EXISTS ist idempotent; DDL oben deckt Neuanlage ab.
        Hier nur fuer explizite Migration alter Dateien nach Schema-Bump.
        """
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS peak_events (
                seq INTEGER PRIMARY KEY,
                raised_at TEXT NOT NULL,
                journal_pos INTEGER NOT NULL,
                peak_equity TEXT NOT NULL,
                marks_json TEXT NOT NULL
            )
            """
        )

    def _migrate_v5(self) -> None:
        """v4 → v5: Neben-Tabelle telemetry_fill_metrics (Fill-Tiefe Persistenz)."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_fill_metrics (
                telemetry_seq INTEGER PRIMARY KEY REFERENCES telemetry(seq),
                fill_ratio TEXT,
                levels_consumed INTEGER,
                vwap TEXT,
                vs_touch_ref_bps TEXT,
                vs_signal_bps TEXT,
                capped INTEGER,
                staleness_applied TEXT,
                queue_ahead_at_rest TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )

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

        Transport: ``model_dump(mode="json")`` wenn BaseModel — UUID/Enum als
        str. Spaltenliste explizit (keine implizite Feldreihenfolge).
        Decimal-Spalten bleiben TEXT: Cast via ``_json_dec_as_text`` (nicht float).

        Defensive Normalisierung: ``TelemetryRecord`` verhindert None bereits
        an der Konstruktion (Pydantic-Feld / ADR 13), aber ein typ-ignorierender
        Aufrufer (SimpleNamespace) kann die Wache umgehen. Charter
        ``diagnostic_only=true``: Telemetrie darf den Engine-Loop nie crashen.
        Die Boundary ist der letzte Punkt, an dem das garantiert werden kann.

        Die Normalisierung ist bewusst NICHT still — sie loggt eine Warnung.
        Zielwert ist ``RejectReason.NONE``, nicht NULL.
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

        if isinstance(record, BaseModel):
            row = record.model_dump(mode="json")
        else:
            # Defensiver Stub-Pfad (Charter): kein Schema, Attribute lesen.
            row = {
                "signal_id": str(record.signal_id),
                "order_id": str(record.order_id) if record.order_id else None,
                "latency_ms": record.latency_ms,
                "approved": record.approved,
                "status": record.status.value if getattr(record, "status", None) else None,
                "requested_size": (
                    _dec_to_text(record.requested_size)
                    if getattr(record, "requested_size", None) is not None
                    else None
                ),
                "decision_seq": getattr(record, "decision_seq", 0) or None,
            }

        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO telemetry (signal_id, order_id, latency_ms, approved,"
                " reject_reason, status, requested_size, decision_seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["signal_id"],
                    row["order_id"],
                    row["latency_ms"],
                    1 if row["approved"] else 0,
                    reason.value,
                    row["status"],
                    _json_dec_as_text(row["requested_size"])
                    if row.get("requested_size") is not None
                    else None,
                    row["decision_seq"] if row.get("decision_seq") else None,
                ),
            )
            telemetry_seq = int(cur.lastrowid)
            metrics = getattr(record, "fill_metrics", None)
            if metrics is not None:
                self._insert_fill_metrics(telemetry_seq, metrics)
            self._conn.commit()

    def _insert_fill_metrics(self, telemetry_seq: int, metrics: Any) -> None:
        """Schreibt typed Spalten + payload_json (Aufrufer hält den Lock)."""
        slip = metrics.slippage
        payload = metrics.model_dump_json()
        self._conn.execute(
            "INSERT INTO telemetry_fill_metrics ("
            " telemetry_seq, fill_ratio, levels_consumed, vwap,"
            " vs_touch_ref_bps, vs_signal_bps, capped, staleness_applied,"
            " queue_ahead_at_rest, payload_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                telemetry_seq,
                _dec_to_text(metrics.fill_ratio),
                int(metrics.levels_consumed),
                _dec_to_text(metrics.vwap) if metrics.vwap is not None else None,
                (
                    _dec_to_text(slip.vs_touch_ref_bps)
                    if slip.vs_touch_ref_bps is not None else None
                ),
                (
                    _dec_to_text(slip.vs_signal_bps)
                    if slip.vs_signal_bps is not None else None
                ),
                1 if slip.capped else 0,
                (
                    metrics.staleness_applied.value
                    if metrics.staleness_applied is not None else None
                ),
                (
                    _dec_to_text(metrics.queue_ahead_at_rest)
                    if metrics.queue_ahead_at_rest is not None else None
                ),
                payload,
            ),
        )

    def read_fill_metrics(self, telemetry_seq: int) -> Optional[Any]:
        """Liest FillMetrics per payload_json (None wenn keine Neben-Zeile)."""
        from order_execution_engine.fill_simulator import FillMetrics

        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM telemetry_fill_metrics"
                " WHERE telemetry_seq = ?",
                (telemetry_seq,),
            ).fetchone()
        if row is None:
            return None
        return FillMetrics.model_validate_json(row["payload_json"])

    def count_fill_metrics_rows(self) -> int:
        """Anzahl Neben-Zeilen (Test-Seam)."""
        with self._lock:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM telemetry_fill_metrics"
                ).fetchone()[0]
            )

    def write_fill(self, fill: FillResult, fill_idx: int = 0,
                   requested_size: Optional[Decimal] = None,
                   decision_seq: Optional[int] = None) -> None:
        """Persistiert einen Fill (Decimal als TEXT, Spaltenliste explizit).

        Transport: ``model_dump(mode="json")``. Cast an der Spaltengrenze via
        ``_json_dec_as_text`` — Schema bleibt TEXT, kein float/REAL.

        Fold-Spalten (``side``, ``token_id``, ``market_id``, ``decision_seq``):
        aus dem Fill bzw. optionalem ``decision_seq``-Argument. Fehlen sie,
        schreibt NULL — Replay zaehlt die Zeile als unfaltbar.

        Args:
            fill: Das FillResult.
            fill_idx: Index bei Partial Fills einer Order (Default 0).
            requested_size: Ungekappte angeforderte Größe. `None` = vor
                Messbeginn. Ohne Angabe wird der ausgeführte Wert verwendet.
            decision_seq: as_of-Anker; Default aus Fill falls gesetzt, sonst None.
        """
        row = fill.model_dump(mode="json")
        req = requested_size if requested_size is not None else fill.executed_size
        side_val = (
            fill.side.value if fill.side is not None
            else (row.get("side") if isinstance(row.get("side"), str) else None)
        )
        seq = decision_seq
        with self._lock:
            self._conn.execute(
                "INSERT INTO fills (order_id, fill_idx, execution_price, executed_size,"
                " slippage, fee, filled_at, latency_ms, requested_size,"
                " side, token_id, market_id, decision_seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["order_id"],
                    fill_idx,
                    _json_dec_as_text(row["execution_price"]),
                    _json_dec_as_text(row["executed_size"]),
                    _json_dec_as_text(row["slippage"]),
                    _json_dec_as_text(row["fee"]),
                    row["filled_at"],
                    row["latency_ms"],
                    _json_dec_as_text(req),
                    side_val,
                    fill.token_id,
                    fill.market_id,
                    seq,
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

    def write_peak_event(self, event: PeakEvent) -> None:
        """Persistiert einen PeakEvent-Zeugen (append-only, seq als PK).

        Decimal als TEXT, Marks als JSON mit TEXT-Werten. Identischer
        Re-Drain wird toleriert; Inhaltwechsel unter gleicher seq → ValueError.
        """
        marks_json = json.dumps(
            {k: _dec_to_text(v) for k, v in sorted(event.marks.items())}
        )
        payload = (
            event.raised_at.isoformat(),
            event.journal_pos,
            _dec_to_text(event.peak_equity),
            marks_json,
        )
        with self._lock:
            row = self._conn.execute(
                "SELECT raised_at, journal_pos, peak_equity, marks_json"
                " FROM peak_events WHERE seq = ?",
                (event.seq,),
            ).fetchone()
            if row is not None:
                if tuple(row) != payload:
                    raise ValueError(
                        f"peak_events seq={event.seq} bereits mit anderem Inhalt "
                        "belegt (append-only-Verletzung)."
                    )
                return
            self._conn.execute(
                "INSERT INTO peak_events (seq, raised_at, journal_pos,"
                " peak_equity, marks_json) VALUES (?, ?, ?, ?, ?)",
                (event.seq, *payload),
            )
            self._conn.commit()

    def read_peak_events(self) -> list[PeakEvent]:
        """Laedt den PeakEvent-Strom (ORDER BY seq) — Reload-Pfad."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, raised_at, journal_pos, peak_equity, marks_json"
                " FROM peak_events ORDER BY seq"
            ).fetchall()
        return [
            PeakEvent(
                seq=seq,
                raised_at=datetime.fromisoformat(raised_at),
                journal_pos=journal_pos,
                peak_equity=_text_to_dec(peak_equity),
                marks={k: _text_to_dec(v) for k, v in json.loads(marks_json).items()},
            )
            for seq, raised_at, journal_pos, peak_equity, marks_json in rows
        ]

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
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def read_telemetry(
        self, *, upto_decision_seq: Optional[int] = None,
    ) -> list[TelemetryRecord]:
        """Liest Telemetrie chronologisch (decision_seq, seq als Tie-Break).

        Args:
            upto_decision_seq: Optionaler as_of-Anker (inkl.); None = alle.

        Returns:
            Liste von TelemetryRecord (RejectReason.NONE bei NULL).
        """
        sql = (
            "SELECT signal_id, order_id, latency_ms, approved, reject_reason,"
            " status, requested_size, decision_seq FROM telemetry"
        )
        args: tuple[Any, ...] = ()
        if upto_decision_seq is not None:
            sql += " WHERE decision_seq IS NOT NULL AND decision_seq <= ?"
            args = (upto_decision_seq,)
        sql += " ORDER BY decision_seq, seq"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        out: list[TelemetryRecord] = []
        for r in rows:
            out.append(TelemetryRecord(
                signal_id=uuid.UUID(r["signal_id"]),
                order_id=uuid.UUID(r["order_id"]) if r["order_id"] else None,
                latency_ms=float(r["latency_ms"]),
                approved=bool(r["approved"]),
                status=OrderStatus(r["status"]) if r["status"] else None,
                reject_reason=RejectReason(r["reject_reason"] or "NONE"),
                requested_size=(
                    Decimal(r["requested_size"]) if r["requested_size"] else None
                ),
                decision_seq=int(r["decision_seq"] or 0),
            ))
        return out

    def read_fills_all(self) -> list[dict[str, Any]]:
        """Rohzeilen aller Fills, Einfuegereihenfolge (rowid).

        Replay falten — die DB denkt nicht. Keys = Spaltennamen + ``rowid``.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT rowid AS rowid, * FROM fills ORDER BY rowid"
            ).fetchall()
        return [dict(r) for r in rows]

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

    def __init__(self, storage: ShadowStorage, telemetry, fills_provider=None,
                 peak_events_provider=None) -> None:
        """Initialisiert die Senke.

        Args:
            storage: Ziel-Storage (Protokoll).
            telemetry: TelemetryLogger-Instanz der Engine.
            fills_provider: Optional; Callable(order_id) -> Iterable[FillResult],
                liefert Fills zu einer Order fuer die Persistenz.
            peak_events_provider: Optional; Callable() -> Iterable[PeakEvent],
                liefert den append-only PeakEvent-Strom (z. B.
                engine.peak_events) fuer die Zeugen-Persistenz (Befund 4).
        """
        self._storage = storage
        self._telemetry = telemetry
        self._fills_provider = fills_provider
        self._peak_events_provider = peak_events_provider
        self._drained = 0
        self._peaks_drained = 0
        self._fill_rows_written: set[tuple[str, int]] = set()

    def drain(self) -> int:
        """Persistiert alle neuen Telemetrie-Einträge (idempotent).

        Zusaetzlich werden — sofern ein peak_events_provider angeschlossen
        ist — neue PeakEvent-Zeugen append-only persistiert. Rueckgabewert
        zaehlt nur Telemetrie (Bestandsvertrag).

        Returns:
            Anzahl neu persistierter Telemetrie-Einträge.
        """
        records = self._telemetry._records  # bewusst intern: Senke- Kopplung
        written = 0
        for record in records[self._drained:]:
            self._storage.write_telemetry(record)
            if self._fills_provider is not None and record.order_id is not None:
                for idx, fill in enumerate(self._fills_provider(record.order_id)):
                    key = (str(record.order_id), idx)
                    if key in self._fill_rows_written:
                        continue
                    self._storage.write_fill(
                        fill, fill_idx=idx, decision_seq=record.decision_seq,
                    )
                    self._fill_rows_written.add(key)
            written += 1
        self._drained += written
        if self._peak_events_provider is not None:
            events = list(self._peak_events_provider())
            for event in events[self._peaks_drained:]:
                self._storage.write_peak_event(event)
            self._peaks_drained = len(events)
        return written
