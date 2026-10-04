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
    detail = {
        "min_run_id": min_run_id,
        "started_at": started_at,
        "dispatched_success": dispatched,
        "telemetry_rows": telemetry_rows,
    }
    if dispatched > 0 and telemetry_rows < dispatched:
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


def gate_snapshot(
    db_path: Path,
    errors: list[str],
    *,
    min_run_id: int = DEFAULT_MIN_RUN_ID,
) -> None:
    if not db_path.exists():
        _warn("keine DB für Gate-Schnappschuss")
        return
    conn = sqlite3.connect(str(db_path))
    try:
        discards = conn.execute(
            "SELECT reason, COUNT(*) FROM bridge_discards GROUP BY reason"
        ).fetchall()
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
        disp = conn.execute(
            "SELECT COUNT(*) FROM dispatched_signals"
        ).fetchone()[0]
        dup = conn.execute(
            "SELECT item_id, COUNT(*) c FROM dispatched_signals "
            "GROUP BY item_id HAVING c > 1"
        ).fetchall()
        recon = gate_telemetry_reconciliation(conn, min_run_id=min_run_id)
    except sqlite3.Error as exc:
        _warn(f"gate snapshot skipped: {exc}")
        return
    finally:
        conn.close()
    print("--- Gate-Schnappschuss ---")
    print(f"  dispatched_signals: {disp}")
    print(f"  discard_reasons: {dict(discards)}")
    print(f"  STALE_SNAPSHOT telemetry (run_id>={min_run_id}): {stale}")
    print(f"  telemetry_fill_metrics rows (run_id>={min_run_id}): {fills}")
    print(f"  duplicate item_ids: {len(dup)}")
    print(f"  {recon.name}: {recon.status} detail={recon.detail}")
    if dup:
        print(f"  FAIL duplicates: {dup[:5]}")
        _fail(f"duplicate item_ids: {dup[:5]}", errors)
    if recon.status == "RED":
        _fail(
            f"{recon.name}: dispatched_success={recon.detail.get('dispatched_success')} "
            f"> telemetry_rows={recon.detail.get('telemetry_rows')}",
            errors,
        )


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
