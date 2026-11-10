"""F3 probe identity + heartbeat helpers (Schritt 2 / GP-S2-3/4/5).

Observations live in the event log. Streak is derived as Δwall_ts — never
stored as a baked ``streak_min`` primary field (GP-S2-3).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

MappingLike = Mapping[str, Any]

# Real cadence ≈ INTERVAL_S(300) + max_work(~50) ≈ 351 s.
# Watchdog ≥ 2 × cadence → ≥ 12–13 min (GP-S2-5).
PROBE_WATCHDOG_S = 13 * 60
DEFAULT_INTERVAL_S = 300
DEFAULT_WS_WAIT_S = 50

CYCLE_STATE_NAME = "night_probe.cycle_state.json"
HEARTBEAT_NAME = "night_probe.heartbeat"


def cycle_state_path(log_dir: Path) -> Path:
    return Path(log_dir) / CYCLE_STATE_NAME


def heartbeat_path(log_dir: Path) -> Path:
    return Path(log_dir) / HEARTBEAT_NAME


def load_or_birth_identity(log_dir: Path) -> dict[str, Any]:
    """Return identity for this process birth.

    New process → new ``instance_id``, ``cycle_seq`` starts at 0 (next_cycle → 1).
    Persists under ``logs/`` (never runner DB).
    """
    path = cycle_state_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    born = {
        "instance_id": str(uuid.uuid4()),
        "cycle_seq": 0,
        "pid": pid,
        "born_wall_ts": time.time(),
    }
    if not path.exists():
        path.write_text(json.dumps(born, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return born
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        path.write_text(json.dumps(born, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return born
    # Same PID continuing (e.g. helper re-entry) keeps identity; else birth.
    if int(data.get("pid") or -1) == pid and data.get("instance_id"):
        return data
    path.write_text(json.dumps(born, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return born


def next_cycle(log_dir: Path) -> dict[str, Any]:
    """Increment persisted ``cycle_seq``; return identity for this cycle."""
    path = cycle_state_path(log_dir)
    data = load_or_birth_identity(log_dir)
    data["cycle_seq"] = int(data.get("cycle_seq") or 0) + 1
    data["pid"] = os.getpid()
    data["last_cycle_wall_ts"] = time.time()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def write_heartbeat(
    log_dir: Path,
    *,
    instance_id: str,
    cycle_seq: int,
    pid: Optional[int] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    path = heartbeat_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instance_id": instance_id,
        "cycle_seq": cycle_seq,
        "pid": pid if pid is not None else os.getpid(),
        "wall_ts": time.time(),
        "ts_mono": time.monotonic(),
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def heartbeat_age_s(log_dir: Path, *, now: Optional[float] = None) -> Optional[float]:
    path = heartbeat_path(log_dir)
    if not path.exists():
        return None
    wall = now if now is not None else time.time()
    return max(0.0, wall - path.stat().st_mtime)


def heartbeat_stale(
    log_dir: Path,
    *,
    watchdog_s: float = PROBE_WATCHDOG_S,
    now: Optional[float] = None,
) -> bool:
    age = heartbeat_age_s(log_dir, now=now)
    if age is None:
        return True
    return age > float(watchdog_s)


def detect_cycle_gaps(events: Sequence[MappingLike]) -> list[dict[str, Any]]:
    """Find missing cycle_seq within an instance, or instance switch without cycle_end.

    A-B4: deleting seq=2 must surface as a gap.
    """
    gaps: list[dict[str, Any]] = []
    by_instance: dict[str, list[int]] = {}
    last_instance: Optional[str] = None
    last_had_end = True
    for ev in events:
        et = ev.get("event_type")
        iid = ev.get("instance_id")
        seq = ev.get("cycle_seq")
        if iid is None:
            continue
        if last_instance is not None and iid != last_instance and not last_had_end:
            gaps.append(
                {
                    "kind": "instance_switch_without_cycle_end",
                    "from_instance": last_instance,
                    "to_instance": iid,
                }
            )
        if et == "cycle_start" and seq is not None:
            by_instance.setdefault(str(iid), []).append(int(seq))
            last_had_end = False
        if et == "cycle_end":
            last_had_end = True
        last_instance = str(iid)
    for iid, seqs in by_instance.items():
        uniq = sorted(set(seqs))
        if not uniq:
            continue
        expect = list(range(uniq[0], uniq[-1] + 1))
        missing = [s for s in expect if s not in uniq]
        for m in missing:
            gaps.append({"kind": "missing_cycle_seq", "instance_id": iid, "cycle_seq": m})
    return gaps


def streak_wall_s_from_events(
    events: Iterable[MappingLike],
    *,
    ok_event_types: frozenset[str] = frozenset({"cycle_end"}),
    ok_field: str = "books_ok_full",
) -> Optional[float]:
    """Derive streak as Δwall_ts between first and last consecutive OK observations.

    Returns None if no OK run. Never reads a stored streak_min (GP-S2-3 / A-B2').
    """
    first: Optional[float] = None
    last: Optional[float] = None
    for ev in events:
        if ev.get("event_type") not in ok_event_types:
            continue
        if not ev.get(ok_field):
            # Break streak on explicit non-OK cycle_end.
            if ev.get(ok_field) is False:
                first, last = None, None
            continue
        ts = float(ev["wall_ts"])
        if first is None:
            first = ts
        last = ts
    if first is None or last is None:
        return None
    return max(0.0, last - first)


def report_gap_findings(events: Sequence[MappingLike]) -> dict[str, Any]:
    gaps = detect_cycle_gaps(events)
    return {"gap_count": len(gaps), "gaps": gaps, "ok": len(gaps) == 0}
