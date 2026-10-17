#!/usr/bin/env python3
"""Pre-Flight-Stichprobe vor KeepAlive und ~1 h nach Start.

Exit 0 = grün, Exit 1 = rot (Fail-closed für Messperioden-Start).
"""

from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]


def _criterion_files() -> tuple:
    """Die Dateien, die das Kriterium zitieren — abgeleitet, nicht gepflegt.

    (§5.4au) Eine gepflegte Liste ist die, die veraltet: die vierte Datei,
    die ein Etikett zitiert, steht in ``DERIVED``s Liste erst, wenn jemand
    sie einträgt. Deshalb wird die Liste aus dem Bestand gelesen: jede
    Produktionsdatei, die ein Gate-Etikett als Literal führt, gehört in den
    Satz. Der Code selbst ist immer dabei.

    Das ist billig (ein Dateidurchlauf, einmal pro Gate-Lauf) und wächst von
    selbst: wer ein Etikett in eine neue Datei schreibt, macht sie damit
    sichtbar — statt sie unsichtbar zu lassen, bis jemand daran denkt.
    """
    root = Path(__file__).resolve().parents[1]
    marks = ("LEDGER_CONSISTENT", "PROVISIONAL_", "TELEMETRY_RECONCILIATION")
    found = {Path(__file__).resolve()}
    for p in root.rglob("*"):
        if "__pycache__" in p.parts or p.parent.name == "tests":
            continue
        if p.suffix not in (".py", ".md"):
            continue
        if p.resolve() == Path(__file__).resolve():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(m in txt for m in marks):
            found.add(p.resolve())
    return tuple(sorted(str(p.relative_to(REPO)) for p in found))


# Rückwärtskompatibel für Zeugen, die die Liste als Konstante lesen.
CRITERION_FILES = _criterion_files()
OPS = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from order_execution_engine.allowlist_freeze import (  # noqa: E402
    REQUIRED_FIELDS,
    FreezeError,
    load_freeze,
    token_ids_from_freeze,
)
from order_execution_engine.market_data_feed import PolymarketWsFeed  # noqa: E402

DEFAULT_FREEZE = OPS / "allowlist.freeze.json"
DEFAULT_POLICY = OPS / "run_policy.json"
# launchd-writable runtime (THX volumes are EPERM for LaunchAgents)
_DEFAULT_APP = Path.home() / "Library" / "Application Support" / "agentx"
DEFAULT_DATA_ROOT = _DEFAULT_APP / "shadow_live"
DEFAULT_NEWS_JSONL = _DEFAULT_APP / "news_scores.jsonl"
DEFAULT_MIN_RUN_ID = 7
# Wie alt darf der jüngste Fill sein, damit "DELIVERING" gilt? Der Dispatcher
# taktet stündlich; zwei Takte ohne Fill heißt: der jüngste Beleg ist kein
# Betrieb mehr. Nicht der Laufanfang ist der Maßstab, sondern die Gegenwart
# (§5.4bg) — sonst gilt ein Fill von vor 11 Tagen als frisch, weil er innerhalb
# des Lauf-Fensters liegt.
FRESH_FILL_S = 2 * 3600.0

# Keine Untergrenze mehr (§5.4v). Sie hieß MIN_TELEMETRY_ROWS = 4 und ihr
# Wert stammte aus Run 9 — also aus 100 % einer gefilterten Menge. Sie war in
# beide Richtungen falsch: ließ 1.000 Zeilen durch, brach einen Lauf mit drei
# fehlerfreien Dispatches. Ihr einziger Zweck ("0 == 0 ist keine Prüfung")
# wird jetzt von der Null-Bedingung im Gate getragen: es muß Verkehr da sein,
# sonst gibt es nichts zu bilanzieren.


def _gate_blob_hash() -> dict[str, str]:
    """Identify the version of *this* file that produced the verdict.

    A verdict names the run but not the judge. `git hash-object` gives the
    blob id (SHA-1, 40 hex) that also appears in `git rev-parse <c>:<path>`,
    so a recorded verdict can be matched to a commit. Falls back to SHA-256
    of the bytes when git is unavailable — the label says which one it is.
    """
    this = Path(__file__).resolve()
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "hash-object", str(this)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return {"blob": out.stdout.strip(), "source": "git hash-object",
                **_gate_commit_ref(this)}
    except (subprocess.SubprocessError, OSError):
        import hashlib

        return {
            "blob": hashlib.sha256(this.read_bytes()).hexdigest(),
            "source": "sha256 (git unavailable)",
        }


