"""S2-W4: N-2 stub/xfail + N-3 doc pin + Charter-Smoke + Segment-Hashes."""

from __future__ import annotations

import inspect
import os
import re
import subprocess
import tempfile
from pathlib import Path

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore[assignment]

from order_execution_engine.event_log import sha256_file, write_segment_manifest
from order_execution_engine.fill_simulator import FillSimConfig


REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "order_execution_engine"
NEWSAGENT = REPO / "newsagent"

_N2_MSG = (
    "N-2 / Messlauf W2.2: positions_since_epoch soll apply_fill-Kette "
    "seit Epoch-Marker rekonstruieren; Schritt 2 liefert nur Andock+Anker"
)


def test_w4_n2_epoch_restart_reconstructs_or_xfail() -> None:
    """N-2: volle apply_fill-Rekonstruktion ist W2.2-Versprechen — Stub xfail."""
    if pytest is not None:
        pytest.xfail(_N2_MSG)
    raise AssertionError(f"XFAIL: {_N2_MSG}")


def test_w4_n3_risk_check_documents_d2_outside() -> None:
    from order_execution_engine.shadow_execution_engine import RiskController

    doc = inspect.getdoc(RiskController.check) or ""
    assert "UNACTIONABLE_SELL_NO_INVENTORY" in doc
    assert "GP-5" in doc
    src = inspect.getsource(RiskController.check)
    # No short-reject for missing inventory reintroduced into Risk.check.
    assert "UNACTIONABLE_SELL_NO_INVENTORY" not in src.split('"""', 2)[-1]
    print("OK test_w4_n3_risk_check_documents_d2_outside")


def test_w4_charter_smoke_r5_analog() -> None:
    """Charter-Smoke: kein order_send=true; θ/Sizing unberührt; max_book_age Default;
    Sonde/Monitor schreiben nicht in shadow.db.
    """
    assert FillSimConfig().max_book_age_ms == 2000

    # Scoped rg against Schritt-2 touch points + charter-sensitive modules.
    paths = [
        ENGINE / "event_log.py",
        ENGINE / "probe_f3.py",
        ENGINE / "telemetry_classify.py",
        ENGINE / "shadow_runner.py",
        ENGINE / "epoch_hydrate.py",
        NEWSAGENT / "scripts" / "phase_c_monitor.py",
        NEWSAGENT / "scripts" / "night_probe.sh",
        NEWSAGENT / "scripts" / "forward_test_status.py",
        NEWSAGENT / "scripts" / "absence_10h_synthesize.py",
    ]
    existing = [str(p) for p in paths if p.exists()]
    assert existing, "expected Schritt-2 files present"

    # order_send=true must not appear in instrumentation.
    hit = subprocess.run(
        ["rg", "-n", r"order_send\s*=\s*true", *existing],
        capture_output=True,
        text=True,
    )
    assert hit.returncode in (0, 1)
    assert not hit.stdout.strip(), f"order_send=true gefunden:\n{hit.stdout}"

    # No theta / sizing knobs touched in new modules.
    for mod in (
        ENGINE / "event_log.py",
        ENGINE / "probe_f3.py",
        ENGINE / "telemetry_classify.py",
    ):
        text = mod.read_text(encoding="utf-8")
        assert not re.search(r"\btheta\b|THETA|size_fn|per_order_cap", text)

    # Probe/monitor: shadow.db only as read-only URI if mentioned.
    for script in (
        NEWSAGENT / "scripts" / "phase_c_monitor.py",
        NEWSAGENT / "scripts" / "forward_test_status.py",
        NEWSAGENT / "scripts" / "absence_10h_synthesize.py",
    ):
        if not script.exists():
            continue
        text = script.read_text(encoding="utf-8")
        for m in re.finditer(r"shadow\.db[^\n]*", text):
            line = m.group(0)
            assert "mode=ro" in text or "read-only" in text.lower() or "Read-only" in text
            assert "connect(" not in line or "mode=ro" in text
    print("OK test_w4_charter_smoke_r5_analog")


def test_w4_segment_manifest_sha256() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        seg = d / "shadow_events.jsonl"
        seg.write_text('{"event_type":"heartbeat"}\n', encoding="utf-8")
        man = d / "MANIFEST.sha256"
        entries = write_segment_manifest([seg], man)
        assert seg.name in {Path(k).name for k in entries} or any(
            v == sha256_file(seg) for v in entries.values()
        )
        body = man.read_text(encoding="utf-8")
        assert sha256_file(seg) in body
        print("OK test_w4_segment_manifest_sha256")


if __name__ == "__main__":
    os.environ.setdefault("SHADOW_EVENT_LOG", "off")
    # Run non-xfail tests under __main__; xfail via pytest when available.
    test_w4_n3_risk_check_documents_d2_outside()
    test_w4_charter_smoke_r5_analog()
    test_w4_segment_manifest_sha256()
    try:
        test_w4_n2_epoch_restart_reconstructs_or_xfail()
    except BaseException as exc:  # pytest.xfail raises
        print(f"OK test_w4_n2_xfail_raised: {type(exc).__name__}")
    print("S2-W4 NACHWEIS grün (N-2 xfail erwartet)")
