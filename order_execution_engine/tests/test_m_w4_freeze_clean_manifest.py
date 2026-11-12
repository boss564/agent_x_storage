"""M-W4: Clean-Tree + allowlist freeze sha + stash quarantine + Manifest fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from order_execution_engine.messlauf_clean_tree import (
    AX_MESS_PREFIXES,
    check_clean_tree,
)
from order_execution_engine.messlauf_manifest import (
    ALLOWLIST_FREEZE_SHA_HISTORICAL,
    HASH_RELATION_DE,
    STASH_PATCH_SHA_QUARANTINE,
    STASH_REV_QUARANTINE,
    _is_docs_only,
    build_manifest,
    measure_stash_quarantine,
    sha256_file,
    write_manifest,
)

REPO = Path(__file__).resolve().parents[2]
AX = REPO
NA = REPO / "newsagent"
FREEZE = AX / "order_execution_engine" / "ops" / "allowlist.freeze.json"


def test_m_w4_allowlist_freeze_sha_unchanged() -> None:
    assert FREEZE.is_file()
    assert sha256_file(FREEZE) == ALLOWLIST_FREEZE_SHA_HISTORICAL
    print("OK test_m_w4_allowlist_freeze_sha_unchanged")


def test_m_w4_stash_quarantine_hashes() -> None:
    rev, patch = measure_stash_quarantine(AX)
    assert rev == STASH_REV_QUARANTINE
    assert patch == STASH_PATCH_SHA_QUARANTINE
    print("OK test_m_w4_stash_quarantine_hashes")


def test_m_w4_ax_mess_path_clean() -> None:
    r = check_clean_tree(AX, repo="agent_x", prefixes=AX_MESS_PREFIXES)
    # Allow only the M-W4 deliverable files themselves while uncommitted; after
    # the Freeze-Pin commit porcelain_mess must be empty.
    wip_paths = {
        "order_execution_engine/messlauf_clean_tree.py",
        "order_execution_engine/messlauf_manifest.py",
        "order_execution_engine/tests/test_m_w4_freeze_clean_manifest.py",
    }

    def _path(line: str) -> str:
        body = line[3:] if len(line) > 3 else line
        if " -> " in body:
            body = body.split(" -> ", 1)[1]
        return body.strip().strip('"')

    unexpected = [ln for ln in r.porcelain_mess if _path(ln) not in wip_paths]
    assert not unexpected, f"AX mess-path dirty: {unexpected} ignored={r.ignored_mess}"
    assert not r.ignored_mess, f"AX ignored mess contamination: {r.ignored_mess}"
    print("OK test_m_w4_ax_mess_path_clean", r.detail, "wip_ok", len(r.porcelain_mess))


def test_m_w4_docs_only_helper() -> None:
    assert _is_docs_only([]) is True
    assert _is_docs_only(["reports/M_W4.md", "docs/x.md"]) is True
    assert _is_docs_only(["order_execution_engine/x.py"]) is False
    print("OK test_m_w4_docs_only_helper")


def test_m_w4_hash_relation_documents_three_hashes() -> None:
    assert "5adab542" in HASH_RELATION_DE
    assert "487b3547" in HASH_RELATION_DE
    assert "43445de8" in HASH_RELATION_DE
    assert "code_freeze_pin" in HASH_RELATION_DE
    print("OK test_m_w4_hash_relation_documents_three_hashes")


def test_m_w4_manifest_roundtrip(tmp_path: Path) -> None:
    # Pins = current HEAD (pin==tip → docs-only vacuously).
    import subprocess

    ax_head = subprocess.check_output(
        ["git", "-C", str(AX), "rev-parse", "HEAD"], text=True
    ).strip()
    na_head = subprocess.check_output(
        ["git", "-C", str(NA), "rev-parse", "HEAD"], text=True
    ).strip()
    man = build_manifest(
        ax_root=AX,
        na_root=NA,
        code_freeze_pin_ax=ax_head,
        code_freeze_pin_na=na_head,
        suite={"passed": 0, "xfailed": 0, "exit": 0, "note": "unit"},
        allow_dirty_for_test=True,  # WIP before Freeze-Pin commit
    )
    assert man.kein_lauf is True
    assert man.push == "held"
    assert man.allowlist_freeze_sha == ALLOWLIST_FREEZE_SHA_HISTORICAL
    assert man.charter["max_book_age_ms"] == 2000
    assert man.charter["order_send"] is False
    assert man.charter["diagnostic_only"] is True
    assert man.pin_to_tip_ax_docs_only is True
    out = tmp_path / "MESSLAUF_MANIFEST.json"
    write_manifest(man, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["wave"] == "M-W4"
    assert loaded["stash_rev"] == STASH_REV_QUARANTINE
    print("OK test_m_w4_manifest_roundtrip")


def test_m_w4_n2_stub_not_replaced() -> None:
    """R1: M-W4 must not materialize N-2 apply_fill (stays M-W5 / xfail)."""
    w4 = (
        AX
        / "order_execution_engine"
        / "tests"
        / "test_schritt2_w4_charter_smoke.py"
    )
    src = w4.read_text(encoding="utf-8")
    assert "@pytest.mark.xfail(strict=True" in src
    assert "raise AssertionError" in src
    print("OK test_m_w4_n2_stub_not_replaced")


if __name__ == "__main__":
    test_m_w4_allowlist_freeze_sha_unchanged()
    test_m_w4_stash_quarantine_hashes()
    test_m_w4_ax_mess_path_clean()
    test_m_w4_docs_only_helper()
    test_m_w4_hash_relation_documents_three_hashes()
    test_m_w4_n2_stub_not_replaced()
    print("M-W4 NACHWEIS (ohne tmp manifest) grün")
