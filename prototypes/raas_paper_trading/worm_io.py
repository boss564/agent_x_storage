"""Streaming WORM JSONL I/O — avoid path.read_text() OOM on large live archives.

Root cause (2026-08-29): A2 called path.read_text().splitlines() twice per cycle on
~670k-line live WORMs → peak RSS >2GiB → OOMKilled / CrashLoopBackOff.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional, Union


def iter_jsonl_rows(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield parsed JSON objects line-by-line (O(1) file buffer)."""
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def read_last_jsonl_chunk(path: Path, *, max_bytes: int = 65536) -> str:
    """Read a trailing byte window for reverse scans (does not load whole file)."""
    if not path.is_file():
        return ""
    size = path.stat().st_size
    if size <= 0:
        return ""
    read_n = min(max_bytes, size)
    with path.open("rb") as f:
        f.seek(max(0, size - read_n))
        raw = f.read(read_n)
    # Drop partial first line when we seek mid-file
    text = raw.decode("utf-8", errors="replace")
    if size > read_n:
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1 :]
    return text


def last_jsonl_row(path: Path, *, max_bytes: int = 65536) -> Optional[Dict[str, Any]]:
    """Return the last valid JSON object in a JSONL file (tail seek, no full read)."""
    if not path.is_file():
        return None
    size = path.stat().st_size
    window = max_bytes
    while window <= size + max_bytes:
        text = read_last_jsonl_chunk(path, max_bytes=window)
        if not text:
            return None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                return row
        if window >= size:
            return None
        window = min(size, window * 4)
    return None


def last_signal_row(path: Path, *, max_bytes: int = 65536) -> Optional[Dict[str, Any]]:
    """Return the last SIGNAL row by scanning a trailing chunk backwards."""
    text = read_last_jsonl_chunk(path, max_bytes=max_bytes)
    if not text:
        return None
    # Grow window if no SIGNAL in first chunk (rare: long non-SIGNAL tail)
    size = path.stat().st_size
    window = max_bytes
    while True:
        last: Optional[Dict[str, Any]] = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("action") == "SIGNAL":
                last = row
        if last is not None:
            return last
        if window >= size:
            return None
        window = min(size, window * 4)
        text = read_last_jsonl_chunk(path, max_bytes=window)


def load_signal_mark_prices(
    path: Path,
    *,
    max_ticks: Optional[int] = None,
) -> List[float]:
    """Extract mark_price from SIGNAL rows (chronological).

    If max_ticks is set, keep only the **last** N prices (deque tail) so memory
    stays O(max_ticks) on multi-100k-line live WORMs.
    """
    if not path.is_file():
        return []
    if max_ticks is not None and max_ticks <= 0:
        return []

    buf: Union[Deque[float], List[float]]
    if max_ticks is None:
        buf = []
        append = buf.append
    else:
        buf = deque(maxlen=max_ticks)
        append = buf.append

    for row in iter_jsonl_rows(path):
        if row.get("action") != "SIGNAL":
            continue
        raw = row.get("mark_price")
        if raw is None:
            continue
        try:
            append(float(raw))
        except (TypeError, ValueError):
            continue
    return list(buf)
