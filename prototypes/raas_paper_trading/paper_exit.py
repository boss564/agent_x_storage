"""Option-B paper exit: fixed hold timer + single-position state machine.

Pre-Reg: docs/PAPER_EXIT_IMPLEMENTATION_PREREG.md (I1–I6, B1–B4, S1–S5).
Charter: live_execution=false · order_send=false · not_investment_advice=true.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from prototypes.raas_paper_trading.ledger import PaperLedger

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
EXIT_REASONS = frozenset({"hold_expired", "force_exit"})
FORBIDDEN_PAPER_KEYS = frozenset(
    {
        "kelly_fraction_computed",
        "advisory_position_size",
        "kelly_fraction",
        "position_size_advisory",
    }
)


class PositionState(str, Enum):
    IDLE = "IDLE"
    ENTRY_PENDING = "ENTRY_PENDING"
    HOLDING = "HOLDING"
    EXIT_PENDING = "EXIT_PENDING"


class ExitAction(str, Enum):
    NONE = "none"
    ENTER = "enter"
    EXIT = "exit"
    BLOCKED = "blocked"
    ALARM = "alarm"


@dataclass
class TickDecision:
    action: ExitAction
    log_code: Optional[str] = None
    exit_reason: Optional[str] = None
    gap_ok: bool = True
    hold_elapsed_s: Optional[float] = None
    state: str = PositionState.IDLE.value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts_unix(ts: str) -> float:
    """Parse ISO-8601 (with Z or offset) to Unix seconds (UTC)."""
    raw = (ts or "").strip()
    if not raw:
        raise ValueError("empty timestamp")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def human_force_exit_requested(*, flag: Optional[bool] = None) -> bool:
    """S5: only Env/API HUMAN_FORCE_EXIT — never Regime/A7."""
    if flag is True:
        return True
    raw = os.environ.get("HUMAN_FORCE_EXIT", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def exit_config_from_env() -> Dict[str, Any]:
    root = Path(os.environ.get("RAAS_DATA_ROOT", "data/raas"))
    return {
        "exit_mode": os.environ.get("PAPER_EXIT_MODE", "time_hold").strip().lower(),
        "hold_seconds": int(os.environ.get("PAPER_HOLD_SECONDS", "433")),
        "gap_dt_s": float(os.environ.get("PAPER_EXIT_GAP_DT_S", "30")),
        "max_wait_s": float(os.environ.get("PAPER_EXIT_MAX_WAIT_S", "2165")),
        # Cluster: set PAPER_*_PATH=/data/... ; local default under RAAS_DATA_ROOT
        "state_path": Path(
            os.environ.get(
                "PAPER_POSITION_STATE_PATH",
                str(root / "state" / "paper_position.json"),
            )
        ),
        "edges_path": Path(
            os.environ.get(
                "PAPER_EDGES_PATH",
                str(root / "audit" / "paper_edges.jsonl"),
            )
        ),
    }


@dataclass
class PaperPositionStore:
    """B4 — persist IDLE/ENTRY_PENDING/HOLDING/EXIT_PENDING across restarts."""

    path: Path
    hold_seconds_target: int = 433
    state: str = PositionState.IDLE.value
    entry_tick_ts: Optional[str] = None
    entry_price: Optional[str] = None
    entry_signal_id: Optional[str] = None
    symbol: Optional[str] = None
    exit_pending_since: Optional[str] = None
    updated_at: Optional[str] = None
    _dirty: bool = field(default=False, repr=False)

    def load(self) -> None:
        if not self.path.is_file():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        st = str(raw.get("state") or PositionState.IDLE.value)
        if st == "EXITED":
            st = PositionState.IDLE.value
        self.state = st
        self.entry_tick_ts = raw.get("entry_tick_ts")
        self.entry_price = raw.get("entry_price")
        self.entry_signal_id = raw.get("entry_signal_id")
        self.symbol = raw.get("symbol")
        self.exit_pending_since = raw.get("exit_pending_since")
        self.hold_seconds_target = int(
            raw.get("hold_seconds_target") or self.hold_seconds_target
        )
        self.updated_at = raw.get("updated_at")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "state": self.state,
            "entry_tick_ts": self.entry_tick_ts,
            "entry_price": self.entry_price,
            "entry_signal_id": self.entry_signal_id,
            "hold_seconds_target": self.hold_seconds_target,
            "symbol": self.symbol,
            "exit_pending_since": self.exit_pending_since,
            "updated_at": _now_iso(),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        self.updated_at = payload["updated_at"]

    def set_idle(self) -> None:
        self.state = PositionState.IDLE.value
        self.entry_tick_ts = None
        self.entry_price = None
        self.entry_signal_id = None
        self.symbol = None
        self.exit_pending_since = None
        self.save()

    def set_holding(
        self,
        *,
        entry_tick_ts: str,
        entry_price: str,
        entry_signal_id: str,
        symbol: str,
    ) -> None:
        self.state = PositionState.HOLDING.value
        self.entry_tick_ts = entry_tick_ts
        self.entry_price = entry_price
        self.entry_signal_id = entry_signal_id
        self.symbol = symbol
        self.exit_pending_since = None
        self.save()

    def set_exit_pending(self, *, since_ts: str) -> None:
        self.state = PositionState.EXIT_PENDING.value
        if not self.exit_pending_since:
            self.exit_pending_since = since_ts
        self.save()


class PaperEdgesLog:
    """I5 — append-only hash-chained edge ledger (1:1 to SELL WORM row)."""

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
        leaked = FORBIDDEN_PAPER_KEYS.intersection(event.keys())
        if leaked:
            raise RuntimeError(f"paper_edges_forbidden_keys: {sorted(leaked)}")
        if event.get("exit_reason") not in EXIT_REASONS:
            raise RuntimeError(f"paper_edges_invalid_exit_reason: {event.get('exit_reason')}")
        if event.get("live_execution") is True or event.get("order_send") is True:
            raise RuntimeError("paper_edges: live_execution and order_send must be false")

        row = {
            **event,
            "edge_id": event.get("edge_id") or str(uuid.uuid4()),
            "ts": event.get("ts") or _now_iso(),
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
            "diagnostic_only": True,
            "scope": SCOPE,
            "prev_hash": self._prev,
        }
        payload = json.dumps(row, sort_keys=True, default=str)
        digest = hashlib.sha256((self._prev + payload).encode("utf-8")).hexdigest()
        row["hash"] = digest
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._prev = digest
        return row


@dataclass
class PaperExitController:
    """I1–I6 state machine for time_hold paper exits."""

    store: PaperPositionStore
    edges: PaperEdgesLog
    hold_seconds: int = 433
    gap_dt_s: float = 30.0
    max_wait_s: float = 2165.0
    _prev_tick_ts: Optional[str] = None
    _alarms: List[str] = field(default_factory=list)
    _logs: List[str] = field(default_factory=list)

    @classmethod
    def from_paths(
        cls,
        *,
        state_path: Path,
        edges_path: Path,
        hold_seconds: int = 433,
        gap_dt_s: float = 30.0,
        max_wait_s: float = 2165.0,
    ) -> "PaperExitController":
        store = PaperPositionStore(path=Path(state_path), hold_seconds_target=hold_seconds)
        store.load()
        return cls(
            store=store,
            edges=PaperEdgesLog(Path(edges_path)),
            hold_seconds=hold_seconds,
            gap_dt_s=gap_dt_s,
            max_wait_s=max_wait_s,
        )

    @property
    def state(self) -> str:
        return self.store.state

    @property
    def alarms(self) -> List[str]:
        return list(self._alarms)

    def persist_for_shutdown(self) -> None:
        """E3/E4 — persist open state; do not close."""
        if self.store.state in (
            PositionState.HOLDING.value,
            PositionState.EXIT_PENDING.value,
            PositionState.ENTRY_PENDING.value,
        ):
            self.store.save()

    def seed_ledger_if_needed(
        self,
        ledger: "PaperLedger",
        *,
        shadow_notional_eur: Decimal,
    ) -> bool:
        """E7 — restore open qty after restart without a second BUY WORM line."""
        if self.store.state not in (
            PositionState.HOLDING.value,
            PositionState.EXIT_PENDING.value,
        ):
            return False
        if ledger.position_qty > 0:
            return False
        if not self.store.entry_price:
            return False
        entry = Decimal(str(self.store.entry_price))
        if entry <= 0:
            return False
        qty = (Decimal(str(shadow_notional_eur)) / entry).quantize(Decimal("0.0001"))
        # Reconstruct inventory without fee double-count: set fields directly.
        ledger.position_qty = qty
        ledger.avg_entry = entry
        return True

    def _gap_ok(self, tick_ts: str) -> bool:
        if self._prev_tick_ts is None:
            return True
        try:
            dt = parse_ts_unix(tick_ts) - parse_ts_unix(self._prev_tick_ts)
        except ValueError:
            return False
        return dt <= self.gap_dt_s

    def _hold_elapsed(self, tick_ts: str) -> Optional[float]:
        if not self.store.entry_tick_ts:
            return None
        return parse_ts_unix(tick_ts) - parse_ts_unix(self.store.entry_tick_ts)

    def decide(
        self,
        *,
        tick_ts: str,
        mark_price: float,
        signal_id: str,
        symbol: str,
        position_open: bool,
        force_exit: bool = False,
    ) -> TickDecision:
        """Decide enter/exit/block for one tick (does not mutate until apply_*)."""
        gap_ok = self._gap_ok(tick_ts)
        st = self.store.state
        force = human_force_exit_requested(flag=force_exit)

        # Reconstruct consistency: ledger open but store IDLE → treat as HOLDING if entry known
        if position_open and st == PositionState.IDLE.value and self.store.entry_tick_ts:
            st = PositionState.HOLDING.value
            self.store.state = st

        if st == PositionState.IDLE.value:
            if position_open:
                # Unpaired open qty without state — block new entry; wait for force or manual fix
                self._logs.append("SIGNAL_IGNORED_POSITION_OPEN")
                return TickDecision(
                    action=ExitAction.BLOCKED,
                    log_code="SIGNAL_IGNORED_POSITION_OPEN",
                    gap_ok=gap_ok,
                    state=st,
                )
            if not gap_ok:
                return TickDecision(
                    action=ExitAction.NONE,
                    log_code="ENTRY_WAIT_GAP",
                    gap_ok=False,
                    state=st,
                )
            return TickDecision(
                action=ExitAction.ENTER,
                log_code="IDLE_FIRST_TICK_BUY",
                gap_ok=True,
                state=st,
            )

        if st in (PositionState.HOLDING.value, PositionState.EXIT_PENDING.value):
            # I1 — block further entries
            elapsed = self._hold_elapsed(tick_ts)
            if force and position_open:
                return TickDecision(
                    action=ExitAction.EXIT,
                    log_code="HUMAN_FORCE_EXIT",
                    exit_reason="force_exit",
                    gap_ok=gap_ok,
                    hold_elapsed_s=elapsed,
                    state=st,
                )

            if st == PositionState.HOLDING.value:
                if elapsed is not None and elapsed >= self.hold_seconds:
                    # Transition intent to EXIT_PENDING (caller applies)
                    return TickDecision(
                        action=ExitAction.NONE,
                        log_code="HOLD_EXPIRED_PENDING",
                        gap_ok=gap_ok,
                        hold_elapsed_s=elapsed,
                        state=PositionState.EXIT_PENDING.value,
                    )
                self._logs.append("SIGNAL_IGNORED_POSITION_OPEN")
                return TickDecision(
                    action=ExitAction.BLOCKED,
                    log_code="SIGNAL_IGNORED_POSITION_OPEN",
                    gap_ok=gap_ok,
                    hold_elapsed_s=elapsed,
                    state=st,
                )

            # EXIT_PENDING — max-wait is alarm-only; still exit on next valid tick (S1/S3b)
            timed_out = False
            if self.store.entry_tick_ts:
                since_expiry = (
                    parse_ts_unix(tick_ts)
                    - parse_ts_unix(self.store.entry_tick_ts)
                    - self.hold_seconds
                )
                if since_expiry > self.max_wait_s:
                    timed_out = True
                    code = "EXIT_WAIT_TIMEOUT"
                    if code not in self._alarms:
                        self._alarms.append(code)

            if not gap_ok:
                self._logs.append("SIGNAL_IGNORED_EXIT_PENDING")
                return TickDecision(
                    action=ExitAction.ALARM if timed_out else ExitAction.BLOCKED,
                    log_code="EXIT_WAIT_TIMEOUT" if timed_out else "EXIT_WAIT_GAP",
                    gap_ok=False,
                    hold_elapsed_s=elapsed,
                    state=st,
                )
            if position_open:
                return TickDecision(
                    action=ExitAction.EXIT,
                    log_code="HOLD_EXPIRED_EXIT",
                    exit_reason="hold_expired",
                    gap_ok=True,
                    hold_elapsed_s=elapsed,
                    state=st,
                )
            # Flat but EXIT_PENDING — clear to IDLE
            return TickDecision(
                action=ExitAction.NONE,
                log_code="EXIT_PENDING_FLAT",
                gap_ok=gap_ok,
                state=PositionState.IDLE.value,
            )

        if st == PositionState.ENTRY_PENDING.value:
            if not gap_ok:
                return TickDecision(
                    action=ExitAction.NONE,
                    log_code="ENTRY_WAIT_GAP",
                    gap_ok=False,
                    state=st,
                )
            return TickDecision(
                action=ExitAction.ENTER,
                log_code="ENTRY_PENDING_BUY",
                gap_ok=True,
                state=st,
            )

        return TickDecision(action=ExitAction.NONE, state=st)

    def note_tick_ts(self, tick_ts: str) -> None:
        self._prev_tick_ts = tick_ts

    def apply_enter(
        self,
        *,
        entry_tick_ts: str,
        entry_price: str,
        entry_signal_id: str,
        symbol: str,
    ) -> None:
        self.store.set_holding(
            entry_tick_ts=entry_tick_ts,
            entry_price=entry_price,
            entry_signal_id=entry_signal_id,
            symbol=symbol,
        )

    def apply_hold_expired_pending(self, *, since_ts: str) -> None:
        self.store.set_exit_pending(since_ts=since_ts)

    def apply_exit_to_idle(self) -> None:
        self.store.set_idle()

    def record_edge(
        self,
        *,
        entry_tick_id: str,
        exit_tick_id: str,
        entry_price: str,
        exit_price: str,
        pnl_eur: str,
        hold_seconds_actual: float,
        exit_reason: str,
        worm_sell_hash: str,
        entry_tick_ts: str,
        exit_tick_ts: str,
    ) -> Dict[str, Any]:
        return self.edges.append(
            {
                "entry_tick_id": entry_tick_id,
                "exit_tick_id": exit_tick_id,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_eur": pnl_eur,
                "hold_seconds_actual": hold_seconds_actual,
                "hold_seconds_target": self.hold_seconds,
                "exit_reason": exit_reason,
                "worm_sell_hash": worm_sell_hash,
                "entry_tick_ts": entry_tick_ts,
                "exit_tick_ts": exit_tick_ts,
            }
        )


def enrich_sell_worm_fields(
    fill: Dict[str, Any],
    *,
    entry_tick_ts: str,
    exit_tick_ts: str,
    hold_seconds_target: int,
    exit_reason: str,
) -> Dict[str, Any]:
    """I4 — SIM_FILL SELL field extension; strip forbidden sizing keys."""
    if exit_reason not in EXIT_REASONS:
        raise ValueError(f"invalid exit_reason: {exit_reason}")
    hold_actual = parse_ts_unix(exit_tick_ts) - parse_ts_unix(entry_tick_ts)
    out = {
        **fill,
        "entry_tick_ts": entry_tick_ts,
        "exit_tick_ts": exit_tick_ts,
        "hold_seconds_actual": round(hold_actual, 6),
        "hold_seconds_target": int(hold_seconds_target),
        "exit_reason": exit_reason,
        "not_investment_advice": True,
    }
    for k in FORBIDDEN_PAPER_KEYS:
        out.pop(k, None)
    return out


def enrich_buy_worm_fields(fill: Dict[str, Any], *, entry_tick_ts: str) -> Dict[str, Any]:
    out = {**fill, "entry_tick_ts": entry_tick_ts}
    for k in FORBIDDEN_PAPER_KEYS:
        out.pop(k, None)
    return out