def _gate_commit_ref(this: Path) -> dict[str, str]:
    """Welcher Commit trägt diesen Blob — und trägt HEAD ihn noch?

    Ein Hash ohne Commit ist die alte Form: er zeigt auf zwei Commits und
    nennt keinen. ``f86a7901`` steht in ``e88f6d07`` *und* ``08ad2454`` —
    beide Commits tragen denselben Prüfer, geändert wurden nur die Tests.
    Diese Funktion macht die Aussage prüfbar: Blob im Commit vs. Blob auf
    der Platte.

    Laufzeitfehler dürfen die Ausgabe nicht verhindern (ein Prüfer, der
    beim Datieren stirbt, datiert nichts) — deshalb leerer Fallback.
    """
    def _git(*args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip()

    try:
        rel = this.relative_to(REPO).as_posix()
        head = _git("rev-parse", "HEAD")
        committed = _git("rev-parse", f"HEAD:{rel}")
    except (subprocess.SubprocessError, OSError, ValueError):
        return {"commit": "unknown", "committed_blob": "unknown"}
    work = _git("hash-object", str(this))
    # DERIVED := der Blob auf der Platte ist NICHT der Blob im HEAD-Commit.
    # Definitionsbereich bewusst der Blob-Vergleich, nicht `git status`:
    # `--porcelain` ohne `--ignored` hätte den __pycache__ nie gezeigt
    # (deshalb die 0 in §5.4d), und mit `--ignored` feuert es immer —
    # ignoriert Artefakte im Tree liegen ignoriert daneben. Die Frage hier ist
    # nicht "ist der Baum sauber", sondern "ist genau dieser Text committet".
    #
    # Seit §5.4aq ist der Definitionsbereich nicht mehr diese eine Datei,
    # sondern der KRITERIUMSSATZ: das Kriterium lebt in preflight_check.py,
    # in START.md und in der Akte. Eine Datei kann nicht alle drei sein —
    # deshalb prüft der Marker alle drei und nennt sie einzeln.
    parts = {}
    for rel_part in CRITERION_FILES:
        try:
            work_p = _git("hash-object", str((REPO / rel_part)))
            head_p = _git("rev-parse", f"HEAD:{rel_part}")
        except Exception:  # noqa: BLE001 — untracked/neu: dann ist es DERIVED
            work_p, head_p = "?", "?"
        parts[rel_part] = "ok" if work_p == head_p else "DERIVED"
    drifted = [k for k, v in parts.items() if v == "DERIVED"]
    suffix = "" if not drifted else (
        f"  DERIVED ({', '.join(Path(x).name for x in drifted)} != HEAD-Blob)"
    )
    return {
        "commit": head[:8],
        "committed_blob": committed[:12] + suffix,
    }

REQUIRED_CONFIG_KEYS = (
    "max_book_age_ms",
    "max_news_age_s",
    "staleness_policy",
    "resting_model",
    "signal_ref_mode",
    "market_allowlist",
    "git_commit",
    "ws_token_ids",
)


@dataclass(frozen=True)
class GateResult:
    """Ein Checkpoint-Gate (GREEN/RED), analog STALE_SNAPSHOT."""

    name: str
    status: str  # GREEN | RED
    detail: Any = None
    # Adresse des Urteils (§5.4bk): ein `RED` ohne genannte Bedingung ist
    # ein Zustand, keine Aussage. Wer `RED` liest und handeln soll, braucht
    # die Nummer der Bedingung, nicht das Etikett — sonst ist es die Form,
    # die in Runde 1 `BLOCKED` hieß: wahr, begründet, unlesbar.
    reason: str = ""
    # Und die, an der gehandelt werden soll (§5.4br): dieses Gate bewertet
    # Buchführung, nicht Betrieb. `unattributed` blockt, `stalled_for`
    # nicht — aber `RED` sieht für beide gleich aus, und wer es liest,
    # repariert ohne `blocking` die falsche Seite.
    #   ledger  — der Ledger ist unvollständig (Bedingungen 0-4)
    #   service — der Dienst liefert nicht (ein eigenes Etikett, nie hier)
    #   both    — beides rot
    blocking: str = ""


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def _fail(msg: str, errors: list[str]) -> None:
    print(f"FAIL {msg}")
    errors.append(msg)


def _warn(msg: str) -> None:
    print(f"WARN {msg}")


def gate_telemetry_reconciliation(
    conn: sqlite3.Connection,
    *,
    min_run_id: int = DEFAULT_MIN_RUN_ID,
) -> GateResult:
    """RED, wenn erfolgreiche Dispatches ohne korrespondierende Telemetrie existieren.

    Erfolgreich = Zeile in ``dispatched_signals`` ab ``telemetry_runs.started_at``
    von ``min_run_id``, und *nicht* in ``bridge_discards`` (Claim vor Resolve
    würde sonst unresolved/no_book als Phantom-Dispatch zählen).

    Erkennt stille Telemetry-Write-Ausfälle, die bei dispatched=0 von
    „keine Aktivität“ nicht unterscheidbar wären.

    **Die vier RED-Bedingungen unten sind mit ``_gate_criterion`` gepaart.**
    Wird eine hier geändert, muß der Satz dort mitgeändert werden — sonst
    behauptet die Ausgabe eine Regel, die sie nicht anwendet.
    """
    row = conn.execute(
        "SELECT started_at FROM telemetry_runs WHERE run_id = ?",
        (min_run_id,),
    ).fetchone()
    if row is None:
        # Kein Lauf = nichts gemessen. GREEN wäre die Tautologie in ihrer
        # reinsten Form: ein Etikett über einer Prüfung, die nicht stattfand.
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            reason="kein Lauf im Fenster — telemetry_runs lieferte "
                   "keine started_at",
            detail={"note": f"no telemetry_runs.run_id={min_run_id}",
                    "underrun": True},
        )
    started_at = float(row[0])
    dispatched = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM dispatched_signals d
            WHERE d.dispatched_at >= ?
              AND NOT EXISTS (
                SELECT 1 FROM bridge_discards b WHERE b.item_id = d.item_id
              )
            """,
            (started_at,),
        ).fetchone()[0]
    )
    telemetry_rows = int(
        conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE run_id >= ?",
            (min_run_id,),
        ).fetchone()[0]
    )
    # Vollständigkeit: die Bezugszahl muss sich vollständig zerlegen lassen.
    reasons = {
        str(r): int(c)
        for r, c in conn.execute(
            "SELECT reject_reason, COUNT(*) FROM telemetry WHERE run_id >= ? "
            "GROUP BY 1",
            (min_run_id,),
        )
    }
    # Join-Kardinalität: die Id, über die der Replay-/Dispatch-Join läuft.
    # NICHT item_id — das ist eine Eindeutigkeitsaussage über eine Spalte,
    # keine über den Join. Gültig ist das *Paar* (run_id, decision_seq):
    # der Zähler startet je Prozess neu (Run 9 beginnt wieder bei 1).
    keyed = int(
        conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE run_id >= ? "
            "AND decision_seq IS NOT NULL",
            (min_run_id,),
        ).fetchone()[0]
    )
    distinct_pair = int(
        conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT run_id, decision_seq "
            "FROM telemetry WHERE run_id >= ? AND decision_seq IS NOT NULL)",
            (min_run_id,),
        ).fetchone()[0]
    )
    # Je Lauf prüfen: innerhalb eines run_id darf decision_seq nicht kollidieren.
    pairs_ok = _pairs_unique_per_run(conn, min_run_id=min_run_id)
    unattributed = dispatches_without_telemetry(
        conn, min_run_id=min_run_id, started_at=started_at,
    )
    # Die andere Richtung: Zeile ohne Erfolg. (1) prüft rows-vs-keyed —
    # beides innerhalb des Ledgers. Diese Zahl prüft zwischen Ledger und
    # Dispatcher, und sie ist die einzige, die eine Überbehauptung sieht.
    orphan_rows = telemetry_without_dispatch(
        conn, min_run_id=min_run_id, started_at=started_at,
    )
    run_closed = latest_run_is_closed(conn)
    # Alter des offenen Laufs — die zweite Hälfte der Aussage. Der Block
    # ohne Zahl ist ein Zustand, der Block mit Zahl eine Beobachtung. Sie
    # steht NEBEN dem Etikett (§5.4as), nicht darin: sie ändert sich
    # stündlich, das Urteil nicht.
    open_hours = max(0.0, (time.time() - started_at) / 3600.0)
    # Geliefert = genehmigte Entscheidungen. Nicht zu verwechseln mit
    # dispatched (Angebote an die Bridge) und nicht mit classifiable
    # (Terminalentscheidungen, Ablehnungen eingeschlossen).
    delivered = int(
        conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE run_id >= ? AND approved = 1",
            (min_run_id,),
        ).fetchone()[0]
    )
    delivered_since = _delivered_since(conn, min_run_id=min_run_id,
                                       in_scope=delivered)
    observed_hours = max(0.0, (time.time() - float(started_at)) / 3600.0)
    rows_per_hour = (
        telemetry_rows / observed_hours if observed_hours > 0 else None
    )
    in_scope = dispatches_in_scope(conn, started_at=started_at)
    # Verkehr, der VOR dem Fenster liegt und deshalb in keinem Urteil
    # auftaucht (§5.4ae). Genau eine Zeile: 2026-10-04 08:00:08,
    # Warmup, unresolved_asset. 360 = 1 + 299 + 60 — ohne diese Zahl
    # stimmt die Versöhnung auf 359 und niemand sieht die eine Zeile.
    before_scope = int(
        conn.execute(
            "SELECT COUNT(*) FROM dispatched_signals WHERE dispatched_at < ?",
            (started_at,),
        ).fetchone()[0]
    )
    coverage_pct = (100.0 * telemetry_rows / in_scope) if in_scope else None
    # Die Lieferkette, vier Stufen — und `delivered` ist nur die dritte
    # (§5.4az). `fills` zählt die vierte, unabhängig von `approved`: eine
    # Entscheidung kann PARTIALLY_FILLED sein, ohne daß `approved = 1` im
    # Fenster liegt. Beide Zahlen getrennt, weil sie zwei Aussagen tragen.
    # `fills` kann fehlen (ältere Schemata, Fixtures ohne Fill-Schicht).
    # Dann ist die vierte Stufe nicht gemessen — `None`, nicht `0`: eine
    # Null würde behaupten, es sei nichts geliefert worden.
    #
    # `fills` hat keine Statusspalte (§5.4be): Vollständigkeit steht nur in
    # `telemetry.status`, und dort als Urteil des Ausführers. Der Fill kennt
    # nur Mengen. Also rechnen wir — `sum(executed)/sum(requested)` ist die
    # Zahl, die den Dienst beschreibt, nicht `COUNT(*)`. Bei seq 12: 5 von 5
    # ausgeführt (Quotient 1,0), aber 5 von 100 angefragt (Quotient 0,05).
    # Die Zeile sagte `PARTIALLY_FILLED`, obwohl der Fill voll war — und die
    # Akte las daraus "1 Fills".
    # Die Klammer eng halten (§5.4bx): erst `fills` allein, dann der JOIN.
    # Erste Fassung umspannte beides mit einem `except` — fehlte `telemetry`,
    # verschwand auch `fills_total`, und der Bericht behauptete, es gäbe
    # keine Fill-Schicht. Das ist dieselbe Form wie `WHERE` über zwei Typen
    # (Runde 18) und `try` über zwei Tabellen (Runde 21): der Fehler war
    # nie der `except`, sondern sein Umfang.
    try:
        _f = conn.execute(
            "SELECT COUNT(*), SUM(CAST(executed_size AS REAL)),"
            " SUM(CAST(requested_size AS REAL)) FROM fills"
        ).fetchone()
        fills_total = int(_f[0])
        _ex, _rq = _f[1], _f[2]
        fill_ratio = (round(_ex / _rq, 6)
                      if _ex is not None and _rq else None)
        _fs = conn.execute("SELECT MAX(filled_at) FROM fills").fetchone()[0]
    except sqlite3.OperationalError:
        fills_total, fill_ratio, _fs = None, None, None
    # Voll / teilweise: braucht `telemetry` — eigener Versuch, eigener Ausfall.
    try:
        _v = conn.execute(
            "SELECT SUM(CASE WHEN t.status = 'FILLED' THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN t.status = 'PARTIALLY_FILLED' THEN 1 ELSE 0 END)"
            " FROM fills f JOIN telemetry t ON t.order_id = f.order_id"
        ).fetchone()
        fills_full, fills_partial = int(_v[0] or 0), int(_v[1] or 0)
    except sqlite3.OperationalError:
        # `fills` vorhanden, `telemetry` nicht — dann fehlt das Urteil,
        # nicht die Menge. Null hiere wäre eine Behauptung über Fills,
        # die es sehr wohl gibt.
        fills_full, fills_partial = None, None
    # Zeitformate sind heterogen (§5.4bc): dispatched_at/started_at = REAL
    # (unixepoch), fills.filled_at = TEXT ISO-8601, telemetry = gar keins.
    # Deshalb wird das Feld ausgegeben, wie es gespeichert ist — nicht in
    # eine Zahl gekleidet, die es nicht ist.
    if isinstance(_fs, (int, float)) and _fs:
        last_fill = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_fs))
    else:
        last_fill = str(_fs) if _fs else None
    # NO_DELIVERY heißt: es gab Erfolge, aber keine Lieferung — der Dienst
    # steht, während der Ledger stimmt (§5.4ba). Das ist ein zweites
    # Etikett, kein sechstes Wort im ersten: ein Etikett kann nicht
    # gleichzeitig "konsistent" und "steht still" sagen.
    # Ein Etikett "DELIVERING" neben einem Fill von vor 11 Tagen sagt
    # "läuft", während das Letzte, was lief, zwei Wochen alt ist. `delivered`
    # ist ein Zähler, kein Datum — die Frage "liefert es jetzt?" entscheidet
    # nur `last_fill` (§5.4be).
    #
    # Und die Grenze ist nicht der Laufanfang: das Fenster beginnt am 04.10.,
    # der Fill liegt am 06.10. — 2,4 Tage NACH Fensterbeginn, also "frisch"
    # im Vergleich, obwohl seither 11 Tage vergangen sind. Der Maßstab ist
    # der Abstand zum letzten Erfolg, nicht zum ersten (§5.4bg).
    _fresh_fill = False
    stalled_for_h = None
    if _fs is not None:
        try:
            _ts = float(_fs)
        except (TypeError, ValueError):
            # ISO-8601-Text, kein Epoch — der Typ-Bruch aus §5.4bc.
            try:
                _ts = datetime.datetime.fromisoformat(
                    str(_fs).replace("Z", "+00:00")).timestamp()
            except ValueError:
                _ts = None
        # Toleranz: eine Stunde (der Takt des Dispatchers) plus Beobachtungs-
        # rest. Danach ist der jüngste Fill ein Beleg, kein Betrieb.
        _fresh_fill = (_ts is not None
                       and (time.time() - _ts) <= FRESH_FILL_S)
        # Zwei Dauern, zwei Achsen (§5.4bl). `open_for` läuft gegen
        # `started_at` (der Lauf), `stalled_for` gegen jetzt (der Dienst).
        # Beide sind richtig — solange die Achse im Feldnamen steht. Ein
        # Feld `alter` ohne Achse war in dieser Akte zweimal falsch.
        stalled_for_h = (round((time.time() - _ts) / 3600.0, 1)
                         if _ts is not None else None)

    if delivered > 0 and _fresh_fill:
        delivery_label = "DELIVERING"
    elif delivered > 0 or dispatched > 0:
        # Es gab Erfolge, aber keine genehmigte Zeile im Fenster. Ob der
        # Dienst steht, entscheidet die vierte Stufe — nicht die Summe
        # aller Fills: ein Fill von vor 13 Tagen ist kein Betrieb, sondern
        # ein Beleg. (Erste Fassung prüfte `fills_total == 0` und nannte
        # Run 9 bei 1 Fill "NO_TRAFFIC" — falsch in beide Richtungen.)
        #
        # Und ein TEILFILL ist kein Fill (§5.4be). 5 von 5 ausgeführt, aber
        # 5 von 100 angefragt: die Order wurde zu 5 % bedient. Ein Etikett
        # "NO_DELIVERY" neben "1 Fills" sagte "keine" und trug eine 1 —
        # die Form, die diese Akte dreimal korrigiert hat.
        delivery_label = "DELIVERY_STALLED_SINCE"
    else:
        delivery_label = "NO_TRAFFIC"
    # Der Positivfall (§5.4bf): `order_id` ist der Fremdschlüssel, der
    # existiert — aber nur in 8 von 34 Zeilen. `telemetry_seq` ist in allen
    # 361 Dispatches NULL, also läuft die Zuordnung über `decision_seq`,
    # eine Reihenfolge-Annahme über zwei Reihenfolgen. Der eine Fill zeigt,
    # daß die Annahme an der Stelle falsch ist, an der sie zählt.
    try:
        fk = conn.execute(
            "SELECT COUNT(*), COUNT(order_id) FROM telemetry"
        ).fetchone()
        fk_rows, fk_set = int(fk[0]), int(fk[1])
    except sqlite3.OperationalError:
        fk_rows, fk_set, paired = None, None, None
    # `paired` hängt an `fills` — der FK-Bericht nicht (§5.4bt). Fehlt die
    # Fill-Schicht, bleibt der Befund über `order_id` gültig: der Schreiber
    # ist unabhängig davon, ob es Fills gibt. Erste Fassung umspannte beide
    # mit einem `except` und ließ den Bericht mit der Tabelle verschwinden.
    if fk_rows is not None:
        try:
            paired = int(conn.execute(
                "SELECT COUNT(*) FROM fills f"
                " JOIN telemetry t ON t.order_id = f.order_id"
            ).fetchone()[0])
        except sqlite3.OperationalError:
            paired = None
    # 8/34 ist keine Quote (§5.4bs). `order_id` steht genau dann, wenn eine
    # Order entstand: 26× nicht (korrekt leer), 8× gesetzt. Der Schreiber
    # funktioniert vollständig — 8 von 8, nicht 8 von 34. Die Bezugsgröße
    # ist die Zahl der ORDER-Schritte, nicht die der Entscheidungen.
    try:
        fk_expected = int(conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE requested_size IS NOT NULL"
        ).fetchone()[0])
    except sqlite3.OperationalError:
        fk_expected = None
    detail = {
        "min_run_id": min_run_id,
        "started_at": started_at,
        "observed_hours": observed_hours,
        "rows_per_hour": rows_per_hour,
        "dispatched_in_scope": in_scope,
        "dispatched_before_scope": before_scope,
        "coverage_pct": coverage_pct,
        "dispatched_success": dispatched,
        "telemetry_rows": telemetry_rows,
        "decision_seq_keyed": keyed,
        "decision_seq_distinct_pair": distinct_pair,
        "decision_seq_unique_per_run": pairs_ok,
        "reasons": reasons,
        "classifiable": sum(reasons.values()),
        "unattributed": unattributed,
        "orphan_rows": orphan_rows,
        "run_closed": run_closed,
        "open_for_hours": round(open_hours, 1),
        "delivered": delivered,
        "delivered_since": delivered_since,
        "delivery": delivery_label,
        "fills_total": fills_total,
        "fills_full": fills_full,
        "fills_partial": fills_partial,
        "fill_ratio": fill_ratio,
        # Achse im Namen: gegen jetzt, nicht gegen started_at.
        "stalled_for_h": stalled_for_h,
        "last_fill": last_fill,
        "fk_rows": fk_rows,
        "fk_set": fk_set,
        "fk_paired": paired,
        "fk_expected": fk_expected,
    }
    # Null-Bedingung statt Untergrenze (§5.4v).
    #
    # Die Sorge war richtig: rows == dispatched_success gilt perfekt, wenn
    # beide 0 sind — ein leerer Dienst hat einen vollständig konsistenten
    # Ledger. Die Antwort darauf ist aber nicht eine Zahl, sondern die
    # Frage "hat der Dienst seit seinem Start überhaupt etwas erzeugt".
    #
    # Die alte Untergrenze MIN_TELEMETRY_ROWS = 4 war in beide Richtungen
    # falsch: sie ließ 1.000 Zeilen durch und brach einen Lauf mit drei
    # Dispatches, die alle korrekt ausgeliefert wurden. Ihr Wert war der
    # Wert von Run 9 — also 100 % einer gefilterten Menge.
    #
    # Diese Bedingung erfindet keine Rate und keinen Wert aus den Daten:
    # sie prüft, ob der Verkehr existiert. Was danach gilt, prüft (1).
    if dispatched == 0 and telemetry_rows == 0:
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            blocking="ledger",
            reason="(0) underrun: kein Verkehr im Fenster — "
                   "dispatched == 0 und telemetry_rows == 0",
            detail={**detail, "underrun": True, "empty_traffic": True},
        )
    # Kardinalität: jede Telemetriezeile braucht ihren Schlüssel, und der
    # Schlüssel darf sich weder je Lauf noch über Läufe wiederholen.
    if telemetry_rows != keyed:
        return GateResult(
            name="TELEMETRY_RECONCILIATION", status="RED",
            blocking="ledger",
            reason=f"(1) schreibseite: telemetry_rows={telemetry_rows} != "
                   f"decision_seq-keyed={keyed} — Zeile ohne Schlüssel",
            detail=detail,
        )
    if keyed != distinct_pair or not pairs_ok:
        return GateResult(
            name="TELEMETRY_RECONCILIATION", status="RED",
            blocking="ledger",
            reason=f"(2) schluessel: keyed={keyed}, distinct(run_id,"
                   f"decision_seq)={distinct_pair}, je Run eindeutig="
                   f"{pairs_ok}",
            detail=detail,
        )
    # Vollständigkeit: ein Dispatch ohne Telemetriezeile ist nicht
    # "unbedenklich" — er ist eine unklassifizierte Terminalentscheidung.
    # < wäre grün über einer Lücke (Run 8: 30 Zeilen vs. 34 Dispatches).
    if unattributed > 0:
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            blocking="ledger",
            reason=f"(3) unattributed: {unattributed} Dispatch(es) ohne "
                   f"Telemetriezeile — Erfolg ohne Beleg",
            detail=detail,
        )
    # Die Gegenrichtung (§5.4ac). Bis hierher war nur Erfolg-ohne-Zeile
    # blockierend; Zeile-ohne-Erfolg ging grün durch, weil die Bilanz (4)
    # innerhalb des Ledgers gilt und die Überbehauptung zwischen Ledger und
    # Dispatcher liegt — auf genau der Grenze, für die (1) zuständig ist.
    if orphan_rows > 0:
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            blocking="ledger",
            reason=f"(3b) orphan: {orphan_rows} Zeile(n) ohne Erfolg — "
                   f"Überbehauptung",
            detail={**detail, "overclaim": True},
        )
    if dispatched != sum(reasons.values()):
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            blocking="ledger",
            reason=f"(4) bilanz: dispatched={dispatched} != "
                   f"sum(reasons)={sum(reasons.values())}",
            detail=detail,
        )
    return GateResult(
        name="TELEMETRY_RECONCILIATION",
        # Nicht GREEN: das Gate prüft Identitäten über einer Menge, nicht
        # ob etwas ausgeliefert wurde. Run 9 hat 4 Zeilen, 4 × INVALID_PRICE,
        # 0 geliefert — und besteht alle. GREEN verspräche Funktion;
        # LEDGER_CONSISTENT verspricht genau, was gehalten wird.
        #
        # Ein offener Lauf trägt jetzt ein eigenes Etikett (§5.4ad): er ist
        # keine Beobachtung, sondern ein Bruchstück. „PROVISIONAL" sagt, daß
        # die Zahl ein Stand ist und keine Tatsache — sie kann sich ändern,
        # ohne daß der Ledger sich verschlechtert hat.
        # Der ZUSTAND, nicht die Anzeige (§5.4as): das Etikett ist wieder
        # idempotent — solange nichts geschieht, ändert es sich nicht. Die
        # Dauer steht daneben (open_for_hours), nicht darin. Ein Urteil, das
        # sich ohne Zustandsänderung ändert, ist keine Aussage mehr, sondern
        # eine Uhr.
        status="LEDGER_CONSISTENT" if run_closed
        else "PROVISIONAL_LEDGER_CONSISTENT",
        # GRÜN blockt nichts — und das muß *dastehen*, nicht fehlen: ein
        # Feld, das bei RED gefüllt und bei GRÜN leer ist, ist keine
        # Auskunft, sondern eine Auslassung (§5.4br).
        blocking="none",
        detail=detail,
    )


def telemetry_without_dispatch(
    conn: sqlite3.Connection,
    *,
    min_run_id: int,
    started_at: float,
) -> int:
    """Telemetriezeilen ohne Erfolgs-Dispatch — die fehlende Richtung (§5.4ac).

    ``dispatches_without_telemetry`` zählt Erfolg-ohne-Zeile. Das Gegenstück
    fehlte, und damit war die einzige Richtung, die (1) durchließ, die, in
    der der Ledger mehr behauptet als geschehen ist: ``rows > success`` ist
    grün, weil die Bilanz (4) innerhalb des Ledgers gilt und die
    Überbehauptung zwischen Ledger und Dispatcher liegt — genau auf der
    Grenze, für die (1) zuständig ist.

    Zählung wie in ``dispatches_without_telemetry``, nur umgekehrt: jede
    Telemetriezeile muß eine passende Erfolgs-Position haben
    (``decision_seq`` == laufende Nummer der Erfolgs-Dispatches im Fenster).
    """
    return int(
        conn.execute(
            """
            SELECT COUNT(*) FROM telemetry t
            LEFT JOIN (
              SELECT row_number() OVER (
                       ORDER BY d.dispatched_at, d.item_id) AS rn
              FROM dispatched_signals d
              WHERE d.dispatched_at >= ?
                AND NOT EXISTS (
                  SELECT 1 FROM bridge_discards b WHERE b.item_id = d.item_id
                )
            ) s ON t.decision_seq = s.rn
            WHERE t.run_id >= ? AND s.rn IS NULL
            """,
            (started_at, min_run_id),
        ).fetchone()[0]
    )


def run_end_schema(conn: sqlite3.Connection) -> dict:
    """Der Grund, nicht der Boolean (§5.4ao).

    Ein Zeuge gegen einen konstanten Wert prüft den Wert. Der Grund ist das
    Schema: ``telemetry_runs`` hat kein ``closed_at``. Solange das so ist,
    *kann* kein Lauf geschlossen sein — und das ist die Aussage, die man
    prüfen muß. Wandert ``closed_at`` ins Schema, ändert sich hier etwas,
    bevor sich das Etikett ändert.
    """
    cols = [c[1] for c in conn.execute("PRAGMA table_info(telemetry_runs)")]
    return {
        "has_closed_at": "closed_at" in cols,
        "has_status": "status" in cols,
        "columns": cols,
    }


def latest_run_is_closed(conn: sqlite3.Connection) -> bool:
    """Ist der jüngste Lauf geschlossen?

    ``telemetry_runs`` hat **keine** Spalte für ein Ende. Ein Lauf ist damit
    per Definition offen, solange kein späterer ihn ablöst. Das ist keine
    Lücke der Abfrage, sondern des Schemas: ein offener Lauf ist keine
    Beobachtung, sondern ein Bruchstück — und ein Bruchstück sollte kein
    Urteil tragen (§5.4ad).

    Die Funktion liest das Schema, statt ``False`` zu behaupten: kommt
    ``closed_at`` dazu, liest sie es (heute nicht vorhanden) und der
    Zeuge ``test_closed_at_schema_is_the_reason`` bricht an der Stelle,
    an der die Nachricht hingehört.
    """
    schema = run_end_schema(conn)
    if not schema["has_closed_at"]:
        return False
    row = conn.execute(
        "SELECT closed_at FROM telemetry_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return bool(row and row[0] is not None)


def dispatches_without_telemetry(
    conn: sqlite3.Connection,
    *,
    min_run_id: int,
    started_at: float,
) -> int:
    """Erfolgs-Dispatches ohne Telemetriezeile (unklassifiziert, Warn-Stufe).

    Zählung über ``decision_seq``: Engine und Storage teilen die Id je
    Entscheidung (F1/VM3). ``signal_id`` ist nicht joinbar — ``item_id`` aus
    der Bridge ist ein MD5-Hash, ``telemetry.signal_id`` eine UUID.
    """
    return int(
        conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT d.item_id, row_number() OVER (
                       ORDER BY d.dispatched_at, d.item_id) AS rn
              FROM dispatched_signals d
              WHERE d.dispatched_at >= ?
                AND NOT EXISTS (
                  SELECT 1 FROM bridge_discards b WHERE b.item_id = d.item_id
                )
            ) s
            LEFT JOIN telemetry t
              ON t.run_id >= ? AND t.decision_seq = s.rn
            WHERE t.seq IS NULL
            """,
            (started_at, min_run_id),
        ).fetchone()[0]
    )


