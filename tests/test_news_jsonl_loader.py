"""Tests for src.ingestion.news_jsonl_loader."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from src.ingestion.news_jsonl_loader import (
    discover_news_jsonl_files,
    iter_news_records,
    iter_news_records_tail,
    load_recent_records,
    sort_news_jsonl_files,
    tail_jsonl_lines,
)


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_sort_active_file_last(tmp_path: Path) -> None:
    a = tmp_path / "news_scores.jsonl-20250901"
    b = tmp_path / "news_scores.jsonl"
    a.touch()
    b.touch()
    ordered = sort_news_jsonl_files([b, a])
    assert ordered[0].name.startswith("news_scores.jsonl-")
    assert ordered[-1].name == "news_scores.jsonl"


def test_iter_only_active(tmp_path: Path) -> None:
    active = tmp_path / "news_scores.jsonl"
    archive = tmp_path / "news_scores.jsonl-20250901.gz"
    _write(active, [{"id": 1, "source_type": "rss"}])
    with gzip.open(archive, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"id": 0, "source_type": "rss"}) + "\n")

    rows = list(iter_news_records(tmp_path, only_active=True))
    assert len(rows) == 1
    assert rows[0]["id"] == 1


def test_iter_max_files_and_order(tmp_path: Path) -> None:
    old = tmp_path / "news_scores.jsonl-20250901"
    mid = tmp_path / "news_scores.jsonl-20250902"
    active = tmp_path / "news_scores.jsonl"
    _write(old, [{"n": 1}])
    _write(mid, [{"n": 2}])
    _write(active, [{"n": 3}])

    rows = list(iter_news_records(tmp_path, max_files=2))
    assert [r["n"] for r in rows] == [2, 3]


def test_skip_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "news_scores.jsonl"
    path.write_text('{"ok": true}\n{broken\n{"ok": false}\n', encoding="utf-8")
    rows = list(iter_news_records(tmp_path, only_active=True, skip_corrupt=True))
    assert len(rows) == 2


def test_tail_and_iter_tail(tmp_path: Path) -> None:
    path = tmp_path / "news_scores.jsonl"
    _write(path, [{"i": i} for i in range(10)])
    lines = tail_jsonl_lines(path, 3)
    assert len(lines) == 3
    tail_rows = list(iter_news_records_tail(path, sample_size=2))
    assert [r["i"] for r in tail_rows] == [8, 9]


def test_load_recent_passes_modified_after(tmp_path: Path) -> None:
    from unittest.mock import patch

    with patch("src.ingestion.news_jsonl_loader.iter_news_records") as mock_iter:
        mock_iter.return_value = iter([{"tag": "new"}])
        rows = load_recent_records(tmp_path, days=5)
        assert rows == [{"tag": "new"}]
        kwargs = mock_iter.call_args.kwargs
        assert kwargs.get("modified_after") is not None


def test_discover_empty_dir(tmp_path: Path) -> None:
    empty = tmp_path / "empty_sub"
    empty.mkdir()
    assert discover_news_jsonl_files(empty) == []
    assert discover_news_jsonl_files(tmp_path / "missing") == []


def test_load_seen_and_markers_across_archive(tmp_path: Path) -> None:
    from services.news_agent.core.processor import load_seen
    from services.news_agent.liveness import last_run_marker, load_run_markers

    archive = tmp_path / "news_scores.jsonl-20250901"
    active = tmp_path / "news_scores.jsonl"
    archive.write_text(
        "\n".join(
            [
                json.dumps({"item_id": "seen-1", "url": "https://example.test/1"}),
                json.dumps(
                    {
                        "source_type": "run_marker",
                        "ts": "2026-09-01T10:00:00+00:00",
                        "feeds": {},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write(
        active,
        [{"source_type": "run_marker", "ts": "2026-09-01T12:00:00+00:00", "feeds": {}}],
    )

    seen = load_seen(active)
    assert "seen-1" in seen
    assert "https://example.test/1" in seen

    markers = load_run_markers(active)
    assert len(markers) == 2
    last = last_run_marker(active)
    assert last is not None
    assert last["ts"] == "2026-09-01T12:00:00+00:00"


def run() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as td:
        root = Path(td)
        test_sort_active_file_last(root)
        test_iter_only_active(root)
        test_iter_max_files_and_order(root)
        test_skip_corrupt_json(root)
        test_tail_and_iter_tail(root)
        test_load_recent_passes_modified_after(root)
        test_discover_empty_dir(root)
        test_load_seen_and_markers_across_archive(root)
    print("news_jsonl_loader: 8/8 passed")


if __name__ == "__main__":
    run()
