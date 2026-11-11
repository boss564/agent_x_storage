"""M-W0 / N-6: Event-log path is absolute and cwd-independent (Bauplan v1.2 §7).

Acceptance: start from /tmp with relative default → write under <repo>/newsagent/logs/;
Start-Log path is absolute; no second log under /tmp/newsagent/logs/.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from order_execution_engine.event_log import (
    DEFAULT_EVENT_LOG_PATH,
    JsonlEventLog,
    find_repo_root,
    iter_events,
    resolve_event_log_path,
)


def test_m_w0_n6_find_repo_root_contains_engine() -> None:
    root = find_repo_root()
    assert (root / "order_execution_engine").is_dir()
    print(f"OK test_m_w0_n6_find_repo_root_contains_engine root={root}")


def test_m_w0_n6_absolute_env_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        abs_path = Path(tmp) / "abs_events.jsonl"
        got = resolve_event_log_path(str(abs_path))
        assert got is not None
        assert got.is_absolute()
        assert got == abs_path.resolve()
        print("OK test_m_w0_n6_absolute_env_unchanged")


def test_m_w0_n6_start_from_tmp_writes_under_repo() -> None:
    """Start-aus-/tmp-Test (Bauplan N-6 Akzeptanz)."""
    repo = find_repo_root()
    rel = "newsagent/logs/_mw0_n6_tmp_cwd_test.jsonl"
    target = (repo / rel).resolve()
    tmp_ghost = Path("/tmp/newsagent/logs/_mw0_n6_tmp_cwd_test.jsonl")
    if target.exists():
        target.unlink()
    if tmp_ghost.exists():
        tmp_ghost.unlink()

    old_cwd = Path.cwd()
    old_env = os.environ.get("SHADOW_EVENT_LOG")
    try:
        os.chdir("/tmp")
        os.environ.pop("SHADOW_EVENT_LOG", None)
        # Explicit relative (same contract as DEFAULT) — must ignore cwd=/tmp.
        path = resolve_event_log_path(rel)
        assert path is not None
        assert path.is_absolute(), path
        assert path == target
        assert str(path).startswith(str(repo))
        assert "/tmp/newsagent" not in str(path)

        log = JsonlEventLog(path, producer="runner")
        log.emit("tick_sample", token_id="mw0-n6", cache_state="MISS", age_s=None)
        assert path.is_file()
        rows = iter_events(path)
        assert len(rows) == 1
        assert rows[0]["token_id"] == "mw0-n6"
        assert not tmp_ghost.exists(), "cwd-relative ghost log must not appear"
        # Default relative string also resolves under repo from /tmp.
        default_path = resolve_event_log_path(DEFAULT_EVENT_LOG_PATH)
        assert default_path is not None and default_path.is_absolute()
        assert default_path == (repo / DEFAULT_EVENT_LOG_PATH).resolve()
        print(
            "OK test_m_w0_n6_start_from_tmp_writes_under_repo "
            f"absolute_path={path}"
        )
    finally:
        os.chdir(old_cwd)
        if old_env is None:
            os.environ.pop("SHADOW_EVENT_LOG", None)
        else:
            os.environ["SHADOW_EVENT_LOG"] = old_env
        if target.exists():
            target.unlink()
        # Remove empty dirs we may have created under repo (not /tmp ghost).
        for parent in (target.parent,):
            try:
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass


def test_m_w0_n6_off_still_disables() -> None:
    assert resolve_event_log_path("off") is None
    assert resolve_event_log_path("0") is None
    print("OK test_m_w0_n6_off_still_disables")


if __name__ == "__main__":
    os.environ.setdefault("SHADOW_EVENT_LOG", "off")
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("M-W0 N-6 NACHWEIS grün")