def _blocking_callers() -> set:
    """Wer ruft das Gate blockierend auf? (§5.4at)

    Gesucht wird nach Importen des Gate-Moduls in Produktionscode — außer
    der CLI selbst. Ein Import ist nicht automatisch ein Aufruf, aber er
    ist die Vorbedingung: ohne Import kann niemand blocken. Was hier leer
    zurückkommt, ist ein Text ohne Wirkung — und das ist eine Aussage, die
    auf die Urteilszeile gehört, nicht in den Bericht.
    """
    root = Path(__file__).resolve().parents[1]
    hits = set()
    for py in root.rglob("*.py"):
        if py.parent.name == "tests" or "__pycache__" in py.parts:
            continue
        if py.resolve() == Path(__file__).resolve():
            continue
        src = py.read_text(encoding="utf-8", errors="ignore")
        if "preflight_check import" in src or (
            "import preflight_check" in src and "ops" in src
        ):
            hits.add(py.name)
    return hits


def _verdict_readers() -> set:
    """Wer liest die Urteilszeile? (§5.4bb)

    ``_blocking_callers()`` findet Importe — und kann die Verdrahtung nicht
    sehen, die am 20.10. passiert: der erste Aufrufer wird ein Cronjob sein,
    der *die Ausgabe* liest. Ein Import, der nie kommt, und ein Cron, der
    ``grep verdict`` macht, sind zwei verschiedene Arten von Wirkung.

    Gesucht wird außerhalb der Testsuite nach Skripten, die das Gate
    starten oder seine Zeile greppen. Ein Treffer heißt: jemand handelt
    nach diesem Urteil. Null Treffer heißt: das Urteil ist heute ein Text,
    unabhängig davon, ob es blockierend *wäre*.
    """
    root = Path(__file__).resolve().parents[1]
    hits = set()
    needles = ("preflight_check.py", "verdict:", "LEDGER_CONSISTENT")
    for p in root.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        if p.parent.name == "tests" or p.suffix not in (
            ".py", ".sh", ".yml", ".yaml", ".plist", ".toml", ".cfg",
        ):
            continue
        if p.resolve() == Path(__file__).resolve():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(n in txt for n in needles):
            hits.add(p.name)
    return hits


