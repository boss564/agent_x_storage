"""Streaming readers for news_scores JSONL (+ logrotate archives)."""
from __future__ import annotations

import gzip
import json
import logging
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, TextIO, Union

logger = logging.getLogger(__name__)

DEFAULT_BASENAME = "news_scores.jsonl"
OpenText = Callable[..., TextIO]

_DATEEXT_SUFFIX_RE = re.compile(r"^\d{8}(?:-\d+)?$")
_NUMERIC_SUFFIX_RE = re.compile(r"^(\d+)$")


def _archive_sort_key(path: Path, *, basename: str = DEFAULT_BASENAME) -> tuple[int, int, str]:
    """Oldest archives first, active file last.

    ``dateext`` with ``-%Y%m%d-%s`` (Hetzner template): lex order = chrono order.
    Legacy ``-%Y%m%d`` only: same. Numeric ``.N`` (no dateext): higher N = older.
    """
    name = path.name
    if name == basename:
        return (1, 0, "")

    stem = name[:-3] if name.endswith(".gz") else name
    if not stem.startswith(basename):
        return (0, 0, name)

    tail = stem[len(basename) :]
    if tail.startswith("-"):
        suffix = tail[1:]
        if _DATEEXT_SUFFIX_RE.match(suffix):
            return (0, 0, suffix)
    if tail.startswith(".") and (m := _NUMERIC_SUFFIX_RE.match(tail[1:])):
        # Higher N = older archive → read first → smaller sort key via negation.
        return (0, -int(m.group(1)), "")

    return (0, 0, name)


def sort_news_jsonl_files(files: List[Path], *, basename: str = DEFAULT_BASENAME) -> List[Path]:
    """Oldest archives first, active ``news_scores.jsonl`` last."""
    return sorted(files, key=lambda p: _archive_sort_key(p, basename=basename))


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")  # type: ignore[return-value]
    return path.open("r", encoding="utf-8")


def discover_news_jsonl_files(
    data_dir: Path | str,
    *,
    pattern: str = "news_scores.jsonl*",
    basename: str = DEFAULT_BASENAME,
    max_files: Optional[int] = None,
    only_active: bool = False,
    modified_after: Optional[datetime] = None,
) -> List[Path]:
    """Resolve JSONL paths to read (archives + active file)."""
    base = Path(data_dir)
    if not base.is_dir():
        return []

    if only_active:
        active = base / basename
        return [active] if active.is_file() else []

    files = [p for p in base.glob(pattern) if p.is_file()]
    if modified_after is not None:
        cutoff = modified_after
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        kept: List[Path] = []
        for path in files:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                kept.append(path)
        files = kept

    files = sort_news_jsonl_files(files, basename=basename)
    if max_files is not None and max_files > 0:
        files = files[-max_files:]
    return files


def iter_jsonl_lines(
    filepath: Path,
    *,
    skip_corrupt: bool = True,
) -> Iterator[Dict[str, Any]]:
    """Yield parsed JSON objects from one plain or ``.gz`` JSONL file."""
    try:
        with _open_text(filepath) as handle:
            for line_num, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    if skip_corrupt:
                        logger.warning(
                            "Corrupt JSON in %s line %s: %s",
                            filepath,
                            line_num,
                            exc,
                        )
                        continue
                    raise
                if isinstance(row, dict):
                    yield row
    except (OSError, gzip.BadGzipFile) as exc:
        logger.error("Failed to read %s: %s", filepath, exc)


def iter_news_records(
    data_dir: str | Path = "data",
    *,
    pattern: str = "news_scores.jsonl*",
    basename: str = DEFAULT_BASENAME,
    max_files: Optional[int] = None,
    only_active: bool = False,
    modified_after: Optional[datetime] = None,
    skip_corrupt: bool = True,
) -> Iterator[Dict[str, Any]]:
    """
    Stream records from active JSONL and/or logrotate archives (oldest file first).

    WORM-safe: read-only iterator; does not mutate sources.
    """
    files = discover_news_jsonl_files(
        data_dir,
        pattern=pattern,
        basename=basename,
        max_files=max_files,
        only_active=only_active,
        modified_after=modified_after,
    )
    if not files:
        logger.warning("No news JSONL files under %s (pattern=%s)", data_dir, pattern)
        return

    for filepath in files:
        logger.debug("Reading %s", filepath)
        yield from iter_jsonl_lines(filepath, skip_corrupt=skip_corrupt)


def iter_jsonl_store(
    store_path: Path | str,
    *,
    max_files: Optional[int] = None,
    only_active: bool = False,
    modified_after: Optional[datetime] = None,
    skip_corrupt: bool = True,
) -> Iterator[Dict[str, Any]]:
    """Stream records for one logical JSONL path (active file + rotated archives)."""
    path = Path(store_path)
    yield from iter_news_records(
        path.parent,
        basename=path.name,
        max_files=max_files,
        only_active=only_active,
        modified_after=modified_after,
        skip_corrupt=skip_corrupt,
    )


def tail_jsonl_lines(filepath: Path | str, n: int) -> List[str]:
    """Last *n* non-empty lines from a single JSONL file (bounded memory)."""
    if n <= 0:
        return []
    path = Path(filepath)
    if not path.is_file():
        return []
    with _open_text(path) as handle:
        lines = [line.rstrip("\n") for line in deque(handle, maxlen=n)]
    return [line for line in lines if line.strip()]


def iter_news_records_tail(
    filepath: Path | str,
    *,
    sample_size: int = 50,
    skip_corrupt: bool = True,
) -> Iterator[Dict[str, Any]]:
    """Newest *sample_size* records from the active JSONL only (watchdog-friendly)."""
    for line in tail_jsonl_lines(filepath, sample_size):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if skip_corrupt:
                continue
            raise
        if isinstance(row, dict):
            yield row


def load_all_news_records(
    data_dir: str | Path = "data",
    *,
    max_files: Optional[int] = None,
    skip_corrupt: bool = True,
) -> List[Dict[str, Any]]:
    """Materialize all records — use only when necessary (memory)."""
    return list(
        iter_news_records(
            data_dir,
            max_files=max_files,
            skip_corrupt=skip_corrupt,
        )
    )


def load_recent_records(
    data_dir: str | Path = "data",
    *,
    days: int = 7,
    skip_corrupt: bool = True,
) -> List[Dict[str, Any]]:
    """Records from files touched in the last *days* (by mtime)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return list(
        iter_news_records(
            data_dir,
            modified_after=cutoff,
            skip_corrupt=skip_corrupt,
        )
    )
