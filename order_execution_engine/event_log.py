"""Append-only Event-Log for Shadow Phase-C freshness (Schritt 2 / GP-S2).

GP-S2-7: JSONL only — never write runner ``shadow.db``.
GP-S2-2: every event carries ``ts_mono`` + ``wall_ts``.
GP-S2-1: runner ``SnapshotCache.update`` and probe wrap are separate producers.
GP-S2-3: store observations only — no baked streak/OK judgments.
"""

from __future__ import annotations

import json
import os
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from order_execution_engine.market_data_feed import SnapshotCache
from order_execution_engine.shadow_execution_engine import MarketSnapshot

DEFAULT_EVENT_LOG_PATH = "newsagent/logs/shadow_events.jsonl"

# Tap anchors — re-pinned 2026-11-11 after G8 SP-1926 (M-a).
# Fund: peek-Insert 2195610f (+ Test d2889bdb) shifted live lines;
# Anker-Test was ROT on HEAD. Conscious re-pin (Fund, kein stiller Fix).
#   SnapshotCache.update          market_data_feed.py:57
#   PolySentinelBookHandler.on_book_update → cache.update  (call :175)
TAP_ANCHOR_UPDATE = "market_data_feed.py:57"
TAP_ANCHOR_ON_BOOK_UPDATE_CALL = "market_data_feed.py:175"


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up to the directory that contains ``order_execution_engine/``.

    N-6 (Bauplan v1.2): Event-log default must not depend on process cwd.
    Same walk-up contract as ``newsagent/scripts/night_probe.sh``.
    """
    cur = (start or Path(__file__).resolve()).parent
    for candidate in (cur, *cur.parents):
        if (candidate / "order_execution_engine").is_dir():
            return candidate
    raise FileNotFoundError(
        "order_execution_engine/ not found walking up from "
        f"{start or Path(__file__).resolve()}"
    )


def resolve_event_log_path(raw: Optional[str] = None) -> Optional[Path]:
    """Return absolute log path or None when disabled (``0``/``off``/``false``/empty).

    N-6: relative paths resolve against repo root (walk-up), never against cwd.
    Absolute env/plist values are kept (``.resolve()`` only).
    """
    if raw is None:
        raw = os.environ.get("SHADOW_EVENT_LOG", DEFAULT_EVENT_LOG_PATH)
    text = (raw or "").strip()
    if text.lower() in ("", "0", "off", "false", "no"):
        return None
    path = Path(text)
    if path.is_absolute():
        return path.resolve()
    return (find_repo_root() / path).resolve()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


# N-7: reader observation counter (not a Gate verdict — Charter: observation only).
corrupt_line_total: int = 0


def reset_corrupt_line_total() -> None:
    """Test helper — reset module corrupt_line_total."""
    global corrupt_line_total
    corrupt_line_total = 0


class JsonlEventLog:
    """Thread-safe append-only JSONL sink (observations only)."""

    def __init__(
        self,
        path: Path,
        *,
        producer: str,
        instance_id: Optional[str] = None,
        cycle_seq: Optional[int] = None,
    ) -> None:
        self.path = Path(path)
        self.producer = producer
        self.instance_id = instance_id
        self.cycle_seq = cycle_seq
        self._lock = threading.Lock()
        self._rowid = 0
        # N-7: emit failures are observations, not Gate judgments.
        self.emit_drop_total: int = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, **fields: Any) -> Optional[dict[str, Any]]:
        """Append one observation. Always sets ts_mono + wall_ts (GP-S2-2).

        N-7: disk/IO errors are swallowed; ``emit_drop_total`` increments; feed
        continues. Returns the in-memory row on success, None on drop.
        """
        with self._lock:
            self._rowid += 1
            row: dict[str, Any] = {
                "rowid": self._rowid,
                "ts_mono": time.monotonic(),
                "wall_ts": time.time(),
                "event_type": event_type,
                "producer": self.producer,
            }
            if self.instance_id is not None:
                row["instance_id"] = self.instance_id
            if self.cycle_seq is not None:
                row["cycle_seq"] = self.cycle_seq
            for key, value in fields.items():
                if value is not None or key in (
                    "best_bid",
                    "best_ask",
                    "received_at",
                    "source",
                    "age_s",
                    "cache_state",
                ):
                    row[key] = _jsonable(value)
            line = json.dumps(row, separators=(",", ":"), sort_keys=True)
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                self.emit_drop_total += 1
                return None
            return row

    def emit_book_update(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        return self.emit(
            "book_update",
            token_id=snapshot.token_id,
            best_bid=snapshot.best_bid(),
            best_ask=snapshot.best_ask(),
            received_at=snapshot.received_at,
            source=getattr(snapshot, "source", None),
            tap_anchor=TAP_ANCHOR_UPDATE,
        )

    def emit_tick_sample(
        self,
        token_id: str,
        peeked: Optional[MarketSnapshot],
        *,
        now: Optional[float] = None,
        max_age_s: Optional[float] = None,
    ) -> dict[str, Any]:
        """Runner decision-takt sample — may exist without any book_update (A-A6)."""
        wall = now if now is not None else time.time()
        if peeked is None:
            return self.emit(
                "tick_sample",
                token_id=token_id,
                best_bid=None,
                best_ask=None,
                received_at=None,
                source=None,
                age_s=None,
                cache_state="MISS",
            )
        age = max(0.0, wall - float(peeked.received_at))
        state = "OK"
        if max_age_s is not None and age > float(max_age_s):
            state = "STALE"
        return self.emit(
            "tick_sample",
            token_id=token_id,
            best_bid=peeked.best_bid(),
            best_ask=peeked.best_ask(),
            received_at=peeked.received_at,
            source=getattr(peeked, "source", None),
            age_s=age,
            cache_state=state,
        )

    def emit_probe_sample(
        self,
        token_id: str,
        *,
        age_s: Optional[float],
        cache_state: Optional[str],
        best_bid: Any = None,
        best_ask: Any = None,
        received_at: Any = None,
        source: Any = None,
    ) -> dict[str, Any]:
        return self.emit(
            "probe_sample",
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            received_at=received_at,
            source=source,
            age_s=age_s,
            cache_state=cache_state,
        )


def install_cache_tap(cache: SnapshotCache, log: JsonlEventLog) -> Callable[[MarketSnapshot], None]:
    """Wrap ``SnapshotCache.update`` so each write emits ``book_update``.

    N-7: cache.update always runs; emit failures never abort the feed.
    Returns the wrapped update for tests; restores via ``cache.update = orig``.
    """
    orig = cache.update

    def tapped(snapshot: MarketSnapshot) -> None:
        orig(snapshot)
        try:
            log.emit_book_update(snapshot)
        except Exception:
            # Belt-and-suspenders: emit already swallows OSError; any other
            # escape must not break the book feed.
            log.emit_drop_total += 1

    cache.update = tapped  # type: ignore[method-assign]
    return tapped


def emit_tick_samples(
    cache: SnapshotCache,
    log: JsonlEventLog,
    token_ids: Iterable[str],
    *,
    now: Optional[float] = None,
    max_age_s: Optional[float] = None,
) -> int:
    """Emit one ``tick_sample`` per token from cache.peek (no invented book_update)."""
    n = 0
    wall = now if now is not None else time.time()
    for tid in token_ids:
        peeked = cache.peek(tid) if hasattr(cache, "peek") else cache.get(tid)
        log.emit_tick_sample(tid, peeked, now=wall, max_age_s=max_age_s)
        n += 1
    return n


def iter_events(path: Path) -> list[dict[str, Any]]:
    """Load JSONL events. N-7: torn/corrupt lines are skipped (no raise).

    Increments module ``corrupt_line_total`` per skipped line. Counter is
    observation only — never a Gate verdict (Charter).
    """
    global corrupt_line_total
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            corrupt_line_total += 1
            continue
    return out


def last_event_age_s(
    path: Path,
    token_id: str,
    *,
    producer: str,
    event_type: str = "book_update",
    now: Optional[float] = None,
) -> Optional[float]:
    """Age from last matching event wall_ts — for A-A3 dual-producer columns."""
    wall = now if now is not None else time.time()
    last: Optional[float] = None
    for ev in iter_events(path):
        if ev.get("token_id") != token_id:
            continue
        if ev.get("producer") != producer:
            continue
        if ev.get("event_type") != event_type:
            continue
        last = float(ev["wall_ts"])
    if last is None:
        return None
    return max(0.0, wall - last)


def count_events(
    path: Path,
    *,
    event_type: Optional[str] = None,
    producer: Optional[str] = None,
    token_id: Optional[str] = None,
) -> int:
    n = 0
    for ev in iter_events(path):
        if event_type is not None and ev.get("event_type") != event_type:
            continue
        if producer is not None and ev.get("producer") != producer:
            continue
        if token_id is not None and ev.get("token_id") != token_id:
            continue
        n += 1
    return n


def sha256_file(path: Path) -> str:
    """Hex digest of a segment file (GP-S2-6 provenance)."""
    import hashlib

    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_segment_manifest(
    segment_paths: Iterable[Path],
    manifest_path: Path,
) -> dict[str, str]:
    """Write ``path\\tsha256`` lines for rolled event-log / probe segments."""
    entries: dict[str, str] = {}
    lines: list[str] = []
    for p in segment_paths:
        path = Path(p)
        if not path.exists():
            continue
        digest = sha256_file(path)
        key = str(path)
        entries[key] = digest
        lines.append(f"{digest}  {path.name}")
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return entries
