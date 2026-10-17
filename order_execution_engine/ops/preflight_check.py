#!/usr/bin/env python3
"""Pre-Flight-Stichprobe vor KeepAlive und ~1 h nach Start.

Exit 0 = grün, Exit 1 = rot (Fail-closed für Messperioden-Start).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
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
    """
    row = conn.execute(
        "SELECT started_at FROM telemetry_runs WHERE run_id = ?",
        (min_run_id,),
    ).fetchone()
    if row is None:
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="GREEN",
            detail={"note": f"no telemetry_runs.run_id={min_run_id}"},
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
    detail = {
        "min_run_id": min_run_id,
        "started_at": started_at,
        "dispatched_success": dispatched,
        "telemetry_rows": telemetry_rows,
        "decision_seq_keyed": keyed,
        "decision_seq_distinct_pair": distinct_pair,
        "decision_seq_unique_per_run": pairs_ok,
        "reasons": reasons,
        "classifiable": sum(reasons.values()),
        "unattributed": unattributed,
    }
    # Kardinalität: jede Telemetriezeile braucht ihren Schlüssel, und der
    # Schlüssel darf sich weder je Lauf noch über Läufe wiederholen.
    if telemetry_rows != keyed:
        return GateResult(
            name="TELEMETRY_RECONCILIATION", status="RED", detail=detail,
        )
    if keyed != distinct_pair or not pairs_ok:
        return GateResult(
            name="TELEMETRY_RECONCILIATION", status="RED", detail=detail,
        )
    # Vollständigkeit: ein Dispatch ohne Telemetriezeile ist nicht
    # "unbedenklich" — er ist eine unklassifizierte Terminalentscheidung.
    # < wäre grün über einer Lücke (Run 8: 30 Zeilen vs. 34 Dispatches).
    if unattributed > 0:
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            detail=detail,
        )
    if dispatched != sum(reasons.values()):
        return GateResult(
            name="TELEMETRY_RECONCILIATION",
            status="RED",
            detail=detail,
        )
    return GateResult(
        name="TELEMETRY_RECONCILIATION",
        status="GREEN",
        detail=detail,
    )


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
    if recon.detail.get("unattributed"):
        print(
            f"  WARN unattributed dispatches (no telemetry row, "
            f"decision_seq join): {recon.detail['unattributed']}"
        )
    if recon.detail.get("dispatched_success"):
        print(f"  invalid_price_by_asset: {invalid_prices}")
    if dup:
        print(f"  FAIL duplicates: {dup[:5]}")
        _fail(f"duplicate item_ids: {dup[:5]}", errors)
    if not join_ok:
        _fail("item_id_is_unique: count(*) != count(DISTINCT item_id)", errors)
    if not join_key_ok:
        _fail(
            "join_is_one_to_one: (run_id, decision_seq) nicht eindeutig "
            f"(keyed={recon.detail.get('decision_seq_keyed')} "
            f"pairs={recon.detail.get('decision_seq_distinct_pair')} "
            f"per_run={recon.detail.get('decision_seq_unique_per_run')})",
            errors,
        )
    if recon.status == "RED":
        _fail(
            f"{recon.name}: dispatched_success={recon.detail.get('dispatched_success')} "
            f"telemetry_rows={recon.detail.get('telemetry_rows')} "
            f"classifiable={recon.detail.get('classifiable')} "
            f"unattributed={recon.detail.get('unattributed')}",
            errors,
        )
    if not partition_ok(classes, recon.detail):
        _fail(
            f"terminal partition: outcome={classes['outcome']} "
            f"origin={classes['origin']} "
            f"success={recon.detail.get('dispatched_success')}",
            errors,
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
