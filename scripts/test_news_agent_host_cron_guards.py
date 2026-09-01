#!/usr/bin/env python3
"""Smoke tests for launchd schedulable-path guards."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.news_agent_host_cron import canonical_schedulable_root, verify_schedulable_root


def test_canonical_prefers_data_volume() -> None:
    ro = Path("/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage")
    if not ro.exists():
        return
    canon = canonical_schedulable_root(ro)
    assert "THX_OS_ULTRA - Data" in str(canon)


def test_verify_schedulable_root_writable() -> None:
    with TemporaryDirectory() as td:
        root = Path(td) / "repo"
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
        out = verify_schedulable_root(root)
        assert out == root.resolve()


def run() -> None:
    test_canonical_prefers_data_volume()
    test_verify_schedulable_root_writable()
    print("news_agent_host_cron_guards: 2/2 passed")


if __name__ == "__main__":
    run()
