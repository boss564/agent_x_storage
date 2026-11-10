"""S2-W3: Report N-4 — telemetry_class ≠ reject (A-C1…C3)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from order_execution_engine.telemetry_classify import classify_telemetry_row


def test_w3_a_c1_d2_is_unactionable_not_reject() -> None:
    kind = classify_telemetry_row(
        approved=0,
        telemetry_class="UNACTIONABLE_SELL_NO_INVENTORY",
        reject_reason="NONE",
    )
    assert kind == "unactionable"
    assert kind != "reject"
    print("OK test_w3_a_c1_d2_is_unactionable_not_reject")


def test_w3_a_c2_missing_class_is_reject() -> None:
    assert classify_telemetry_row(approved=0, telemetry_class=None) == "reject"
    assert classify_telemetry_row(approved=1, telemetry_class=None) == "approval"
    print("OK test_w3_a_c2_missing_class_is_reject")


def test_w3_a_c3_vacuity_alt_schema_without_column() -> None:
    """Alt-DB ohne telemetry_class: classify + SELECT darf nicht crashen."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "legacy.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE telemetry ("
            "run_id INT, approved INT, reject_reason TEXT, reject_detail TEXT)"
        )
        conn.execute(
            "INSERT INTO telemetry VALUES (13, 0, 'NO_SNAPSHOT', NULL)"
        )
        conn.commit()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(telemetry)")}
        assert "telemetry_class" not in cols
        row = conn.execute(
            "SELECT approved, reject_reason, reject_detail FROM telemetry"
        ).fetchone()
        kind = classify_telemetry_row(
            approved=row[0], telemetry_class=None, reject_reason=row[1],
        )
        assert kind == "reject"
        conn.close()
        print("OK test_w3_a_c3_vacuity_alt_schema_without_column")


def test_w3_absence_splits_rejects() -> None:
    import sys

    newsagent_scripts = (
        Path(__file__).resolve().parents[2] / "newsagent" / "scripts"
    )
    sys.path.insert(0, str(newsagent_scripts))
    from absence_10h_synthesize import discard_hourly  # type: ignore
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "shadow.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE bridge_discards ("
            "reason TEXT, discarded_at REAL)"
        )
        conn.execute(
            "CREATE TABLE telemetry ("
            "run_id INT, approved INT, reject_reason TEXT, "
            "reject_detail TEXT, telemetry_class TEXT)"
        )
        conn.executemany(
            "INSERT INTO telemetry VALUES (?,?,?,?,?)",
            [
                (13, 1, "NONE", None, None),
                (13, 0, "NONE", None, "UNACTIONABLE_SELL_NO_INVENTORY"),
                (13, 0, "NO_SNAPSHOT", None, None),
            ],
        )
        conn.commit()
        conn.close()
        out = discard_hourly(
            db, datetime(2020, 1, 1, tzinfo=timezone.utc), min_run_id=13,
        )
        tel = out["telemetry_min_run"]
        assert tel["n"] == 3
        assert tel["rejects"] == 1
        assert tel["unactionable"] == 1
        assert "UNACTIONABLE_SELL_NO_INVENTORY" in tel["telemetry_class_top"]
        print("OK test_w3_absence_splits_rejects")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("S2-W3 NACHWEIS grün")
