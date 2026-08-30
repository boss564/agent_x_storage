"""Cross-venue connectivity — t_recv gaps only (Pre-Reg FREIGABE).

docs/CROSS_VENUE_FEED_VALIDATION_PREREG.md
- No prices on audit JSONL (charter invariant)
- 2×2 slot cells NN/LN/NL/LL + onset_skew_s on LL
- H2 priority: INSUFFICIENT → V2_NOISE → COLLAPSED → SEPARABLE → MIXED
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from prototypes.raas_paper_trading.paper_exit import parse_ts_unix

VENUES = frozenset({"v1", "v2"})
GAP_SOURCES = frozenset({"recv_gap", "heartbeat", "restart_marker"})
CELLS = frozenset({"NN", "LN", "NL", "LL"})
FORBIDDEN_KEYS = frozenset(
    {
        "price",
        "bid",
        "ask",
        "mid",
        "deviation",
        "deviation_pct",
        "spread",
        "mark_price",
        "last_price",
    }
)
DEFAULT_GAP_DT_S = 30.0
DEFAULT_SLOT_S = 10.0
DEFAULT_FACTOR_MAX = 1.5
DEFAULT_HEARTBEAT_INTERVAL_S = float(os.environ.get("CROSS_VENUE_HEARTBEAT_S", "3600"))
DEFAULT_HEARTBEAT_STALE_S = float(os.environ.get("CROSS_VENUE_HEARTBEAT_STALE_S", "7200"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cross_venue_paths_from_env() -> Dict[str, Path]:
    root = Path(os.environ.get("RAAS_DATA_ROOT", "data/raas"))
    return {
        "gaps_path": Path(
            os.environ.get(
                "CROSS_VENUE_GAPS_PATH",
                str(root / "audit" / "cross_venue_gaps.jsonl"),
            )
        ),
        "slots_path": Path(
            os.environ.get(
                "CROSS_VENUE_SLOTS_PATH",
                str(root / "audit" / "cross_venue_slots.jsonl"),
            )
        ),
        "state_path": Path(
            os.environ.get(
                "CROSS_VENUE_STATE_PATH",
                str(root / "state" / "cross_venue_state.json"),
            )
        ),
    }


def assert_no_price_fields(row: Dict[str, Any]) -> None:
    leaked = FORBIDDEN_KEYS.intersection(row.keys())
    if leaked:
        raise RuntimeError(f"cross_venue_price_forbidden: {sorted(leaked)}")


def threshold_factor_ok(gap_v1: float, gap_v2: float, *, max_factor: float = DEFAULT_FACTOR_MAX) -> bool:
    lo = min(float(gap_v1), float(gap_v2))
    hi = max(float(gap_v1), float(gap_v2))
    if lo <= 0:
        return False
    return (hi / lo) <= float(max_factor)


class _HashChainLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = "0" * 64
        if self.path.is_file():
            lines = self.path.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                self._prev = str(last.get("hash") or self._prev)

    def append(self, event: Dict[str, Any]) -> Dict[str, Any]:
        source = str(event.get("source") or "recv_gap")
        if source not in GAP_SOURCES:
            raise RuntimeError(f"cross_venue_gaps_invalid_source: {source}")
        assert_no_price_fields(event)
        if event.get("live_execution") is True or event.get("order_send") is True:
            raise RuntimeError("cross_venue: live_execution and order_send must be false")
        row = {
            **event,
            "event_id": event.get("event_id") or str(uuid.uuid4()),
            "ts": event.get("ts") or _now_iso(),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
            "diagnostic_only": True,
            "prev_hash": self._prev,
        }
        assert_no_price_fields(row)
        payload = json.dumps(row, sort_keys=True, default=str)
        digest = hashlib.sha256((self._prev + payload).encode("utf-8")).hexdigest()
        row["hash"] = digest
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._prev = digest
        return row


@dataclass
class CrossVenueState:
    path: Path
    last_recv_ts: Dict[str, Optional[str]] = field(
        default_factory=lambda: {"v1": None, "v2": None}
    )
    last_heartbeat_ts: Dict[str, Optional[str]] = field(
        default_factory=lambda: {"v1": None, "v2": None}
    )
    dual_start_ts: Optional[str] = None

    def load(self) -> None:
        if not self.path.is_file():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        lr = raw.get("last_recv_ts") or {}
        self.last_recv_ts = {
            "v1": lr.get("v1"),
            "v2": lr.get("v2"),
        }
        hb = raw.get("last_heartbeat_ts") or {}
        self.last_heartbeat_ts = {
            "v1": hb.get("v1"),
            "v2": hb.get("v2"),
        }
        self.dual_start_ts = raw.get("dual_start_ts")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_recv_ts": self.last_recv_ts,
            "last_heartbeat_ts": self.last_heartbeat_ts,
            "dual_start_ts": self.dual_start_ts,
            "updated_at": _now_iso(),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


@dataclass
class CrossVenueMonitor:
    """Per-venue t_recv gap detector + open gap tracking for slot paint."""

    gaps_log: _HashChainLog
    slots_log: _HashChainLog
    state: CrossVenueState
    gap_dt_v1: float = DEFAULT_GAP_DT_S
    gap_dt_v2: float = DEFAULT_GAP_DT_S
    slot_s: float = DEFAULT_SLOT_S
    # open gaps: venue -> (start_unix, end_unix) while waiting for next recv after gap start
    _open_gaps: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    _closed_gaps: List[Dict[str, Any]] = field(default_factory=list)
    _slot_cursor_unix: Optional[float] = None
    _last_heartbeat_unix: Dict[str, float] = field(default_factory=dict)
    _wrote_restart_marker: Dict[str, bool] = field(default_factory=dict, repr=False)

    @classmethod
    def from_paths(
        cls,
        *,
        gaps_path: Path,
        slots_path: Path,
        state_path: Path,
        gap_dt_v1: float = DEFAULT_GAP_DT_S,
        gap_dt_v2: float = DEFAULT_GAP_DT_S,
        slot_s: float = DEFAULT_SLOT_S,
        require_factor_ok: bool = True,
        emit_restart_marker: bool = True,
    ) -> "CrossVenueMonitor":
        if require_factor_ok and not threshold_factor_ok(gap_dt_v1, gap_dt_v2):
            raise RuntimeError(
                f"cross_venue_threshold_factor: gap_dt {gap_dt_v1}/{gap_dt_v2} "
                f"exceeds factor {DEFAULT_FACTOR_MAX} — swap V2, do not compensate"
            )
        state = CrossVenueState(path=Path(state_path))
        state.load()
        mon = cls(
            gaps_log=_HashChainLog(Path(gaps_path)),
            slots_log=_HashChainLog(Path(slots_path)),
            state=state,
            gap_dt_v1=float(gap_dt_v1),
            gap_dt_v2=float(gap_dt_v2),
            slot_s=float(slot_s),
        )
        if state.dual_start_ts is None:
            state.dual_start_ts = _now_iso()
            state.save()
        if emit_restart_marker:
            for venue in sorted(VENUES):
                mon.emit_restart_marker(venue)
        mon._seed_heartbeat_clocks()
        return mon

    def emit_restart_marker(self, venue: str) -> Dict[str, Any]:
        if venue not in VENUES:
            raise ValueError(f"invalid venue: {venue}")
        if self._wrote_restart_marker.get(venue):
            return {}
        self._wrote_restart_marker[venue] = True
        now_iso = _now_iso()
        return self.gaps_log.append(
            {
                "source": "restart_marker",
                "venue": venue,
                "gap_start_recv_ts": now_iso,
                "gap_end_recv_ts": None,
                "gap_duration_s": None,
                "gap_dt_threshold_s": self._gap_dt(venue),
                "last_recv_ts": self.state.last_recv_ts.get(venue),
            }
        )

    def _seed_heartbeat_clocks(self) -> None:
        for venue in VENUES:
            raw = self.state.last_heartbeat_ts.get(venue)
            if not raw:
                continue
            try:
                self._last_heartbeat_unix[venue] = parse_ts_unix(str(raw))
            except ValueError:
                continue

    def emit_heartbeat(self, venue: str) -> Dict[str, Any]:
        if venue not in VENUES:
            raise ValueError(f"invalid venue: {venue}")
        now_iso = _now_iso()
        row = self.gaps_log.append(
            {
                "source": "heartbeat",
                "venue": venue,
                "gap_start_recv_ts": now_iso,
                "gap_end_recv_ts": None,
                "gap_duration_s": None,
                "gap_dt_threshold_s": self._gap_dt(venue),
                "last_recv_ts": self.state.last_recv_ts.get(venue),
            }
        )
        self.state.last_heartbeat_ts[venue] = now_iso
        self.state.save()
        self._last_heartbeat_unix[venue] = time.time()
        return row

    def maybe_emit_heartbeat(
        self, venue: str, *, now_unix: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        now = now_unix if now_unix is not None else time.time()
        last = self._last_heartbeat_unix.get(venue, 0.0)
        if last and (now - last) < DEFAULT_HEARTBEAT_INTERVAL_S:
            return None
        return self.emit_heartbeat(venue)

    def maybe_emit_all_heartbeats(self, *, now_unix: Optional[float] = None) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for venue in sorted(VENUES):
            row = self.maybe_emit_heartbeat(venue, now_unix=now_unix)
            if row:
                rows.append(row)
        return rows

    def _gap_dt(self, venue: str) -> float:
        return self.gap_dt_v1 if venue == "v1" else self.gap_dt_v2

    def on_recv(self, venue: str, *, recv_ts: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Record local accept time for venue. Must not pass price."""
        if venue not in VENUES:
            raise ValueError(f"invalid venue: {venue}")
        ts = recv_ts or _now_iso()
        prev = self.state.last_recv_ts.get(venue)
        row: Optional[Dict[str, Any]] = None
        if prev:
            try:
                dt = parse_ts_unix(ts) - parse_ts_unix(prev)
            except ValueError:
                dt = 0.0
            thr = self._gap_dt(venue)
            if dt > thr:
                start_u = parse_ts_unix(prev)
                end_u = parse_ts_unix(ts)
                row = self.gaps_log.append(
                    {
                        "source": "recv_gap",
                        "venue": venue,
                        "gap_start_recv_ts": prev,
                        "gap_end_recv_ts": ts,
                        "gap_duration_s": round(dt, 6),
                        "gap_dt_threshold_s": thr,
                    }
                )
                self._closed_gaps.append(
                    {
                        "venue": venue,
                        "start_u": start_u,
                        "end_u": end_u,
                        "event_id": row["event_id"],
                    }
                )
                self._flush_slots_until(end_u)
        self.state.last_recv_ts[venue] = ts
        self.state.save()
        try:
            self._flush_slots_until(parse_ts_unix(ts))
        except ValueError:
            pass
        return row

    def _flush_slots_until(self, until_u: float) -> None:
        if self._slot_cursor_unix is None:
            self._slot_cursor_unix = (int(until_u // self.slot_s) - 1) * self.slot_s
        while self._slot_cursor_unix + self.slot_s <= until_u:
            self._emit_slot(self._slot_cursor_unix, self._slot_cursor_unix + self.slot_s)
            self._slot_cursor_unix += self.slot_s

    def flush_slots_to_now(self, *, now_ts: Optional[str] = None) -> None:
        now_u = parse_ts_unix(now_ts or _now_iso())
        self._flush_slots_until(now_u)

    def _venue_gap_in_slot(self, venue: str, s0: float, s1: float) -> List[Dict[str, Any]]:
        hits = []
        for g in self._closed_gaps:
            if g["venue"] != venue:
                continue
            if g["start_u"] <= s1 and g["end_u"] >= s0:
                hits.append(g)
        return hits

    def _emit_slot(self, s0: float, s1: float) -> Dict[str, Any]:
        v1 = self._venue_gap_in_slot("v1", s0, s1)
        v2 = self._venue_gap_in_slot("v2", s0, s1)
        has1, has2 = bool(v1), bool(v2)
        if has1 and has2:
            cell = "LL"
        elif has1:
            cell = "LN"
        elif has2:
            cell = "NL"
        else:
            cell = "NN"
        slot_start = datetime.fromtimestamp(s0, tz=timezone.utc).isoformat()
        event: Dict[str, Any] = {
            "slot_start_ts": slot_start,
            "slot_s": self.slot_s,
            "cell": cell,
        }
        if cell == "LL":
            # minimal onset skew among overlapping pairs
            best = None
            for a in v1:
                for b in v2:
                    skew = abs(a["start_u"] - b["start_u"])
                    if best is None or skew < best:
                        best = skew
            event["onset_skew_s"] = round(float(best if best is not None else 0.0), 6)
        return self.slots_log.append(event)


def writer_liveness_status(
    *,
    gaps: Sequence[Dict[str, Any]],
    venue: str,
    heartbeat_stale_s: float = DEFAULT_HEARTBEAT_STALE_S,
) -> Dict[str, Any]:
    """Per-venue writer alive vs defect: heartbeat = quiet; stale = defect."""
    if venue not in VENUES:
        raise ValueError(f"invalid venue: {venue}")
    venue_rows = [g for g in gaps if str(g.get("venue") or "") == venue]
    if not venue_rows:
        return {"status": "MISSING", "mode": "empty", "age_s": None, "venue": venue}

    last_hb: Optional[Dict[str, Any]] = None
    last_any: Optional[Dict[str, Any]] = None
    for r in venue_rows:
        last_any = r
        if str(r.get("source") or "") == "heartbeat":
            last_hb = r

    now = time.time()

    def _age_of(row: Dict[str, Any]) -> Optional[float]:
        raw = row.get("ts") or row.get("gap_start_recv_ts")
        if not raw:
            return None
        try:
            return now - parse_ts_unix(str(raw))
        except ValueError:
            return None

    if last_hb is not None:
        age = _age_of(last_hb)
        if age is not None and age <= heartbeat_stale_s:
            return {
                "status": "ACTIVE",
                "mode": "quiet",
                "age_s": round(age, 3),
                "last_source": "heartbeat",
                "venue": venue,
            }
        if age is not None:
            return {
                "status": "STALE",
                "mode": "heartbeat_stale",
                "age_s": round(age, 3),
                "last_source": "heartbeat",
                "venue": venue,
            }

    if last_any is not None:
        src = str(last_any.get("source") or "recv_gap")
        age = _age_of(last_any)
        if src == "restart_marker" and age is not None and age <= heartbeat_stale_s:
            return {
                "status": "ACTIVE",
                "mode": "restart_only",
                "age_s": round(age, 3),
                "last_source": src,
                "venue": venue,
            }
        if age is not None and age <= DEFAULT_GAP_DT_S * 6:
            return {
                "status": "ACTIVE",
                "mode": "event_driven",
                "age_s": round(age, 3),
                "last_source": src,
                "venue": venue,
            }
        if age is not None:
            return {
                "status": "IDLE",
                "mode": "defect_suspected",
                "age_s": round(age, 3),
                "last_source": src,
                "venue": venue,
            }

    return {"status": "MISSING", "mode": "unknown", "age_s": None, "venue": venue}


def writer_liveness_all(gaps: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {v: writer_liveness_status(gaps=gaps, venue=v) for v in sorted(VENUES)}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _slot_descriptives(
    slots: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, int], List[float], Optional[Dict[str, Any]]]:
    """Shared slot counts; returns (counts, onset_list, ll_error_or_none)."""
    counts = {"NN": 0, "LN": 0, "NL": 0, "LL": 0}
    onset: List[float] = []
    for s in slots:
        cell = str(s.get("cell") or "")
        if cell in counts:
            counts[cell] += 1
        if cell == "LL":
            if "onset_skew_s" not in s or s["onset_skew_s"] is None:
                return counts, onset, {
                    "h0_measurable": False,
                    "h2": "INSUFFICIENT_DISTURBED",
                    "error": "LL_missing_onset_skew_s",
                    "counts": counts,
                }
            onset.append(float(s["onset_skew_s"]))
    return counts, onset, None


def analyze_cross_venue_h2(
    slots: Sequence[Dict[str, Any]],
    *,
    gaps: Optional[Sequence[Dict[str, Any]]] = None,
    min_disturbed: int = 20,
    sync_skew_s: float = 2.0,
) -> Dict[str, Any]:
    """H0 descriptive counts + H2 priority verdict (Pre-Reg §4.1).

    gaps=None → UNVERIFIED / NOT_GATED (no clean H2 verdict without observer JSONL).
    gaps=[] or stale heartbeat → OBSERVER_DOWN before cell-based verdicts.
    """
    counts, onset, ll_err = _slot_descriptives(slots)
    if ll_err is not None:
        ll_err["observer_check"] = "NOT_GATED" if gaps is None else "GATED"
        return ll_err

    n_slots = sum(counts.values())
    n_disturbed = counts["LN"] + counts["NL"] + counts["LL"]
    p_nn = (counts["NN"] / n_slots) if n_slots else None
    h0_slots_ok = n_slots >= 500
    ll_onset_ok = counts["LL"] == 0 or len(onset) == counts["LL"]
    onset_sorted = sorted(onset)
    f_sync = (
        sum(1 for x in onset if x <= sync_skew_s) / len(onset) if onset else None
    )

    base = {
        "n_slots": n_slots,
        "n_disturbed": n_disturbed,
        "counts": counts,
        "p_NN_descriptive": p_nn,
        "onset_skew_median": (
            onset_sorted[len(onset_sorted) // 2] if onset_sorted else None
        ),
        "onset_skew_p90": (
            onset_sorted[int(0.9 * (len(onset_sorted) - 1))] if onset_sorted else None
        ),
        "f_sync": f_sync,
        "h0_slots_ok": h0_slots_ok,
    }

    if gaps is None:
        return {
            **base,
            "h0_measurable": False,
            "h2": "UNVERIFIED",
            "observer_check": "NOT_GATED",
            "observer_down": [],
            "observer_liveness": None,
            "p_LL": None,
            "p_LN": None,
            "p_NL": None,
            "note": (
                "H2 UNVERIFIED: cross_venue_gaps.jsonl required for observer gate. "
                "Pass --gaps to count_cross_venue_h2. "
                "p_NN and counts are descriptive only."
            ),
        }

    observer_liveness = writer_liveness_all(gaps)
    observer_down = [
        v
        for v in sorted(VENUES)
        if str(observer_liveness[v].get("status") or "") not in ("ACTIVE",)
    ]
    observers_ok = not observer_down

    if observer_down:
        h2 = "OBSERVER_DOWN"
        p_ll = p_ln = p_nl = None
    elif n_disturbed < min_disturbed:
        h2 = "INSUFFICIENT_DISTURBED"
        p_ll = p_ln = p_nl = None
    else:
        p_ll = counts["LL"] / n_disturbed
        p_ln = counts["LN"] / n_disturbed
        p_nl = counts["NL"] / n_disturbed
        if p_nl > 0.60:
            h2 = "V2_NOISE"
        elif p_ll > 0.70:
            h2 = "COLLAPSED"
        elif p_ll <= 0.50:
            h2 = "SEPARABLE"
        else:
            h2 = "MIXED"

    return {
        **base,
        "h0_measurable": h0_slots_ok and ll_onset_ok and observers_ok,
        "h2": h2,
        "observer_check": "GATED",
        "observer_down": observer_down,
        "observer_liveness": observer_liveness,
        "p_LL": None if n_disturbed < min_disturbed or observer_down else p_ll,
        "p_LN": None if n_disturbed < min_disturbed or observer_down else p_ln,
        "p_NL": None if n_disturbed < min_disturbed or observer_down else p_nl,
        "note": (
            "p_NN is descriptive only (no H1). "
            "H2 priority: UNVERIFIED (no gaps) → OBSERVER_DOWN → INSUFFICIENT → "
            "V2_NOISE → COLLAPSED → SEPARABLE → MIXED. "
            "Per-venue heartbeat distinguishes quiet (N) from unobserved (U). "
            "No prices in estimand."
        ),
    }
