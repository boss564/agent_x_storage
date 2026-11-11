"""M-W3: N-9 import-fail → warn + n4_split=unavailable; N-10 strict xfail pin."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NEWSAGENT_SCRIPTS = REPO / "newsagent" / "scripts"
ENGINE_TESTS = Path(__file__).resolve().parent


def _load_n4_resolve():
    if str(NEWSAGENT_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(NEWSAGENT_SCRIPTS))
    import n4_classify_resolve as mod  # type: ignore

    return mod


def test_m_w3_n9_import_fail_warns_and_sets_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_n4_resolve()

    def boom():
        raise ImportError("simulated telemetry_classify missing (N-9)")

    classify, row_get, n4_split = mod.resolve_n4_classify(import_fn=boom)
    assert classify is None
    assert row_get is None
    assert n4_split == mod.N4_SPLIT_UNAVAILABLE == "unavailable"
    err = capsys.readouterr().err
    assert "WARN N-9" in err
    assert 'n4_split=unavailable' in err or "n4_split=unavailable" in err
    print("OK test_m_w3_n9_import_fail_warns_and_sets_unavailable")


def test_m_w3_n9_ok_import_sets_n4_split_ok() -> None:
    mod = _load_n4_resolve()
    classify, row_get, n4_split = mod.resolve_n4_classify()
    assert classify is not None
    assert row_get is not None
    assert n4_split == mod.N4_SPLIT_OK == "ok"
    assert classify(approved=0, telemetry_class="UNACTIONABLE_SELL_NO_INVENTORY") == (
        "unactionable"
    )
    print("OK test_m_w3_n9_ok_import_sets_n4_split_ok")


def test_m_w3_n9_absence_exposes_n4_split_field() -> None:
    """discard_hourly return carries n4_split (ok path under normal PYTHONPATH)."""
    import sqlite3
    import tempfile

    if str(NEWSAGENT_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(NEWSAGENT_SCRIPTS))
    from absence_10h_synthesize import discard_hourly  # type: ignore
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "shadow.db"
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE bridge_discards (reason TEXT, discarded_at REAL)"
        )
        conn.execute(
            "CREATE TABLE telemetry ("
            "run_id INT, approved INT, reject_reason TEXT, "
            "reject_detail TEXT, telemetry_class TEXT)"
        )
        conn.execute(
            "INSERT INTO telemetry VALUES (?,?,?,?,?)",
            (13, 0, "NONE", None, "UNACTIONABLE_SELL_NO_INVENTORY"),
        )
        conn.commit()
        conn.close()
        out = discard_hourly(
            db, datetime(2020, 1, 1, tzinfo=timezone.utc), min_run_id=13
        )
    tel = out["telemetry_min_run"]
    assert tel["n4_split"] == "ok"
    assert tel["unactionable"] == 1
    print("OK test_m_w3_n9_absence_exposes_n4_split_field")


def test_m_w3_n10_n2_xfail_is_strict_mark() -> None:
    """N-10 Source-Pin: @pytest.mark.xfail(strict=True, reason=…) on N-2 stub."""
    from order_execution_engine.tests import test_schritt2_w4_charter_smoke as w4

    fn = w4.test_w4_n2_epoch_restart_reconstructs_or_xfail
    mark = fn.pytestmark
    assert mark, "expected pytestmark on N-2 stub"
    xfail_marks = [m for m in mark if m.name == "xfail"]
    assert len(xfail_marks) == 1, f"expected one xfail mark, got {mark}"
    m = xfail_marks[0]
    assert m.kwargs.get("strict") is True
    reason = m.kwargs.get("reason") or ""
    assert "N-2" in reason and "apply_fill" in reason
    # Body must still fail (no soft pass) — XPASS would fail the suite under strict.
    src = inspect.getsource(fn)
    assert "raise AssertionError" in src
    assert "pytest.xfail(" not in src  # no imperative soft xfail
    print("OK test_m_w3_n10_n2_xfail_is_strict_mark")


if __name__ == "__main__":
    class _Cap:
        def readouterr(self):
            return type("O", (), {"err": "", "out": ""})()

    test_m_w3_n9_ok_import_sets_n4_split_ok()
    test_m_w3_n9_absence_exposes_n4_split_field()
    test_m_w3_n10_n2_xfail_is_strict_mark()
    print("M-W3 NACHWEIS grün (N-9 Import-Fail-Pfad unter pytest capsys)")
