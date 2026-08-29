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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from prototypes.raas_paper_trading.paper_edge_sample import (
    DEFAULT_FREEZE_K,
    DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    count_eligible,
    edge_sample_eligible,
)
from prototypes.raas_paper_trading.paper_exit import parse_ts_unix

GAP_SOURCES = frozenset({"tick_spacing", "socket", "restart_marker"})
DEFAULT_GAP_DT_S = float(os.environ.get("PAPER_EXIT_GAP_DT_S", "30"))


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

    def load(self) -> None:
        if not self.path.is_file():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.last_tick_ts = raw.get("last_tick_ts")
        self.last_symbol = raw.get("last_symbol")
        self.open_socket_disconnect_ts = raw.get("open_socket_disconnect_ts")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_tick_ts": self.last_tick_ts,
            "last_symbol": self.last_symbol,
            "open_socket_disconnect_ts": self.open_socket_disconnect_ts,
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
        return mon

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


def analyze_concordance(
    *,
    gaps: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    freeze_k: int = DEFAULT_FREEZE_K,
    max_delta_s: float = DEFAULT_HOLD_CLEAN_MAX_DELTA_S,
    window_start_ts: Optional[str] = None,
    window_end_ts: Optional[str] = None,
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

    h0 = bool(gaps) and len(freeze_edges) >= 1
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
