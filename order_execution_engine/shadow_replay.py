"""Shadow-Audit: Rekonstruiert Portfolio-Zustand aus dem Ledger. Read-only.

Faltet Fills mit Fold-Spalten (side/token_id/market_id). Legacy-NULLs werden
als unfaltbar gezaehlt — keine Richtungsvermutung. decision_seq-Luecken in der
Telemetrie werden markiert, nicht abgebrochen.

Ruhende Orders: letzter Telemetrie-Status pro order_id + remaining =
requested_size − Σ executed_size. Keine Schema-Erweiterung — Ruhe-Daten
sind foldbar aus dem bestehenden Ledger. resting_at_seq = decision_seq des
letzten RESTING/PARTIALLY_FILLED-Records (Ledger-Uhr, kein Timestamp).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional

from order_execution_engine.models import (
    DEFAULT_VIRTUAL_CASH,
    ExecutionMode,
    ExecutedFillEvent,
    OrderSide,
    OrderStatus,
    PaperOrder,
    PortfolioSnapshot,
    Position,
    VirtualPortfolio,
    default_expiration,
)
from order_execution_engine.persistence import SQLiteShadowStorage
from order_execution_engine.shadow_execution_engine import TelemetryRecord


@dataclass(frozen=True)
class RestingReplay:
    """Rekonstruiertes ruhendes Order-Fragment (kein Matcher-Register)."""

    order_id: uuid.UUID
    remaining: Decimal
    resting_at_seq: int
    token_id: Optional[str] = None
    market_id: Optional[str] = None
    requested_size: Optional[Decimal] = None


@dataclass(frozen=True)
class ReplayResult:
    """Ergebnis einer Read-only-Rekonstruktion."""

    snapshot: PortfolioSnapshot
    gaps: tuple[int, ...]  # fehlende decision_seq-Werte (markiert)
    fills_folded: int
    unfilled_rows: int  # Legacy-NULLs / unfaltbare Zeilen
    resting_orders: tuple[RestingReplay, ...] = ()


class ShadowReplay:
    """Faltet das Persistenz-Ledger zu Portfolio + ruhenden Orders."""

    # Terminal: Order liegt nicht mehr im virtuellen Buch.
    _DONE = frozenset({
        OrderStatus.FILLED,
        OrderStatus.EXPIRED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED_BY_RISK,
    })

    def __init__(self, storage: SQLiteShadowStorage, start_cash: Decimal) -> None:
        self._storage = storage
        self._start_cash = start_cash

    def reconstruct(
        self,
        *,
        mark_prices: Optional[Mapping[str, Decimal]] = None,
        as_of_seq: Optional[int] = None,
    ) -> ReplayResult:
        """Rekonstruiert Zustand bis ``as_of_seq`` (inkl.), sonst vollstaendig."""
        telemetry = self._storage.read_telemetry(upto_decision_seq=as_of_seq)
        gaps = self._gaps(telemetry)
        portfolio = VirtualPortfolio(
            cash=self._start_cash,
            start_balance=self._start_cash,
            peak_equity=self._start_cash,
        )
        folded = 0
        unfilled = 0
        fills = self._storage.read_fills_all()
        for row in fills:
            seq = row.get("decision_seq")
            if as_of_seq is not None:
                if seq is None:
                    unfilled += 1
                    continue
                if int(seq) > as_of_seq:
                    continue
            if not self._is_foldable(row):
                unfilled += 1
                continue
            self._fold(portfolio, row)
            folded += 1
        marks = dict(mark_prices or {})
        seq_out = as_of_seq if as_of_seq is not None else (
            max((t.decision_seq for t in telemetry), default=0)
        )
        resting = self._resting_orders(telemetry, fills, as_of_seq=as_of_seq)
        return ReplayResult(
            snapshot=portfolio.snapshot(marks, as_of_seq=seq_out),
            gaps=gaps,
            fills_folded=folded,
            unfilled_rows=unfilled,
            resting_orders=resting,
        )

    def _resting_orders(
        self,
        telemetry: list[TelemetryRecord],
        fills: list[dict[str, Any]],
        *,
        as_of_seq: Optional[int],
    ) -> tuple[RestingReplay, ...]:
        """Letzter Status pro order_id + remaining aus Fills; keine Schema-Aenderung."""
        last_by_order: dict[uuid.UUID, TelemetryRecord] = {}
        for rec in telemetry:
            if rec.order_id is None:
                continue
            prev = last_by_order.get(rec.order_id)
            if prev is None or rec.decision_seq >= prev.decision_seq:
                last_by_order[rec.order_id] = rec

        executed: dict[uuid.UUID, Decimal] = {}
        meta: dict[uuid.UUID, tuple[Optional[str], Optional[str]]] = {}
        for row in fills:
            seq = row.get("decision_seq")
            if as_of_seq is not None:
                if seq is None or int(seq) > as_of_seq:
                    continue
            try:
                oid = uuid.UUID(str(row["order_id"]))
            except (ValueError, TypeError, KeyError):
                continue
            size = Decimal(row["executed_size"])
            executed[oid] = executed.get(oid, Decimal("0")) + size
            if oid not in meta and self._is_foldable(row):
                meta[oid] = (str(row["token_id"]), str(row["market_id"]))

        out: list[RestingReplay] = []
        for oid, rec in last_by_order.items():
            if rec.status is None or rec.status in self._DONE:
                continue
            filled = executed.get(oid, Decimal("0"))
            requested = rec.requested_size
            if requested is None:
                continue
            remaining = requested - filled
            if remaining <= 0:
                continue
            # RESTING (idle) oder PARTIALLY_FILLED mit Rest (GTC im Register)
            if rec.status is OrderStatus.RESTING:
                pass
            elif rec.status is OrderStatus.PARTIALLY_FILLED:
                pass
            else:
                continue
            tok, mkt = meta.get(oid, (None, None))
            out.append(RestingReplay(
                order_id=oid,
                remaining=remaining,
                resting_at_seq=rec.decision_seq,
                token_id=tok,
                market_id=mkt,
                requested_size=requested,
            ))
        out.sort(key=lambda r: (r.resting_at_seq, str(r.order_id)))
        return tuple(out)

    @staticmethod
    def _gaps(telemetry: list[TelemetryRecord]) -> tuple[int, ...]:
        seqs = {t.decision_seq for t in telemetry if t.decision_seq}
        if not seqs:
            return ()
        lo, hi = min(seqs), max(seqs)
        return tuple(s for s in range(lo, hi + 1) if s not in seqs)

    @staticmethod
    def _is_foldable(row: Mapping[str, Any]) -> bool:
        return bool(row.get("side") and row.get("token_id") and row.get("market_id"))

    @staticmethod
    def _fold(portfolio: VirtualPortfolio, row: Mapping[str, Any]) -> None:
        """Cash/Position-Arithmetik analog ``apply_fill``, ohne Pseudo-Order."""
        side = OrderSide(row["side"])
        token_id = str(row["token_id"])
        market_id = str(row["market_id"])
        price = Decimal(row["execution_price"])
        size = Decimal(row["executed_size"])
        fee = Decimal(row["fee"] or "0")
        cost = price * size

        if side is OrderSide.BUY:
            total_cost = cost + fee
            if total_cost > portfolio.cash:
                raise ValueError(
                    f"Replay INSUFFICIENT_CASH: braucht {total_cost}, hat {portfolio.cash}"
                )
            portfolio.cash -= total_cost
            pos = portfolio.positions.get(token_id)
            if pos is None:
                portfolio.positions[token_id] = Position(
                    token_id=token_id,
                    market_id=market_id,
                    side=OrderSide.BUY,
                    avg_entry_price=price,
                    size=size,
                )
            else:
                pos.add_shares(size, price)
        else:
            portfolio.cash += cost - fee
            pos = portfolio.positions.get(token_id)
            if pos is None:
                raise ValueError(f"Replay SELL ohne Position: {token_id}")
            realized = pos.reduce_shares(size, price)
            portfolio.realized_pnl += realized
            if pos.size == 0:
                del portfolio.positions[token_id]


# ---------------------------------------------------------------------------
# In-Memory Journal-Audit (Hub-Selbstpruefung; parallel zum Ledger-Fold oben)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditFinding:
    """Eine einzelne Divergenz zwischen Live- und Journal-Replay-Zustand."""

    path: str
    live: str
    replay: str


@dataclass(frozen=True)
class AuditReport:
    """Ergebnis eines Shadow-Audits gegen das Fill-Journal."""

    ok: bool
    findings: tuple[AuditFinding, ...]
    live_snapshot: PortfolioSnapshot
    replay_snapshot: PortfolioSnapshot


class ShadowAuditDivergence(RuntimeError):
    """Wird geworfen, wenn Live-Portfolio und Journal-Replay auseinanderlaufen."""

    def __init__(self, findings: Iterable[AuditFinding]) -> None:
        self.findings = tuple(findings)
        detail = "; ".join(
            f"{f.path}: live={f.live} replay={f.replay}" for f in self.findings
        )
        super().__init__(f"Shadow-Audit-Divergenz: {detail}")


def diff_portfolio_snapshots(
    live: PortfolioSnapshot,
    replay: PortfolioSnapshot,
) -> tuple[AuditFinding, ...]:
    """Vergleicht zwei PortfolioSnapshots feldweise (ohne as_of_seq-Uhr)."""
    findings: list[AuditFinding] = []
    if live.cash != replay.cash:
        findings.append(AuditFinding("cash", str(live.cash), str(replay.cash)))
    if live.equity != replay.equity:
        findings.append(AuditFinding("equity", str(live.equity), str(replay.equity)))
    live_pos = {k: str(v) for k, v in live.positions.items()}
    replay_pos = {k: str(v) for k, v in replay.positions.items()}
    for key in sorted(set(live_pos) | set(replay_pos)):
        path = f"positions.{key}"
        if key not in live_pos:
            findings.append(AuditFinding(path, "<missing>", replay_pos[key]))
        elif key not in replay_pos:
            findings.append(AuditFinding(path, live_pos[key], "<missing>"))
        elif live_pos[key] != replay_pos[key]:
            findings.append(AuditFinding(path, live_pos[key], replay_pos[key]))
    live_marks = {k: str(v) for k, v in live.mark_prices.items()}
    replay_marks = {k: str(v) for k, v in replay.mark_prices.items()}
    for key in sorted(set(live_marks) | set(replay_marks)):
        path = f"mark_prices.{key}"
        if key not in live_marks:
            findings.append(AuditFinding(path, "<missing>", replay_marks[key]))
        elif key not in replay_marks:
            findings.append(AuditFinding(path, live_marks[key], "<missing>"))
        elif live_marks[key] != replay_marks[key]:
            findings.append(AuditFinding(path, live_marks[key], replay_marks[key]))
    return tuple(findings)


class JournalReplay:
    """Unabhängiger Buchhaltungs-Gegenlauf aus dem In-Memory-Fill-Journal.

    Parallel zu ``ShadowReplay`` (Ledger). Ruft dieselbe ``apply_fill``-Logik
    auf wie die Engine — doppelte/verlorene Fills werden sichtbar.
    """

    def __init__(
        self,
        events: Iterable[ExecutedFillEvent],
        start_balance: Decimal = DEFAULT_VIRTUAL_CASH,
    ) -> None:
        self._events = tuple(events)
        self._start_balance = start_balance

    def reconstruct(self) -> VirtualPortfolio:
        """Rekonstruiert das Portfolio vollständig aus dem Journal."""
        portfolio = VirtualPortfolio(
            cash=self._start_balance,
            start_balance=self._start_balance,
            peak_equity=self._start_balance,
        )
        for event in self._events:
            order = self._replay_order(event)
            portfolio.apply_fill(order, event.fill, market_id=event.market_id)
        return portfolio

    @staticmethod
    def _replay_order(event: ExecutedFillEvent) -> PaperOrder:
        """Minimale valide PaperOrder für ``apply_fill`` aus dem Event."""
        return PaperOrder(
            order_id=event.order_id,
            signal_id=event.signal_id,
            token_id=event.token_id,
            side=event.side,
            price=event.limit_price,
            size=event.order_size,
            expiration=default_expiration(5),
            mode=ExecutionMode.DRY_RUN,
        )
