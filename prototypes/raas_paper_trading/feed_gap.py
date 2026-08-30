"""Feed-gap audit: tick_spacing + socket sources → append-only feed_gaps.jsonl.

Pre-Reg: docs/PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md
- H_inv: n_hold_delta_exceeded ≤ n_gap_exit_window_hits_tick
- H2: |socket_hits − tick_hits| ≤ 1 (independent layers)
Prometheus counters are ops-only; JSONL is the evaluation source of truth.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from prototypes.raas_paper_trading.paper_edge_sample import (
    DEFAULT_FREEZE_K,
    DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    count_eligible,
    edge_sample_eligible,
)
from prototypes.raas_paper_trading.paper_exit import parse_ts_unix
from prototypes.raas_paper_trading.worm_io import iter_signal_timestamps

GAP_SOURCES = frozenset({"tick_spacing", "socket", "restart_marker", "heartbeat"})
DEFAULT_GAP_DT_S = float(os.environ.get("PAPER_EXIT_GAP_DT_S", "30"))
DEFAULT_HEARTBEAT_INTERVAL_S = float(os.environ.get("PAPER_FEED_GAP_HEARTBEAT_S", "3600"))
DEFAULT_HEARTBEAT_STALE_S = float(os.environ.get("PAPER_FEED_GAP_HEARTBEAT_STALE_S", "7200"))
# Fenster W Dual-Start (Live-Shadow feed-gap-v2); Pre-Reg Provenienz
FEED_GAP_WINDOW_W_DUAL_START_TS = "2026-08-29T13:17:46+00:00"
# Pre-Reg W (72–96 h): min. beobachtbarer Fensteranteil für null_gaps_proven — vor Audit festgelegt
# Amendment FGDC-A1 (2026-08-30); original_pre_reg_hash b1f92b99 sealed doc
MIN_OBSERVABLE_FRACTION = float(
    os.environ.get("PAPER_FEED_GAP_MIN_OBSERVABLE_FRACTION", "0.80")
)
FEED_GAP_AMENDMENT_FGDC_A1 = "FGDC-A1"
FEED_GAP_ORIGINAL_PREREG_HASH = (
    "0b2ea75d2b18e90b52dcaa158fcd5bcead6c36d0d7ff73ba3aafc40401901950"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def feed_gap_paths_from_env() -> Dict[str, Path]:
    root = Path(os.environ.get("RAAS_DATA_ROOT", "data/raas"))
    return {
        "gaps_path": Path(
            os.environ.get(
                "PAPER_FEED_GAPS_PATH",
                str(root / "audit" / "feed_gaps.jsonl"),
            )
        ),
        "state_path": Path(
            os.environ.get(
                "PAPER_FEED_GAP_STATE_PATH",
                str(root / "state" / "feed_gap_state.json"),
            )
        ),
    }


def intervals_overlap(
    a0: float, a1: float, b0: float, b1: float
) -> bool:
    """Closed interval overlap on the real line (order-independent endpoints)."""
    lo_a, hi_a = (a0, a1) if a0 <= a1 else (a1, a0)
    lo_b, hi_b = (b0, b1) if b0 <= b1 else (b1, b0)
    return lo_a <= hi_b and lo_b <= hi_a


# --- Ops-only Prometheus (in-process; resets on restart — not evaluation source) ---

_PROM_LOCK = threading.Lock()
_PROM: Dict[str, float] = {
    "feed_gap_events_total_tick_spacing": 0.0,
    "feed_gap_events_total_socket": 0.0,
    "feed_gap_events_total_restart_marker": 0.0,
    "feed_gap_events_total_heartbeat": 0.0,
    "feed_tick_total": 0.0,
    "feed_last_tick_age_s": 0.0,
}


def reset_feed_gap_prom_metrics() -> None:
    with _PROM_LOCK:
        for k in list(_PROM.keys()):
            _PROM[k] = 0.0


def record_feed_gap_prom(*, source: str, tick: bool = False, last_age_s: Optional[float] = None) -> None:
    with _PROM_LOCK:
        if tick:
            _PROM["feed_tick_total"] += 1.0
        if last_age_s is not None:
            _PROM["feed_last_tick_age_s"] = float(last_age_s)
        key = f"feed_gap_events_total_{source}"
        if key in _PROM and source in GAP_SOURCES:
            _PROM[key] += 1.0


def render_feed_gap_metrics_text() -> str:
    with _PROM_LOCK:
        snap = dict(_PROM)
    lines = [
        "# HELP feed_gap_events_total Feed gap JSONL events by source (ops-only).",
        "# TYPE feed_gap_events_total counter",
        f'feed_gap_events_total{{source="tick_spacing"}} {snap["feed_gap_events_total_tick_spacing"]}',
        f'feed_gap_events_total{{source="socket"}} {snap["feed_gap_events_total_socket"]}',
        f'feed_gap_events_total{{source="restart_marker"}} {snap["feed_gap_events_total_restart_marker"]}',
        f'feed_gap_events_total{{source="heartbeat"}} {snap["feed_gap_events_total_heartbeat"]}',
        "# HELP feed_tick_total Ticks observed by gap detector (ops-only).",
        "# TYPE feed_tick_total counter",
        f"feed_tick_total {snap['feed_tick_total']}",
        "# HELP feed_last_tick_age_s Seconds since previous tick at last observation (ops-only).",
        "# TYPE feed_last_tick_age_s gauge",
        f"feed_last_tick_age_s {snap['feed_last_tick_age_s']}",
        "",
    ]
    return "\n".join(lines)


class FeedGapsLog:
    """Append-only hash-chained gap ledger — primary store for H_inv / H2."""

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
        source = str(event.get("source") or "")
        if source not in GAP_SOURCES:
            raise RuntimeError(f"feed_gaps_invalid_source: {source}")
        if event.get("live_execution") is True or event.get("order_send") is True:
            raise RuntimeError("feed_gaps: live_execution and order_send must be false")

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
        payload = json.dumps(row, sort_keys=True, default=str)
        digest = hashlib.sha256((self._prev + payload).encode("utf-8")).hexdigest()
        row["hash"] = digest
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._prev = digest
        record_feed_gap_prom(source=source)
        return row


@dataclass
class FeedGapStateStore:
    """Persist last_tick_ts across pod restarts (S3)."""

    path: Path
    last_tick_ts: Optional[str] = None
    last_symbol: Optional[str] = None
    open_socket_disconnect_ts: Optional[str] = None
    last_heartbeat_ts: Optional[str] = None

    def load(self) -> None:
        if not self.path.is_file():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.last_tick_ts = raw.get("last_tick_ts")
        self.last_symbol = raw.get("last_symbol")
        self.open_socket_disconnect_ts = raw.get("open_socket_disconnect_ts")
        self.last_heartbeat_ts = raw.get("last_heartbeat_ts")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_tick_ts": self.last_tick_ts,
            "last_symbol": self.last_symbol,
            "open_socket_disconnect_ts": self.open_socket_disconnect_ts,
            "last_heartbeat_ts": self.last_heartbeat_ts,
            "updated_at": _now_iso(),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


@dataclass
class FeedGapMonitor:
    """Tick-spacing detector + socket disconnect/reconnect recorder."""

    log: FeedGapsLog
    state: FeedGapStateStore
    gap_dt_s: float = DEFAULT_GAP_DT_S
    symbol: str = "ETHUSDT"
    _wrote_restart_marker: bool = field(default=False, repr=False)
    _last_heartbeat_unix: float = field(default=0.0, repr=False)

    @classmethod
    def from_paths(
        cls,
        *,
        gaps_path: Path,
        state_path: Path,
        gap_dt_s: float = DEFAULT_GAP_DT_S,
        symbol: str = "ETHUSDT",
        emit_restart_marker: bool = True,
    ) -> "FeedGapMonitor":
        state = FeedGapStateStore(path=Path(state_path))
        state.load()
        mon = cls(
            log=FeedGapsLog(Path(gaps_path)),
            state=state,
            gap_dt_s=float(gap_dt_s),
            symbol=symbol.upper(),
        )
        if emit_restart_marker:
            mon.emit_restart_marker()
        mon._seed_heartbeat_clock()
        return mon

    def _seed_heartbeat_clock(self) -> None:
        if self.state.last_heartbeat_ts:
            try:
                self._last_heartbeat_unix = parse_ts_unix(self.state.last_heartbeat_ts)
            except ValueError:
                self._last_heartbeat_unix = 0.0

    def emit_restart_marker(self) -> Dict[str, Any]:
        if self._wrote_restart_marker:
            return {}
        self._wrote_restart_marker = True
        return self.log.append(
            {
                "source": "restart_marker",
                "symbol": self.symbol,
                "gap_start_ts": _now_iso(),
                "gap_end_ts": None,
                "gap_duration_s": None,
                "gap_dt_threshold_s": self.gap_dt_s,
                "in_exit_window": False,
                "exit_window_start": None,
                "exit_window_end": None,
                "round_trip_id": None,
                "fsm_state": "RESTART",
                "position_open": False,
            }
        )

    def emit_heartbeat(self) -> Dict[str, Any]:
        now_iso = _now_iso()
        row = self.log.append(
            {
                "source": "heartbeat",
                "symbol": self.symbol,
                "gap_start_ts": now_iso,
                "gap_end_ts": None,
                "gap_duration_s": None,
                "gap_dt_threshold_s": self.gap_dt_s,
                "in_exit_window": False,
                "exit_window_start": None,
                "exit_window_end": None,
                "round_trip_id": None,
                "fsm_state": "ALIVE",
                "position_open": False,
                "last_tick_ts": self.state.last_tick_ts,
            }
        )
        self.state.last_heartbeat_ts = now_iso
        self.state.save()
        self._last_heartbeat_unix = time.time()
        return row

    def maybe_emit_heartbeat(self, *, now_unix: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Periodic writer liveness — default hourly (PAPER_FEED_GAP_HEARTBEAT_S)."""
        now = now_unix if now_unix is not None else time.time()
        interval = DEFAULT_HEARTBEAT_INTERVAL_S
        if self._last_heartbeat_unix and (now - self._last_heartbeat_unix) < interval:
            return None
        return self.emit_heartbeat()

    def _window_hint(
        self,
        *,
        hold_deadline_ts: Optional[str],
        exit_tick_ts: Optional[str],
        gap_start_ts: str,
        gap_end_ts: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        if not hold_deadline_ts:
            return False, None, None
        try:
            g0 = parse_ts_unix(gap_start_ts)
            g1 = parse_ts_unix(gap_end_ts)
            d0 = parse_ts_unix(hold_deadline_ts)
            d1 = parse_ts_unix(exit_tick_ts) if exit_tick_ts else g1
        except ValueError:
            return False, hold_deadline_ts, exit_tick_ts
        hit = intervals_overlap(g0, g1, d0, d1)
        return hit, hold_deadline_ts, exit_tick_ts

    def on_tick(
        self,
        *,
        tick_ts: str,
        symbol: Optional[str] = None,
        fsm_state: str = "IDLE",
        position_open: bool = False,
        hold_deadline_ts: Optional[str] = None,
        exit_tick_ts: Optional[str] = None,
        round_trip_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sym = (symbol or self.symbol).upper()
        self.symbol = sym
        row: Optional[Dict[str, Any]] = None
        prev = self.state.last_tick_ts
        dt: Optional[float] = None
        if prev:
            try:
                dt = parse_ts_unix(tick_ts) - parse_ts_unix(prev)
            except ValueError:
                dt = 0.0
            if dt > self.gap_dt_s:
                in_win, w0, w1 = self._window_hint(
                    hold_deadline_ts=hold_deadline_ts,
                    exit_tick_ts=exit_tick_ts,
                    gap_start_ts=prev,
                    gap_end_ts=tick_ts,
                )
                row = self.log.append(
                    {
                        "source": "tick_spacing",
                        "symbol": sym,
                        "gap_start_ts": prev,
                        "gap_end_ts": tick_ts,
                        "gap_duration_s": round(dt, 6),
                        "gap_dt_threshold_s": self.gap_dt_s,
                        "in_exit_window": in_win,
                        "exit_window_start": w0,
                        "exit_window_end": w1,
                        "round_trip_id": round_trip_id,
                        "fsm_state": fsm_state,
                        "position_open": bool(position_open),
                    }
                )
        record_feed_gap_prom(source="", tick=True, last_age_s=dt)

        self.state.last_tick_ts = tick_ts
        self.state.last_symbol = sym
        self.state.save()
        return row

    def on_socket_disconnect(self, *, ts: Optional[str] = None, fsm_state: str = "UNKNOWN") -> None:
        """Record disconnect start; gap closed on reconnect."""
        self.state.open_socket_disconnect_ts = ts or _now_iso()
        self.state.save()

    def on_socket_reconnect(
        self,
        *,
        ts: Optional[str] = None,
        fsm_state: str = "UNKNOWN",
        position_open: bool = False,
        hold_deadline_ts: Optional[str] = None,
        exit_tick_ts: Optional[str] = None,
        round_trip_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        end = ts or _now_iso()
        start = self.state.open_socket_disconnect_ts
        self.state.open_socket_disconnect_ts = None
        self.state.save()
        if not start:
            return None
        try:
            dt = parse_ts_unix(end) - parse_ts_unix(start)
        except ValueError:
            dt = 0.0
        # Socket events are recorded even if dt ≤ gap_dt (layer independence);
        # exit-window hit still uses overlap geometry. Ops may filter by duration.
        in_win, w0, w1 = self._window_hint(
            hold_deadline_ts=hold_deadline_ts,
            exit_tick_ts=exit_tick_ts,
            gap_start_ts=start,
            gap_end_ts=end,
        )
        return self.log.append(
            {
                "source": "socket",
                "symbol": self.symbol,
                "gap_start_ts": start,
                "gap_end_ts": end,
                "gap_duration_s": round(dt, 6),
                "gap_dt_threshold_s": self.gap_dt_s,
                "in_exit_window": in_win,
                "exit_window_start": w0,
                "exit_window_end": w1,
                "round_trip_id": round_trip_id,
                "fsm_state": fsm_state,
                "position_open": bool(position_open),
            }
        )


def load_gaps(path: Path) -> List[Dict[str, Any]]:
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


def reconstruct_worm_tick_spacings(
    worm_path: Path,
    *,
    gap_dt_s: float = DEFAULT_GAP_DT_S,
    window_start_ts: Optional[str] = None,
    window_end_ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Reconstruct inter-SIGNAL Δt from WORM (retrospective null-gap / writer audit)."""
    spacings: List[Dict[str, Any]] = []
    prev_ts: Optional[str] = None
    prev_u: Optional[float] = None
    for iso_ts, u in iter_signal_timestamps(
        worm_path,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
    ):
        if prev_ts is not None and prev_u is not None:
            dt = u - prev_u
            spacings.append(
                {
                    "gap_start_ts": prev_ts,
                    "gap_end_ts": iso_ts,
                    "gap_duration_s": round(dt, 6),
                    "over_threshold": dt > float(gap_dt_s),
                }
            )
        prev_ts, prev_u = iso_ts, u
    return spacings


def _restart_marker_times(
    gaps: Sequence[Dict[str, Any]],
    window_filter: Any,
) -> List[float]:
    times: List[float] = []
    for g in gaps:
        if str(g.get("source") or "") != "restart_marker":
            continue
        if not window_filter(g):
            continue
        raw = g.get("gap_start_ts") or g.get("ts")
        if not raw:
            continue
        try:
            times.append(parse_ts_unix(str(raw)))
        except ValueError:
            continue
    return sorted(times)


def _spacing_spans_restart(
    spacing: Dict[str, Any],
    restart_times: Sequence[float],
) -> bool:
    if not restart_times:
        return False
    try:
        w0 = parse_ts_unix(str(spacing["gap_start_ts"]))
        w1 = parse_ts_unix(str(spacing["gap_end_ts"]))
    except (KeyError, ValueError):
        return False
    return any(w0 <= r <= w1 for r in restart_times)


def _merge_intervals(intervals: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    merged: List[Tuple[float, float]] = [sorted_iv[0]]
    for a, b in sorted_iv[1:]:
        la, lb = merged[-1]
        if a <= lb:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def _intervals_total_s(intervals: Sequence[Tuple[float, float]]) -> float:
    return sum(b - a for a, b in intervals)


def _clip_intervals_to_window(
    intervals: Sequence[Tuple[float, float]],
    w0: float,
    w1: float,
) -> List[Tuple[float, float]]:
    clipped: List[Tuple[float, float]] = []
    for a, b in intervals:
        ca, cb = max(a, w0), min(b, w1)
        if cb > ca:
            clipped.append((ca, cb))
    return _merge_intervals(clipped)


def _tick_spacing_covers(
    written: Sequence[Dict[str, Any]],
    worm_gap: Dict[str, Any],
    *,
    slack_s: float = 1.0,
) -> bool:
    try:
        w0 = parse_ts_unix(str(worm_gap["gap_start_ts"]))
        w1 = parse_ts_unix(str(worm_gap["gap_end_ts"]))
    except (KeyError, ValueError):
        return False
    for g in written:
        if str(g.get("source") or "") != "tick_spacing":
            continue
        try:
            g0 = parse_ts_unix(str(g["gap_start_ts"])) - slack_s
            g1 = parse_ts_unix(str(g["gap_end_ts"])) + slack_s
        except (KeyError, ValueError):
            continue
        if g0 <= w0 and g1 >= w1:
            return True
    return False


def audit_gap_writer_against_worm(
    *,
    gaps: Sequence[Dict[str, Any]],
    worm_path: Path,
    gap_dt_s: float = DEFAULT_GAP_DT_S,
    window_start_ts: Optional[str] = None,
    window_end_ts: Optional[str] = None,
) -> Dict[str, Any]:
    """W-Studie: Null-Lücken aus WORM belegen oder Schreiber-Versagen vor Ergebnisdok.

    Drei Kategorien für WORM-Δt > gap_dt:
      - tick_spacing deckt ab → beobachtet, sauber
      - restart_marker im Intervall → unbeobachtbar (Pod down)
      - sonst → writer_failed
    """
    spacings = reconstruct_worm_tick_spacings(
        worm_path,
        gap_dt_s=gap_dt_s,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
    )
    max_spacing = max((float(s["gap_duration_s"]) for s in spacings), default=0.0)

    def _gap_in_w(g: Dict[str, Any]) -> bool:
        ts = g.get("ts") or g.get("gap_start_ts")
        if not ts or (window_start_ts is None and window_end_ts is None):
            return True
        try:
            u = parse_ts_unix(str(ts))
            if window_start_ts and u < parse_ts_unix(window_start_ts):
                return False
            if window_end_ts and u > parse_ts_unix(window_end_ts):
                return False
        except ValueError:
            return False
        return True

    restart_times = _restart_marker_times(gaps, _gap_in_w)
    unobservable = [s for s in spacings if _spacing_spans_restart(s, restart_times)]
    observable = [s for s in spacings if not _spacing_spans_restart(s, restart_times)]
    observable_over = [s for s in observable if s.get("over_threshold")]
    over = [s for s in spacings if s.get("over_threshold")]

    tick_written = [g for g in gaps if str(g.get("source") or "") == "tick_spacing" and _gap_in_w(g)]
    unmatched = [wg for wg in observable_over if not _tick_spacing_covers(tick_written, wg)]

    writer_failed = len(unmatched) > 0

    window_total_s = 0.0
    w0_u: Optional[float] = None
    w1_u: Optional[float] = None
    if window_start_ts and window_end_ts:
        try:
            w0_u = parse_ts_unix(window_start_ts)
            w1_u = parse_ts_unix(window_end_ts)
            window_total_s = max(0.0, w1_u - w0_u)
        except ValueError:
            pass
    elif spacings:
        try:
            w0_u = parse_ts_unix(str(spacings[0]["gap_start_ts"]))
            w1_u = parse_ts_unix(str(spacings[-1]["gap_end_ts"]))
            window_total_s = max(0.0, w1_u - w0_u)
        except (KeyError, ValueError):
            pass

    unobs_iv: List[Tuple[float, float]] = []
    for s in unobservable:
        try:
            unobs_iv.append(
                (parse_ts_unix(str(s["gap_start_ts"])), parse_ts_unix(str(s["gap_end_ts"])))
            )
        except (KeyError, ValueError):
            continue
    merged_unobs = _merge_intervals(unobs_iv)
    if w0_u is not None and w1_u is not None:
        merged_unobs = _clip_intervals_to_window(merged_unobs, w0_u, w1_u)
    unobservable_s = _intervals_total_s(merged_unobs)
    observable_s = max(0.0, window_total_s - unobservable_s) if window_total_s > 0 else 0.0

    coverage_frac = observable_s / window_total_s if window_total_s > 0 else 0.0
    insufficient_coverage = window_total_s > 0 and coverage_frac < MIN_OBSERVABLE_FRACTION
    null_gaps_proven = (
        coverage_frac >= MIN_OBSERVABLE_FRACTION
        and len(observable_over) == 0
        and not writer_failed
    )

    window_h = round(window_total_s / 3600.0, 4)
    observable_h = round(observable_s / 3600.0, 4)
    unobservable_h = round(unobservable_s / 3600.0, 4)
    coverage_pct = round(coverage_frac * 100.0, 2)
    min_pct = round(MIN_OBSERVABLE_FRACTION * 100.0, 2)
    if writer_failed:
        coverage_summary = (
            f"Schreiber-Versagen; beobachtbar {observable_h} von {window_h} h "
            f"({coverage_pct}%, Schwelle {min_pct}%)"
        )
    elif insufficient_coverage:
        coverage_summary = (
            f"INSUFFICIENT_COVERAGE: beobachtbar {observable_h} von {window_h} h "
            f"({coverage_pct}%, Schwelle {min_pct}%)"
        )
    elif null_gaps_proven:
        coverage_summary = (
            f"Null-Lücken belegt über {observable_h} von {window_h} h "
            f"({coverage_pct}%), {unobservable_h} h unbeobachtbar"
        )
    else:
        coverage_summary = (
            f"Null-Lücken nicht belegt; beobachtbar {observable_h} von {window_h} h "
            f"({coverage_pct}%), {unobservable_h} h unbeobachtbar"
        )

    liveness = writer_liveness_status(gaps_path=None, gaps=gaps, window_filter=_gap_in_w)

    return {
        "null_gaps_proven": null_gaps_proven,
        "insufficient_coverage": insufficient_coverage,
        "writer_failed": writer_failed,
        "n_worm_signal_spacings": len(spacings),
        "n_observable_spacings": len(observable),
        "n_unobservable_spacings": len(unobservable),
        "n_worm_gaps_over_threshold": len(over),
        "n_observable_over_threshold": len(observable_over),
        "n_unmatched_worm_gaps": len(unmatched),
        "max_spacing_s": round(max_spacing, 6),
        "unmatched_worm_gaps": unmatched[:20],
        "unobservable_spacings": unobservable[:20],
        "window_start_ts": window_start_ts,
        "window_end_ts": window_end_ts,
        "window_total_hours": window_h,
        "observable_hours": observable_h,
        "unobservable_hours": unobservable_h,
        "coverage_fraction": round(coverage_frac, 6),
        "min_observable_fraction": MIN_OBSERVABLE_FRACTION,
        "coverage_summary": coverage_summary,
        "dual_start_default_ts": FEED_GAP_WINDOW_W_DUAL_START_TS,
        "amendment_id": FEED_GAP_AMENDMENT_FGDC_A1,
        "original_pre_reg_hash": FEED_GAP_ORIGINAL_PREREG_HASH,
        "writer_liveness": liveness,
        "gap_dt_threshold_s": float(gap_dt_s),
        "n_restart_markers": len(restart_times),
    }


def writer_liveness_status(
    *,
    gaps_path: Optional[Path] = None,
    gaps: Optional[Sequence[Dict[str, Any]]] = None,
    heartbeat_stale_s: float = DEFAULT_HEARTBEAT_STALE_S,
    window_filter: Optional[Any] = None,
) -> Dict[str, Any]:
    """Writer alive vs defect: heartbeat = quiet; no heartbeat + stale = defect."""
    rows: List[Dict[str, Any]]
    if gaps is not None:
        rows = list(gaps)
    elif gaps_path is not None:
        rows = load_gaps(gaps_path)
    else:
        return {"status": "MISSING", "mode": "no_path", "age_s": None}

    if window_filter is not None:
        rows = [r for r in rows if window_filter(r)]

    if not rows:
        return {"status": "MISSING", "mode": "empty", "age_s": None}

    last_hb: Optional[Dict[str, Any]] = None
    last_any: Optional[Dict[str, Any]] = None
    for r in rows:
        last_any = r
        if str(r.get("source") or "") == "heartbeat":
            last_hb = r

    now = time.time()

    def _age_of(row: Dict[str, Any]) -> Optional[float]:
        raw = row.get("ts") or row.get("gap_start_ts")
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
            }
        if age is not None:
            return {
                "status": "STALE",
                "mode": "heartbeat_stale",
                "age_s": round(age, 3),
                "last_source": "heartbeat",
            }

    if last_any is not None:
        src = str(last_any.get("source") or "")
        age = _age_of(last_any)
        if src == "restart_marker" and age is not None and age <= heartbeat_stale_s:
            return {
                "status": "ACTIVE",
                "mode": "restart_only",
                "age_s": round(age, 3),
                "last_source": src,
            }
        if age is not None and age <= DEFAULT_GAP_DT_S * 6:
            return {
                "status": "ACTIVE",
                "mode": "event_driven",
                "age_s": round(age, 3),
                "last_source": src,
            }
        if age is not None:
            return {
                "status": "IDLE",
                "mode": "defect_suspected",
                "age_s": round(age, 3),
                "last_source": src,
            }

    return {"status": "MISSING", "mode": "unknown", "age_s": None}


def analyze_concordance(
    *,
    gaps: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    freeze_k: int = DEFAULT_FREEZE_K,
    max_delta_s: float = DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    window_start_ts: Optional[str] = None,
    window_end_ts: Optional[str] = None,
    worm_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate H0 / H1 / H_inv / H2 from JSONL only (Pre-Reg §3)."""

    def _in_w(ts: Optional[str]) -> bool:
        if not ts:
            return True
        if window_start_ts is None and window_end_ts is None:
            return True
        try:
            u = parse_ts_unix(ts)
            if window_start_ts and u < parse_ts_unix(window_start_ts):
                return False
            if window_end_ts and u > parse_ts_unix(window_end_ts):
                return False
        except ValueError:
            return False
        return True

    freeze_edges = []
    for e in edges:
        try:
            if int(e.get("hold_seconds_target")) != int(freeze_k):
                continue
        except (TypeError, ValueError):
            continue
        if str(e.get("exit_reason") or "") != "hold_expired":
            continue
        exit_ts = e.get("exit_tick_ts") or e.get("ts")
        if not _in_w(str(exit_ts) if exit_ts else None):
            continue
        freeze_edges.append(e)

    n_delta = 0
    for e in freeze_edges:
        ok, code = edge_sample_eligible(e, freeze_k=freeze_k, max_delta_s=max_delta_s)
        if not ok and code == "hold_delta_exceeded":
            n_delta += 1

    rts: List[Tuple[str, float, float]] = []
    for e in freeze_edges:
        try:
            entry = str(e["entry_tick_ts"])
            exit_ts = str(e["exit_tick_ts"])
            target = int(e["hold_seconds_target"])
            entry_u = parse_ts_unix(entry)
            exit_u = parse_ts_unix(exit_ts)
            deadline = entry_u + float(target)
        except (KeyError, TypeError, ValueError):
            continue
        if exit_u < deadline:
            continue
        key = str(e.get("edge_id") or f"{entry}|{exit_ts}")
        rts.append((key, deadline, exit_u))

    def _hits(source: str) -> Tuple[int, List[str]]:
        hit_keys = set()
        for g in gaps:
            if str(g.get("source") or "") != source:
                continue
            gs, ge = g.get("gap_start_ts"), g.get("gap_end_ts")
            if not gs or not ge:
                continue
            if not _in_w(str(ge)):
                continue
            try:
                g0 = parse_ts_unix(str(gs))
                g1 = parse_ts_unix(str(ge))
            except ValueError:
                continue
            for key, d0, d1 in rts:
                if intervals_overlap(g0, g1, d0, d1):
                    hit_keys.add(key)
        return len(hit_keys), sorted(hit_keys)

    n_tick, tick_ids = _hits("tick_spacing")
    n_sock, sock_ids = _hits("socket")

    sample = count_eligible(freeze_edges, freeze_k=freeze_k, max_delta_s=max_delta_s)

    null_gaps_proven = bool(worm_audit and worm_audit.get("null_gaps_proven"))
    worm_insufficient = bool(worm_audit and worm_audit.get("insufficient_coverage"))
    has_gap_jsonl = bool(gaps)
    h0 = len(freeze_edges) >= 1 and (has_gap_jsonl or null_gaps_proven)
    if len(freeze_edges) < 1:
        h0_branch = "none"
    elif has_gap_jsonl:
        h0_branch = "gap_jsonl"
    elif null_gaps_proven:
        h0_branch = "worm_null_gaps"
    elif worm_insufficient:
        h0_branch = "insufficient_coverage"
    else:
        h0_branch = "none"
    if n_delta >= 1:
        h1 = "CONFIRMED"
    elif sample["n_edges_total"] >= 20:
        h1 = "NOT_CONFIRMED"
    else:
        h1 = "INCONCLUSIVE"

    h_inv = "HOLD" if n_delta <= n_tick else "BROKEN"
    delta_conc = abs(n_sock - n_tick)
    h2 = "CONCORDANT" if delta_conc <= 1 else "DISCORDANT"

    return {
        "h0_measurable": h0,
        "h0_branch": h0_branch,
        "null_gaps_proven": null_gaps_proven,
        "worm_insufficient_coverage": worm_insufficient,
        "worm_writer_failed": bool(worm_audit and worm_audit.get("writer_failed")),
        "worm_audit": worm_audit,
        "h1": h1,
        "h_inv": h_inv,
        "h2": h2,
        "n_hold_delta_exceeded": n_delta,
        "n_gap_exit_window_hits_tick": n_tick,
        "n_gap_exit_window_hits_socket": n_sock,
        "delta_conc": delta_conc,
        "n_freeze_k_edges": len(freeze_edges),
        "n_gaps_total_tick_spacing": sum(
            1 for g in gaps if g.get("source") == "tick_spacing"
        ),
        "n_gaps_total_socket": sum(1 for g in gaps if g.get("source") == "socket"),
        "tick_hit_edge_ids": tick_ids,
        "socket_hit_edge_ids": sock_ids,
        "freeze_k": int(freeze_k),
        "max_delta_s": float(max_delta_s),
        "note": (
            "H_inv is one-sided (delta ≤ tick hits). "
            "H2 compares socket vs tick layers (±1). "
            "Prometheus is not used."
        ),
    }