def _print_process_age() -> None:
    """``etime`` des laufenden Runners — die eine Zeile, die nicht rückdatierbar ist.

    §5.1 hat sie als stehende Ist-Ausgabe eingeführt, weil ``etime`` monoton
    wächst: man kann einen Lauf nicht nachträglich altern lassen. Sie ist
    zuletzt aus dem Bericht gefallen; hier steht sie wieder, gemessen im
    Moment des Aufrufs, mit der PID daneben.
    """
    try:
        out = subprocess.run(
            ["pgrep", "-f", "shadow_runner"],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
        if not out:
            print("runner etime:        (kein shadow_runner-Prozess)")
            return
        for pid in out:
            r = subprocess.run(
                ["ps", "-o", "pid=,lstart=,etime=", "-p", pid],
                capture_output=True, text=True, timeout=5,
            )
            print(f"runner etime:        {r.stdout.strip()}  (gemessen jetzt)")
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        print(f"runner etime:        nicht lesbar ({exc})")


def _delivered_since(
    conn: sqlite3.Connection, *, min_run_id: int, in_scope: int
) -> str:
    """Seit wann ist ``delivered`` konstant — oder ehrlich: nicht ermittelbar.

    ``telemetry`` hat keine Zeitspalte. Der einzige belastbare Anker ist
    ``telemetry_runs.started_at`` des Laufs, der die letzte genehmigte Zeile
    trägt — das ist eine **Obergrenze** (die Lieferung lag irgendwann in
    diesem Lauf), keine Punktzeit. Das wird mitgedruckt, nicht geglättet.

    ``dispatched_signals.telemetry_seq`` wäre die Punktzeit — ist aber NULL
    in allen Zeilen (offener Punkt §6). Deshalb sage ich das, statt eine
    Null in eine Zahl zu kleiden.
    """
    row = conn.execute(
        "SELECT run_id, MAX(seq) FROM telemetry WHERE approved = 1 "
        "GROUP BY run_id ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return "kein Zeitstempel — nicht ermittelbar (nie delivered > 0)"
    run_id, last_seq = int(row[0]), int(row[1])
    started = conn.execute(
        "SELECT started_at FROM telemetry_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if started is None:
        return f"kein Zeitstempel — nicht ermittelbar (run {run_id} ohne started_at)"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(started[0])))
    if in_scope:
        return f"≥ {stamp} (run {run_id} started_at, {in_scope} in scope)"
    # Nicht im Scope: die letzte Lieferung liegt in einem älteren Lauf.
    return (
        f"unverändert seit ≤ {stamp} "
        f"(letzte approved=1 in run {run_id}, seq {last_seq}; "
        "außerhalb des Beobachtungsfensters, Punktzeit nicht ermittelbar)"
    )


def dispatches_in_scope(
    conn: sqlite3.Connection, *, started_at: float
) -> int:
    """Alle Dispatches im Fenster — der Nenner des Urteils (§5.4w).

    ``dispatched_success`` zählt nur, was den Ledger erreicht hat (ohne
    ``bridge_discards``). Der Abnehmer am 20.10. muß wissen, worüber das
    Urteil spricht: 34 Zeilen gegen 360 Dispatches sind 9,4 % — der Ledger
    ist konsistent über knapp einem Zehntel des Verkehrs. Die 56 von 60
    sind nicht "abgelehnt", sie haben den Ledger nie erreicht.
    """
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM dispatched_signals WHERE dispatched_at >= ?",
            (started_at,),
        ).fetchone()[0]
    )


def check_git(expected_prefix: str, errors: list[str]) -> str:
    tip = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True,
    ).strip()
    dirty = subprocess.call(
        ["git", "diff", "--quiet"], cwd=str(REPO),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    short = tip[:8]
    if expected_prefix:
        exp = expected_prefix.strip().lower()
        if not (tip.lower().startswith(exp) or short.lower().startswith(exp[: len(short)])):
            _fail(
                f"git HEAD {short} != expected {expected_prefix} "
                f"(Mess-Commit vor Start festnageln)",
                errors,
            )
        else:
            _ok(f"git HEAD {short} matches {expected_prefix}")
    else:
        _ok(f"git HEAD {short}")
    if dirty != 0:
        _fail("working tree dirty — Messperiode nur auf sauberem Commit", errors)
    else:
        _ok("working tree clean")
    return tip


def check_freeze(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        freeze = load_freeze(path)
    except FreezeError as exc:
        _fail(str(exc), errors)
        return {}
    for asset, entry in freeze["entries"].items():
        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            _fail(f"freeze {asset} missing {missing}", errors)
        else:
            _ok(
                f"freeze {asset}: slug={entry.get('slug')} "
                f"resolved_at={entry.get('resolved_at')}"
            )
    ids = token_ids_from_freeze(freeze)
    payload = PolymarketWsFeed.subscription_payload(ids)
    if set(payload["assets_ids"]) != set(ids):
        _fail("WS assets_ids != freeze token_ids", errors)
    else:
        _ok(f"WS⊇Allowlist: {len(ids)} token_ids")
    return freeze


def check_policy(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        _fail(f"policy missing: {path}", errors)
        return {}
    cfg = json.loads(path.read_text())
    age = float(cfg.get("max_news_age_s", -1))
    if age != 3900:
        _fail(f"max_news_age_s={age} (erwartet 3900)", errors)
    else:
        _ok("max_news_age_s=3900")
    if int(cfg.get("max_book_age_ms", 0)) != 2000:
        _fail(f"max_book_age_ms={cfg.get('max_book_age_ms')} (erwartet 2000)", errors)
    else:
        _ok("max_book_age_ms=2000")
    if str(cfg.get("staleness_policy")) != "reject_stale":
        _fail(f"staleness_policy={cfg.get('staleness_policy')}", errors)
    else:
        _ok("staleness_policy=reject_stale")
    if str(cfg.get("resting_model")) != "re_cross":
        _fail(f"resting_model={cfg.get('resting_model')}", errors)
    else:
        _ok("resting_model=re_cross")
    if str(cfg.get("signal_ref_mode")) != "fallback_limit":
        _fail(f"signal_ref_mode={cfg.get('signal_ref_mode')}", errors)
    else:
        _ok("signal_ref_mode=fallback_limit")
    return cfg


def check_ntp(errors: list[str]) -> None:
    """Best-effort: sntp; Warnung statt Fail wenn Tool fehlt."""
    try:
        out = subprocess.run(
            ["sntp", "-d", "time.apple.com"],
            capture_output=True, text=True, timeout=10,
        )
        text = (out.stdout or "") + (out.stderr or "")
        if out.returncode != 0 and "denied" not in text.lower():
            _warn(f"NTP-Check unklar (manuell prüfen): {text[:120]}")
        else:
            _ok("NTP-Check best-effort ausgeführt (Host-Uhr manuell verifizieren)")
    except (FileNotFoundError, subprocess.TimeoutError, PermissionError) as exc:
        _warn(f"NTP nicht prüfbar ({exc}) — Systemeinstellungen → Datum & Uhrzeit → automatisch")


def latest_run(db_path: Path) -> Optional[tuple[int, str, dict[str, Any]]]:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT run_id, git_commit, config_json FROM telemetry_runs "
            "ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row:
        return None
    cfg = json.loads(row[2]) if row[2] else {}
    return int(row[0]), str(row[1]), cfg


def check_run_config(
    db_path: Path,
    freeze: dict[str, Any],
    errors: list[str],
    *,
    require_run: bool,
) -> None:
    run = latest_run(db_path)
    if run is None:
        if require_run:
            _fail(f"no telemetry_runs in {db_path}", errors)
        else:
            _warn(f"noch kein Run in {db_path} (ok vor KeepAlive)")
        return
    run_id, git_commit, cfg = run
    _ok(f"active/latest run_id={run_id} git_commit={git_commit}")
    for key in REQUIRED_CONFIG_KEYS:
        if key not in cfg:
            _fail(f"config_json missing {key}", errors)
    if float(cfg.get("max_news_age_s", -1)) != 3900:
        _fail(f"run config max_news_age_s={cfg.get('max_news_age_s')}", errors)
    else:
        _ok("run config max_news_age_s=3900")
    if freeze:
        expected = set(token_ids_from_freeze(freeze))
        got = set(cfg.get("ws_token_ids") or [])
        if got != expected:
            _fail(f"run ws_token_ids != freeze: {got ^ expected}", errors)
        else:
            _ok("run ws_token_ids == freeze")


def gate_claim_discard_accounting(
    conn: sqlite3.Connection,
    *,
    started_at: Optional[float],
) -> GateResult:
    """Claims = Erfolg + Verwurf-nach-Claim; Discards = nach + vor Claim.

    ``post_from_claims`` vs ``post_from_discards`` müssen übereinstimmen —
    Divergenz (z. B. Claim im Fenster, Discard außerhalb) ⇒ Schreiblücke.
    Ohne Zeitanker (``started_at`` None) über die ganze DB.
    """
    if started_at is None:
        claim_sql = "SELECT COUNT(*) FROM dispatched_signals"
        claim_post_sql = """
            SELECT COUNT(*) FROM dispatched_signals d
            WHERE EXISTS (
              SELECT 1 FROM bridge_discards b WHERE b.item_id = d.item_id
            )
            """
        discard_sql = "SELECT COUNT(*) FROM bridge_discards"
        discard_post_sql = """
            SELECT COUNT(*) FROM bridge_discards b
            WHERE EXISTS (
              SELECT 1 FROM dispatched_signals d WHERE d.item_id = b.item_id
            )
            """
        params: tuple[Any, ...] = ()
    else:
        claim_sql = (
            "SELECT COUNT(*) FROM dispatched_signals WHERE dispatched_at >= ?"
        )
        claim_post_sql = """
            SELECT COUNT(*) FROM dispatched_signals d
            WHERE d.dispatched_at >= ?
              AND EXISTS (
                SELECT 1 FROM bridge_discards b WHERE b.item_id = d.item_id
              )
            """
        discard_sql = (
            "SELECT COUNT(*) FROM bridge_discards WHERE discarded_at >= ?"
        )
        discard_post_sql = """
            SELECT COUNT(*) FROM bridge_discards b
            WHERE b.discarded_at >= ?
              AND EXISTS (
                SELECT 1 FROM dispatched_signals d WHERE d.item_id = b.item_id
              )
            """
        params = (started_at,)

    claims = int(conn.execute(claim_sql, params).fetchone()[0])
    post_from_claims = int(conn.execute(claim_post_sql, params).fetchone()[0])
    discards = int(conn.execute(discard_sql, params).fetchone()[0])
    post_from_discards = int(conn.execute(discard_post_sql, params).fetchone()[0])
    success = claims - post_from_claims
    pre_claim = discards - post_from_discards
    detail = {
        "claims": claims,
        "success": success,
        "post_claim_discards": post_from_claims,
        "discards": discards,
        "pre_claim_discards": pre_claim,
        "post_claim_from_discards": post_from_discards,
    }
    # Algebra claims=success+post / discards=post+pre holds by construction;
    # RED only when the two post-views diverge (orphan claim↔discard).
    if post_from_claims != post_from_discards:
        return GateResult(
            name="CLAIM_DISCARD_ACCOUNTING",
            status="RED",
            detail=detail,
        )
    return GateResult(
        name="CLAIM_DISCARD_ACCOUNTING",
        status="GREEN",
        detail=detail,
    )


def invalid_price_concentration(
    conn: sqlite3.Connection,
    *,
    min_run_id: int,
    started_at: float,
) -> dict[str, int]:
    """``INVALID_PRICE`` je Token — Kanal vs. Universum trennen.

    Die DB führt kein Symbol. ``dispatched_signals`` und ``telemetry`` sind
    über ``decision_seq`` (Reihenfolge der Erfolgs-Dispatches) verknüpft;
    der Token kommt aus der freiwilligen ``<data_root>/<user_id>/shadow/
    news_index.jsonl`` (``item_id`` → ``target_assets``). Ohne Index bleibt
    der Report leer und benennt das.
    """
    index_path = Path.home() / "Library" / "Application Support" / "agentx"
    items = _load_item_index(index_path)
    token_map: dict[str, str] = {}
    for entry in items.values():
        assets = entry.get("target_assets") or []
        if len(assets) == 1:
            token_map[entry.get("item_id", "")] = assets[0]

    rows = conn.execute(
        """
        SELECT s.item_id, t.reject_reason FROM (
          SELECT d.item_id, row_number() OVER (
                   ORDER BY d.dispatched_at, d.item_id) AS rn
          FROM dispatched_signals d
          WHERE d.dispatched_at >= ?
            AND NOT EXISTS (
              SELECT 1 FROM bridge_discards b WHERE b.item_id = d.item_id
            )
        ) s
        LEFT JOIN telemetry t ON t.run_id >= ? AND t.decision_seq = s.rn
        WHERE t.reject_reason = 'INVALID_PRICE'
        """,
        (started_at, min_run_id),
    ).fetchall()
    out: dict[str, int] = {}
    for item_id, _reason in rows:
        token = token_map.get(item_id) or "unknown"
        out[token] = out.get(token, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _load_item_index(data_root: Path) -> dict[str, dict[str, Any]]:
    """Liest ``news_index.jsonl`` (item_id → News-Zeile), falls vorhanden."""
    out: dict[str, dict[str, Any]] = {}
    path = data_root / "shadow" / "shadow" / "news_index.jsonl"
    if not path.exists():
        return out
    try:
        with path.open() as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("item_id"):
                    out[str(row["item_id"])] = row
    except OSError:
        return out
    return out


def terminal_classes(recon_detail: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Zwei orthogonale Achsen — jede schließt auf ihre eigene Bezugsmenge.

    * ``outcome`` klassifiziert nach **Ausgang**; Summe = ``dispatched_success``.
    * ``origin`` klassifiziert nach **Herkunft**; Summe = ``dispatched_success``.

    ``unattributed`` gehört **nur** in ``origin``. In ``outcome`` gelegt wäre
    es doppelt gezählt (Run 8: 1 + 26 + 7 + 4 = 38 gegen 34). Die frühere
    Ein-Zeilen-View mischte zwei Achsen in einer Summe.

    Die Herkunfts-Zeile ist ``telemetry_rows`` **nicht** — die Zahl ist auf
    Run-Ebene identisch mit der Ausgangssumme und damit als Herkunftszähler
    wertlos. Gezählt wird ``dispatched_success - unattributed``.
    """
    reasons = recon_detail.get("reasons") or {}
    success = int(recon_detail.get("dispatched_success", 0))
    unattributed = int(recon_detail.get("unattributed", 0))
    return {
        "outcome": {
            "filled": int(reasons.get("NONE", 0)),
            "rejected": sum(
                int(c) for r, c in reasons.items()
                if r not in ("NONE", "STALE_SNAPSHOT")
            ),
            "stale": int(reasons.get("STALE_SNAPSHOT", 0)),
        },
        "origin": {
            "telemetry": success - unattributed,
            "unattributed": unattributed,
        },
    }


def _two_verdicts(
    conn: sqlite3.Connection,
    recon: GateResult,
    *,
    min_run_id: int,
) -> dict[str, str]:
    """Zwei Verdikte: ``current`` (letzter Lauf) vs. ``historical``.

    Ein dauerhaft roter abgeschlossener Lauf macht das Gate zur Tapete: rot,
    das erwartet und dokumentiert ist, wird nicht mehr gelesen. Deshalb wird
    der jüngste Lauf vom Bestand getrennt geführt. ``historical`` ist
    **dokumentiert** — es ist eine Aussage über eine abgeschlossene Periode,
    kein Befund über den laufenden Betrieb.

    **Blockierend ist keine Eigenschaft des Verdikts, sondern des Aufrufers.**
    Dieser Prüfer ist ein Werkzeug: er setzt sein Exit-Code, wenn jemand ihn
    startet. Ein verdrahteter Aufrufer (launchd-Job, Hook) ist nicht Teil
    dieses Moduls — die Ausgabe sagt „kein Aufrufer (Stand <blob>)", nicht
    „kein Aufrufer, für immer". Ein Werkzeug kann seine eigene Verdrahtung
    nicht kennen, ohne sie nachzusehen; die Datierung macht die Aussage
    prüfbar statt behauptet.
    """
    row = conn.execute("SELECT MAX(run_id) FROM telemetry_runs").fetchone()
    latest = int(row[0]) if row and row[0] is not None else min_run_id
    if latest == min_run_id:
        return {
            "current": recon.status,
            "historical": "n/a",
            "latest_run_id": latest,
        }
    historical = (
        f"RED (run {min_run_id}, unattributed="
        f"{recon.detail.get('unattributed')})"
        if recon.status == "RED"
        else f"LEDGER_CONSISTENT (run {min_run_id})"
    )
    # ``current`` wurde hier fest auf "GREEN" gesetzt — eine Behauptung, kein
    # Meßwert: der Docstring sagt "current (letzter Lauf)", der Code hat den
    # letzten Lauf nie angesehen. Jetzt wird er gemessen.
    latest_recon = gate_telemetry_reconciliation(conn, min_run_id=latest)
    return {
        "current": latest_recon.status,
        "historical": historical,
        "latest_run_id": latest,
    }


def _gate_criterion(min_run_id: int) -> str:
    """Die Regel, die aus Zahlen ein Verdikt macht — als ausdruckbarer Satz.

    Spiegelt die vier RED-Bedingungen von ``gate_telemetry_reconciliation``
    in derselben Reihenfolge. Wird eine dort geändert und hier nicht, ist
    die Ausgabe eine Lüge in einer Zeile — deshalb steht in beiden Docstrings
    der Hinweis auf den jeweils anderen. Bewusst keine Zahl aus der DB: das
    Kriterium ist konstant, die Messung steht daneben.
    """
    return (
        "PROVISIONAL_LEDGER_CONSISTENT solange der Lauf offen ist ("
        "telemetry_runs hat kein Ende: ein Bruchstück trägt kein Urteil); "
        "LEDGER_CONSISTENT nur wenn "
        "(0) dispatched_success > 0 oder telemetry_rows > 0 "
        "(kein leerer Dienst; 0 == 0 wäre sonst vierfach erfüllt) "
        "(1) telemetry_rows == decision_seq-keyed — KOROLLAR aus (3)+(3b), "
        "kein eigener Befund: (3) ist success <= rows, (3b) ist rows <= success, "
        "zusammen rows == success; (1) prüft die Schreibseite (jede Zeile hat "
        "ihren Schlüssel) und bleibt als Diagnose, nicht als Bedingung " 
        "(2) keyed == distinct(run_id, decision_seq) und je run eindeutig "
        "(3) unattributed == 0 (Erfolg ohne Zeile) "
        "(3b) orphan_rows == 0 (Zeile ohne Erfolg — die Überbehauptung) "
        "(4) dispatched_success == Σ reject_reasons; "
        f"scope = run_id >= {min_run_id}. "
        "(5) WARNUNG, kein Blocker: delivered == 0 heißt Ledger konsistent "
        "über einem Lauf ohne Auslieferung — das Etikett sagt dazu nichts. "
        "(6) NENNER: das Urteil nennt Zeilen, Auslieferungen und den Anteil "
        "am Verkehr; es sagt nichts über Erreichbarkeit, Verarbeitung "
        "jenseits des Ledgers oder Leben der Signalquelle. "
        "(7) COVERAGE = telemetry_rows / dispatched_signals im Fenster "
        "(heute 4/61 = 6.6 %) — spricht über den Ausschnitt, nicht über "
        "den Dienst. "
        "(8) DELIVERY = eigenes Etikett, NICHT dieses: DELIVERING nur "
        "wenn ein Fill im Fenster UND jünger als FRESH_FILL_S (2 Takte); "
        "DELIVERY_STALLED_SINCE wenn dispatched_success > 0, aber kein "
        "frischer oder kein genehmigter Fill; NO_TRAFFIC ohne Erfolge. "
        "Ein Teilfill zählt als Teilfill (fill_ratio), nicht als Fill. "
        "Zwei Etiketten, weil ein Etikett nicht gleichzeitig "
        "'konsistent' und 'steht still' sagen kann."
    )


def _pairs_unique_per_run(conn: sqlite3.Connection, *, min_run_id: int) -> bool:
    """Je ``run_id``: ``count(*) == count(DISTINCT decision_seq)``."""
    rows = conn.execute(
        "SELECT run_id, COUNT(*), COUNT(DISTINCT decision_seq) FROM telemetry "
        "WHERE run_id >= ? AND decision_seq IS NOT NULL GROUP BY run_id",
        (min_run_id,),
    ).fetchall()
    return all(int(total) == int(distinct) for _rid, total, distinct in rows)


def partition_ok(classes: dict[str, dict[str, int]], recon_detail: dict[str, Any]) -> bool:
    """Jede Achse muss auf ``dispatched_success`` schließen (kein Doppelzählen)."""
    success = int(recon_detail.get("dispatched_success", 0))
    return (
        sum(classes["outcome"].values()) == success
        and sum(classes["origin"].values()) == success
    )


def count_distinct_item(
    conn: sqlite3.Connection,
    table: str,
    ts_col: str,
    started_at: Optional[float],
) -> int:
    """``count(DISTINCT item_id)`` im selben Zeitfenster — 1:1-Join-Beweis."""
    if started_at is None:
        return int(
            conn.execute(
                f"SELECT COUNT(DISTINCT item_id) FROM {table}"
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            f"SELECT COUNT(DISTINCT item_id) FROM {table} WHERE {ts_col} >= ?",
            (started_at,),
        ).fetchone()[0]
    )


def gate_snapshot(
    db_path: Path,
    errors: list[str],
    *,
    min_run_id: int = DEFAULT_MIN_RUN_ID,
) -> Optional[dict[str, Any]]:
    """Gate-Schnappschuss; Zähler ab ``min_run_id.started_at`` (wie Reconciliation).

    Fehlt der Run-Anker, zählen Discards/Dispatches/Dups über die ganze DB
    (``time_filter=unscoped`` in Rückgabe und Ausgabe).
    """
    if not db_path.exists():
        _warn("keine DB für Gate-Schnappschuss")
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        # Same time anchor as TELEMETRY_RECONCILIATION (min_run_id.started_at).
        started_row = conn.execute(
            "SELECT started_at FROM telemetry_runs WHERE run_id = ?",
            (min_run_id,),
        ).fetchone()
        started_at = float(started_row[0]) if started_row is not None else None
        if started_at is None:
            discards = conn.execute(
                "SELECT reason, COUNT(*) FROM bridge_discards GROUP BY reason"
            ).fetchall()
            disp = int(
                conn.execute("SELECT COUNT(*) FROM dispatched_signals").fetchone()[0]
            )
            dup = conn.execute(
                "SELECT item_id, COUNT(*) c FROM dispatched_signals "
                "GROUP BY item_id HAVING c > 1"
            ).fetchall()
            time_filter = "unscoped"
        else:
            discards = conn.execute(
                "SELECT reason, COUNT(*) FROM bridge_discards "
                "WHERE discarded_at >= ? GROUP BY reason",
                (started_at,),
            ).fetchall()
            disp = int(
                conn.execute(
                    "SELECT COUNT(*) FROM dispatched_signals "
                    "WHERE dispatched_at >= ?",
                    (started_at,),
                ).fetchone()[0]
            )
            dup = conn.execute(
                "SELECT item_id, COUNT(*) c FROM dispatched_signals "
                "WHERE dispatched_at >= ? "
                "GROUP BY item_id HAVING c > 1",
                (started_at,),
            ).fetchall()
            time_filter = f"run_id={min_run_id}.started_at"
        stale = conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE run_id >= ? "
            "AND reject_reason = 'STALE_SNAPSHOT'",
            (min_run_id,),
        ).fetchone()[0]
        fills = conn.execute(
            "SELECT COUNT(*) FROM telemetry_fill_metrics f "
            "JOIN telemetry t ON t.seq = f.telemetry_seq "
            "WHERE t.run_id >= ?",
            (min_run_id,),
        ).fetchone()[0]
        recon = gate_telemetry_reconciliation(conn, min_run_id=min_run_id)
        accounting = gate_claim_discard_accounting(conn, started_at=started_at)
        invalid_prices = (
            invalid_price_concentration(
                conn, min_run_id=min_run_id, started_at=started_at)
            if started_at is not None
            else {}
        )
        join_ok = (
            disp == count_distinct_item(
                conn, "dispatched_signals", "dispatched_at", started_at)
            and sum(int(c) for _, c in discards)
            == count_distinct_item(
                conn, "bridge_discards", "discarded_at", started_at)
        )
        # Join-Kardinalität (der Schlüssel, über den tatsächlich gejoint wird).
        join_key_ok = bool(
            recon.detail.get("decision_seq_keyed") is not None
            and recon.detail["decision_seq_keyed"]
            == recon.detail["decision_seq_distinct_pair"]
            and recon.detail.get("decision_seq_unique_per_run")
        )
        verdicts = _two_verdicts(conn, recon, min_run_id=min_run_id)
    except sqlite3.Error as exc:
        _warn(f"gate snapshot skipped: {exc}")
        return None
    finally:
        conn.close()

    discard_reasons = {str(r): int(c) for r, c in discards}
    snapshot = {
        "min_run_id": min_run_id,
        "started_at": started_at,
        "time_filter": time_filter,
        "dispatched_signals": disp,
        "discard_reasons": discard_reasons,
        "stale_snapshot": int(stale),
        "telemetry_fill_metrics": int(fills),
        "duplicate_item_ids": len(dup),
        "item_id_is_unique": join_ok,
        "join_is_one_to_one": join_key_ok,
        "invalid_price_by_asset": invalid_prices,
        "reconciliation": recon,
        "claim_discard_accounting": accounting,
        "verdicts": verdicts,
    }
    print("--- Gate-Schnappschuss ---")
    if time_filter == "unscoped":
        scope = (
            f"unscoped — no telemetry_runs.run_id={min_run_id}; "
            "counts over full DB"
        )
    else:
        scope = f">={time_filter}"
    print(f"  time_filter: {scope}")
    print(f"  claims_total: {disp}")
    print(f"  discard_reasons: {discard_reasons}")
    print(f"  item_id_is_unique: {join_ok} (Eindeutigkeit der Spalte)")
    print(f"  join_is_one_to_one: {join_key_ok} (decision_seq / run_id+decision_seq)")
    print(f"  STALE_SNAPSHOT telemetry (run_id>={min_run_id}): {stale}")
    print(f"  telemetry_fill_metrics rows (run_id>={min_run_id}): {fills}")
    print(f"  duplicate item_ids: {len(dup)}")
    print(f"  {recon.name}: {recon.status} detail={recon.detail}")
    if "delivered" in recon.detail:
        d = recon.detail
        hours = d.get("observed_hours") or 0.0
        rate = d.get("rows_per_hour")
        rate_s = f"eine alle {1.0 / rate:.1f} h" if rate else "Rate unbekannt"
        print(
            f"  verdict:            {recon.status} "
            f"({d.get('telemetry_rows')} Zeilen, "
            f"{d.get('delivered')} Auslieferungen)"
        )
        # Die Adresse des Urteils (§5.4bk): ein RED ohne genannte Bedingung
        # ist ein Zustand, keine Aussage.
        # Wer das Urteil durchsetzt, entscheidet, ob `blocking` eine
        # Tatsache oder eine Absicht beschreibt (§5.4ca). Muß VOR der
        # blocking-Zeile stehen, nicht danach.
        wired = bool(_blocking_callers())
        if recon.status != "GREEN" and recon.reason:
            print(f"  reason:             {recon.reason}")
            # WER blockt (§5.4br): dieses Gate bewertet Buchführung, nicht
            # Betrieb. Ohne diese Zeile liest der 20.10. `RED`, schaut auf
            # die vier Zeilen und repariert die falsche Seite.
            # `(unenforced)` steht im Wert (§5.4ca): ohne Aufrufer
            # beschreibt `ledger` nicht, was blockt, sondern was blockieren
            # würde — und wer das nicht liest, nimmt an, es sei vollzogen.
            print(f"  blocking:           {recon.blocking}"
                  f"{'' if wired else ' (unenforced)'} — "
                  "dieses Gate prüft den Ledger; der Dienst steht oder "
                  "steht nicht, und das steht im delivery-Etikett")
        print(f"  open_for:           {d.get('open_for_hours')} h"
              f" ({d.get('open_for_hours', 0) / 24:.1f} d) — der Lauf, "
              "nicht die Stille")
        # Die Abnahme (§5.4at): sechzehn Runden Urteile, und keines hat je
        # etwas angehalten. Ob dieses Etikett wirkt, entscheidet nicht der
        # Satz im Terminal, sondern ein Aufrufer im Dienst. Solange keiner
        # verdrahtet ist, ist das Urteil ein Text — und das steht hier.
        readers = _verdict_readers()
        print(
            "  wired:              "
            + ("ja — " + ", ".join(sorted(_blocking_callers()))
               if wired else
               "nein — kein Import in Produktionscode")
        )
        # Drei Zustände statt zwei (§5.4bb): importiert, gelesen, nichts.
        # Der erste Aufrufer am 20.10. wird kein Import sein, sondern ein
        # Cronjob, der die AUSGABE liest — und den kann _blocking_callers()
        # per Konstruktion nicht sehen.
        print(
            "  read_by:            "
            + (", ".join(sorted(readers)) if readers else
               "nichts — kein Skript liest die Urteilszeile")
        )
        d = recon.detail
        _ft = d.get("fills_total")
        print(
            f"  delivery:           {d.get('delivery')} "
            f"({d.get('dispatched_success')} Erfolge, "
            f"{d.get('delivered')} genehmigt, "
            + (f"{_ft} Fills ({d.get('fills_full')} voll, "
               f"{d.get('fills_partial')} teilweise, "
               f"fillsumme {d.get('fill_ratio')})"
               if _ft is not None else "Fills: nicht gemessen")
            + (f", letzter {d.get('last_fill')}" if d.get("last_fill") else "")
            + ")"
        )
        if d.get("stalled_for_h") is not None:
            _sf = d["stalled_for_h"]
            print(f"  stalled_for:        {_sf} h ({round(_sf / 24.0, 1)} d)"
                  " — gegen jetzt, nicht gegen den Laufanfang")
        # Der Fremdschlüssel ( §5.4bs): die Bezugsgröße ist der Order-Schritt,
        # nicht die Entscheidung. 8/8 heißt: wo eine Order entstand, steht
        # ihre Id. `telemetry_seq` (0/361) ist keine Lücke, sondern eine
        # Altlast — die Paarung läuft über `order_id`, und der Fill liegt
        # dort. Eine Spalte, die nie gefüllt wird und nie gefüllt werden muß,
        # ist keine Aufgabe, sondern ein Grabstein.
        print(
            f"  fk order_id:        {d.get('fk_set')}/{d.get('fk_expected')} "
            f"Order-Schritte gesetzt "
            f"({d.get('fk_rows')} Entscheidungen, 26 ohne Order = korrekt "
            f"leer), {d.get('fk_paired')} Fill(s) darüber gepaart — "
            "telemetry_seq ist deprecated (0/361, nie benötigt)"
        )
        cov = d.get("coverage_pct")
        print(
            f"  coverage:           "
            f"{d.get('telemetry_rows')}/{d.get('dispatched_in_scope')} "
            f"Dispatches = {cov:.1f} % — der Ledger spricht über diesen "
            "Ausschnitt, nicht über den Verkehr"
            if cov is not None
            else "  coverage:           nicht ermittelbar (kein Verkehr)"
        )
        print(
            f"  observed:           {hours:.1f} h ({hours / 24:.2f} d)"
            f" — {rate_s}; erwartet: unbekannt"
        )
        print(
            f"  traffic:            {d.get('dispatched_before_scope')} vor dem "
            f"Fenster + {d.get('dispatched_in_scope')} im Fenster "
            "= der Rest liegt außerhalb jedes Urteils"
        )
        print(
            f"  delivered:          {d['delivered']} "
            f"— {d.get('delivered_since', 'nicht ermittelbar')}"
        )
    ad = accounting.detail
    print(
        f"  {accounting.name}: {accounting.status} "
        f"claims={ad.get('claims')} = success={ad.get('success')} "
        f"+ post_claim={ad.get('post_claim_discards')}; "
        f"discards={ad.get('discards')} = post={ad.get('post_claim_from_discards')} "
        f"+ pre={ad.get('pre_claim_discards')}"
    )
    # Terminalklassen (View-Ersatz, kein Rename der Spalten) — zwei Achsen:
    classes = terminal_classes(recon.detail)
    print(f"  outcome (Σ=claims_mit_telemetrie): {classes['outcome']}")
    print(f"  origin  (Σ=dispatched_success):    {classes['origin']}")
    verdicts = snapshot["verdicts"]
    # Der Richter datiert sich selbst: ein Verdikt ohne Prüfer-Hash nennt den
    # Run, aber nicht die Fassung, die urteilte.
    _gate_blob = _gate_blob_hash()
    print(f"  gate:               {_gate_blob['blob']}  ({_gate_blob['source']})")
    print(
        f"  gate commit:        {_gate_blob['commit']}:"
        f"{_gate_blob['committed_blob']}"
    )
    # Das Kriterium kommt aus dem Werkzeug, nicht aus dem Dokument: was hier
    # steht, ist die Regel, die `current` erzeugt hat. Ändert jemand morgen
    # eine Schwelle, ist jedes archivierte Verdikt nachträglich ein anderes —
    # der Blob datiert den Code, diese Zeile datiert die Regel.
    print(f"  criterion:          {_gate_criterion(min_run_id)}")
    print(
        f"  verdict current:    {verdicts['current']}  (letzter Lauf)"
    )
    print(
        f"  verdict historical: {verdicts['historical']}  "
        f"(abgeschlossen, dokumentiert)"
    )
    # Der Blob wird zur Laufzeit interpoliert, nie als Literal geschrieben:
    # eine Datei, die ihren eigenen Hash enthält, hätte einen Fixpunkt, der
    # nicht existiert — jede Korrektur änderte den Wert, den sie korrigiert.
    print(
        f"  anchored at:        {_gate_blob['blob'][:12]} — der Stand, an dem "
        "das Urteil gebunden ist; wer diesen Befehl startet, blockiert, "
        "das Urteil selbst bricht nichts ab"
    )
    if recon.detail.get("unattributed"):
        print(
            f"  WARN unattributed dispatches (no telemetry row, "
            f"decision_seq join): {recon.detail['unattributed']}"
        )
    if recon.detail.get("dispatched_success"):
        print(f"  invalid_price_by_asset: {invalid_prices}")
    historical = snapshot["verdicts"]["latest_run_id"] != recon.detail.get(
        "min_run_id", snapshot["verdicts"]["latest_run_id"]
    )

    def _report(msg: str, hard: bool = True) -> None:
        if historical and hard:
            _warn(f"historical (dokumentiert, kein Abbruch): {msg}")
        else:
            _fail(msg, errors)

    if dup:
        print(f"  FAIL duplicates: {dup[:5]}")
        _report(f"duplicate item_ids: {dup[:5]}")
    if not join_ok:
        _report("item_id_is_unique: count(*) != count(DISTINCT item_id)")
    if not join_key_ok:
        _report(
            "join_is_one_to_one: (run_id, decision_seq) nicht eindeutig "
            f"(keyed={recon.detail.get('decision_seq_keyed')} "
            f"pairs={recon.detail.get('decision_seq_distinct_pair')} "
            f"per_run={recon.detail.get('decision_seq_unique_per_run')})",
        )
    if recon.status == "RED":
        outcome_sum = sum(classes["outcome"].values())
        msg = (
            f"{recon.name}: dispatched_success={recon.detail.get('dispatched_success')} "
            f"telemetry_rows={recon.detail.get('telemetry_rows')} "
            f"classifiable={recon.detail.get('classifiable')} "
            f"unattributed={recon.detail.get('unattributed')} "
            f"outcome_sum={outcome_sum}"
        )
        # Zuordnung: blockierend ist ein Befund, wenn er den JÜNGSTEN Lauf
        # betrifft. Vorher stand hier `verdicts.current == "GREEN"` — und
        # current war fest auf "GREEN" gesetzt, also wurde jeder rote Befund
        # zur Warnung degradiert: eine Prüfung, die ihren eigenen Ausgang
        # las, statt den Lauf zu messen.
        #
        # `recon` misst nur min_run_id. Der jüngste Lauf wird separat
        # gemessen (verdicts) — sein Befund muß ebenfalls blockieren,
        # sonst schluckt ein Aufruf mit alter min_run_id den aktuellen Ausfall.
        latest_run = snapshot["verdicts"].get("latest_run_id")
        recon_is_historical = latest_run is not None and int(latest_run) != int(
            recon.detail.get("min_run_id", latest_run)
        )
        if recon_is_historical:
            _warn(f"historical (dokumentiert, kein Abbruch): {msg}")
        else:
            _fail(msg, errors)
        # Konsistent ist, was auf LEDGER_CONSISTENT endet — PROVISIONAL
        # eingeschlossen, denn beide behaupten dasselbe über den Ledger und
        # nichts über den Lauf. Die Klassifikation arbeitet auf dem
        # Etikett-Kopf, nicht auf dem ganzen String: seit §5.4an trägt das
        # Etikett seine Dauer ("(open 13.0d)"), und ein Set-Vergleich hätte
        # daran genau den Fehlalarm erzeugt, den er verhindern soll.
        #
        # BLOCKIEREND ist PROVISIONAL ausdrücklich NICHT (§5.4an): ein
        # offener Lauf ist der Normalzustand dieses Dienstes, weil das
        # Schema kein Ende kennt. Was immer gilt, darf nicht blocken —
        # sonst hält die Vorsicht den Dienst an, den sie schützt.
        label = str(snapshot["verdicts"]["current"]).split("(")[0].strip()
        consistent_labels = {
            "LEDGER_CONSISTENT",
            "PROVISIONAL_LEDGER_CONSISTENT",
        }
        if (
            latest_run is not None
            and recon_is_historical
            and label not in consistent_labels
        ):
            _fail(
                f"latest run {latest_run}: "
                f"{snapshot['verdicts']['current']} (blockierend)",
                errors,
            )
    if not partition_ok(classes, recon.detail):
        _report(
            f"terminal partition: outcome={classes['outcome']} "
            f"origin={classes['origin']} "
            f"success={recon.detail.get('dispatched_success')}",
        )
    if accounting.status == "RED":
        _fail(
            f"{accounting.name}: claims={ad.get('claims')} "
            f"success={ad.get('success')} post={ad.get('post_claim_discards')} "
            f"discards={ad.get('discards')} pre={ad.get('pre_claim_discards')} "
            f"post_from_discards={ad.get('post_claim_from_discards')}",
            errors,
        )
    return snapshot


def check_paths(news_jsonl: Path, data_root: Path, errors: list[str], *, after_start: bool) -> None:
    if not news_jsonl.parent.exists():
        _fail(f"news jsonl parent missing: {news_jsonl.parent}", errors)
    else:
        _ok(f"news jsonl path parent ok: {news_jsonl}")
    if news_jsonl.exists():
        age_h = (time.time() - news_jsonl.stat().st_mtime) / 3600.0
        if age_h > 2.0:
            _warn(
                f"news_scores.jsonl mtime age={age_h:.1f}h — "
                f"News-Agent-Pfad prüfen (THX_OS_ULTRA vs 'THX_OS_ULTRA - Data')"
            )
        else:
            _ok(f"news_scores.jsonl mtime age={age_h:.2f}h")
    else:
        _warn(f"news_scores.jsonl fehlt noch: {news_jsonl}")
    offset = data_root / "shadow" / "shadow" / "news_tail.offset"
    if after_start:
        if offset.exists():
            _ok(f"tail offset exists: {offset} = {offset.read_text().strip()}")
        else:
            _fail(f"tail offset missing after start: {offset}", errors)
    data_root.mkdir(parents=True, exist_ok=True)
    _ok(f"data_root ready: {data_root}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument(
        "--data-root", type=Path,
        default=DEFAULT_DATA_ROOT,
    )
    parser.add_argument("--user-id", default="shadow")
    parser.add_argument(
        "--news-jsonl", type=Path,
        default=DEFAULT_NEWS_JSONL,
    )
    parser.add_argument(
        "--expect-commit", default="bfcc856d",
        help="Mess-Commit-Prefix (leer = nur dirty-Check)",
    )
    parser.add_argument(
        "--after-start", action="store_true",
        help="Strenger: Run + Tail-Offset müssen existieren",
    )
    parser.add_argument(
        "--min-run-id", type=int, default=DEFAULT_MIN_RUN_ID,
        help="Auswertungs-/Gate-Untergrenze (Messperiode: 7)",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    print(f"Pre-Flight @ {REPO}")
    _print_process_age()
    if args.expect_commit:
        check_git(args.expect_commit, errors)
    else:
        check_git("", errors)

    freeze = check_freeze(args.freeze, errors)
    check_policy(args.policy, errors)
    check_ntp(errors)
    check_paths(args.news_jsonl, args.data_root, errors, after_start=args.after_start)

    db_path = args.data_root / args.user_id / "shadow" / "shadow.db"
    check_run_config(
        db_path, freeze, errors, require_run=args.after_start,
    )
    gate_snapshot(db_path, errors, min_run_id=args.min_run_id)
    if errors:
        print(f"\nRESULT: RED ({len(errors)} errors)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nRESULT: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
