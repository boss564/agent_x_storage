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
    ExecutedFillEvent,
    OrderSide,
    OrderStatus,
    PeakEvent,
    PortfolioSnapshot,
    Position,
    VirtualPortfolio,
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


@dataclass
class _JournalPosition:
    """Minimale Positionszeile fuer den unabhaengigen Journal-Fold."""

    market_id: str
    size: Decimal
    avg_entry_price: Decimal


def diff_audit_state(
    live_snapshot: PortfolioSnapshot,
    replay_snapshot: PortfolioSnapshot,
    *,
    live_realized_pnl: Decimal,
    replay_realized_pnl: Decimal,
    live_peak_equity: Decimal,
    replay_peak_equity: Decimal,
    previous_live_peak: Optional[Decimal] = None,
    check_peak: bool = True,
) -> tuple[AuditFinding, ...]:
    """Vergleicht Snapshots + realized_pnl; Peak als Invariante, nicht Gleichheit.

    mark_prices bewusst ausgelassen (beide Seiten denselben Dict).
    Peak: Live kann durch Book-Updates (ohne Journal-Event) steigen und
    spaeter wieder fallen — Gleichheit waere ein False-Positive.
    Geprueft wird:
      1) live_peak >= max(replay_peak, replay_equity)  (Untergrenze)
      2) live_peak sinkt nie zwischen zwei Audits (Monotonie)
    """
    findings: list[AuditFinding] = []
    if live_snapshot.cash != replay_snapshot.cash:
        findings.append(AuditFinding(
            "cash", str(live_snapshot.cash), str(replay_snapshot.cash),
        ))
    if live_snapshot.equity != replay_snapshot.equity:
        findings.append(AuditFinding(
            "equity", str(live_snapshot.equity), str(replay_snapshot.equity),
        ))
    live_pos = {k: str(v) for k, v in live_snapshot.positions.items()}
    replay_pos = {k: str(v) for k, v in replay_snapshot.positions.items()}
    for key in sorted(set(live_pos) | set(replay_pos)):
        path = f"positions.{key}"
        if key not in live_pos:
            findings.append(AuditFinding(path, "<missing>", replay_pos[key]))
        elif key not in replay_pos:
            findings.append(AuditFinding(path, live_pos[key], "<missing>"))
        elif live_pos[key] != replay_pos[key]:
            findings.append(AuditFinding(path, live_pos[key], replay_pos[key]))
    if live_realized_pnl != replay_realized_pnl:
        findings.append(AuditFinding(
            "realized_pnl", str(live_realized_pnl), str(replay_realized_pnl),
        ))
    if check_peak:
        floor = max(replay_peak_equity, replay_snapshot.equity)
        if live_peak_equity < floor:
            findings.append(AuditFinding(
                "peak_equity.floor",
                str(live_peak_equity),
                f"min_required={floor}",
            ))
        if (
            previous_live_peak is not None
            and live_peak_equity < previous_live_peak
        ):
            findings.append(AuditFinding(
                "peak_equity.monotonic",
                str(live_peak_equity),
                f"previous={previous_live_peak}",
            ))
    return tuple(findings)


def check_peak_ceiling(
    peak_events: Iterable[PeakEvent],
    journal: tuple[ExecutedFillEvent, ...] | list[ExecutedFillEvent],
    start_balance: Decimal = DEFAULT_VIRTUAL_CASH,
    tolerance: Decimal = Decimal("0"),
    live_peak: Decimal | None = None,
) -> tuple[AuditFinding, ...]:
    """PeakEvent Stufe 2: Live-Peak darf nicht hoeher sein als das Journal.

    Fuer jeden PeakEvent-Zeugen wird das Fill-Journal unabhaengig bis zu
    seinem Cursor gefaltet und die Equity mit den im Event konservierten
    Marks gerechnet. Referenz ist bewusst das Journal (eigener Fold +
    Event-Marks), nicht der Live-Mark-Cache.

    Zusaetzlich (wenn ``live_peak`` gesetzt): der Live-Peak muss durch den
    PeakEvent-Strom gedeckt sein — sonst ``peak_equity.ceiling.unwitnessed``.
    Gedeckt heisst ``live_peak <= max(start_balance, letztes PeakEvent.peak_equity)
    + tolerance``. Ohne Events ist die Decke ``start_balance``.

    Returns:
        Findings mit Pfad ``peak_equity.ceiling[<seq>]`` bzw.
        ``peak_equity.ceiling.unwitnessed`` (leer = ok).
    """
    events = tuple(peak_events)
    journal_tuple = tuple(journal)
    findings: list[AuditFinding] = []
    for event in events:
        path = f"peak_equity.ceiling[{event.seq}]"
        if event.journal_pos > len(journal_tuple):
            findings.append(AuditFinding(
                f"{path}.journal_pos",
                str(event.journal_pos),
                f"journal_len={len(journal_tuple)}",
            ))
            continue
        replayed = JournalReplay(start_balance=start_balance)
        fold_findings, _ = replayed.apply_events(
            journal_tuple[: event.journal_pos],
        )
        if fold_findings:
            findings.extend(fold_findings)
            continue
        replay_equity = replayed.equity(dict(event.marks))
        if event.peak_equity > replay_equity + tolerance:
            findings.append(AuditFinding(
                path,
                format(event.peak_equity, "f"),
                format(replay_equity, "f"),
            ))
    if live_peak is not None:
        witnessed = start_balance
        if events:
            witnessed = max(witnessed, events[-1].peak_equity)
        if live_peak > witnessed + tolerance:
            findings.append(AuditFinding(
                "peak_equity.ceiling.unwitnessed",
                format(live_peak, "f"),
                format(witnessed, "f"),
            ))
    return tuple(findings)


# Rueckwaerts-Kompat: Snapshot-Diff ohne Peak-/PnL-Semantik.
def diff_portfolio_snapshots(
    live: PortfolioSnapshot,
    replay: PortfolioSnapshot,
) -> tuple[AuditFinding, ...]:
    """Nur cash/equity/positions — ohne mark_prices und ohne Peak-Checks."""
    return diff_audit_state(
        live, replay,
        live_realized_pnl=Decimal("0"),
        replay_realized_pnl=Decimal("0"),
        live_peak_equity=Decimal("0"),
        replay_peak_equity=Decimal("0"),
        check_peak=False,
    )


class JournalReplay:
    """Unabhaengiger Buchhaltungs-Gegenlauf aus dem Fill-Journal.

    Ruft bewusst **nicht** ``VirtualPortfolio.apply_fill`` auf — Cash,
    Positionsgroesse, Durchschnittspreis und realisierter PnL sind hier
    ein zweites Mal ausgeschrieben. So findet das Audit Fehler in
    ``apply_fill`` selbst, nicht nur doppelte/verlorene Events.
    """

    def __init__(self, start_balance: Decimal = DEFAULT_VIRTUAL_CASH) -> None:
        self._start_balance = start_balance
        self.reset()

    def reset(self) -> None:
        """Setzt den Fold-Zustand auf Startkapital zurueck (Vollaudit)."""
        self.cash = self._start_balance
        self.realized_pnl = Decimal("0")
        self.peak_equity = self._start_balance
        self._positions: dict[str, _JournalPosition] = {}
        # Monotonie: letzter beobachteter Live-Peak (None = noch kein Audit)
        self.last_live_peak: Optional[Decimal] = None

    def apply_events(
        self,
        events: Iterable[ExecutedFillEvent],
    ) -> tuple[tuple[AuditFinding, ...], int]:
        """Faltet Events; Cursor-sicher bei Fold-Fehlern.

        Returns:
            (findings, n_consumed) — jedes Event zaehlt als verbraucht,
            auch wenn der Fold fehlschlaegt (sonst wuerden erfolgreiche
            Events davor beim naechsten Tick doppelt gebucht).
        """
        findings: list[AuditFinding] = []
        consumed = 0
        for event in events:
            try:
                self._fold(event)
            except ValueError as exc:
                findings.append(AuditFinding(
                    path="journal",
                    live="fold_ok",
                    replay=str(exc),
                ))
            consumed += 1
        return tuple(findings), consumed

    def touch_marks(self, mark_prices: Mapping[str, Decimal]) -> None:
        """Peak-Equity anhand aktueller Marks nachziehen (wie Engine-Feed)."""
        eq = self.equity(mark_prices)
        if eq > self.peak_equity:
            self.peak_equity = eq

    def equity(self, mark_prices: Mapping[str, Decimal]) -> Decimal:
        unrealized = Decimal("0")
        for tid, pos in self._positions.items():
            mark = mark_prices.get(tid, pos.avg_entry_price)
            unrealized += pos.size * mark
        return self.cash + unrealized

    def snapshot(
        self,
        mark_prices: Mapping[str, Decimal],
        as_of_seq: int = 0,
    ) -> PortfolioSnapshot:
        marks = dict(mark_prices)
        return PortfolioSnapshot(
            cash=self.cash,
            equity=self.equity(marks),
            positions={tid: p.size for tid, p in self._positions.items()},
            as_of_seq=as_of_seq,
            mark_prices=marks,
        )

    def _fold(self, event: ExecutedFillEvent) -> None:
        """Kauf/Verkauf analog apply_fill — absichtlich duplizierte Arithmetik."""
        fill = event.fill
        price = fill.execution_price
        size = fill.executed_size
        fee = fill.fee or Decimal("0")
        cost = price * size

        if event.side is OrderSide.BUY:
            total_cost = cost + fee
            if total_cost > self.cash:
                raise ValueError(
                    f"Journal INSUFFICIENT_CASH: braucht {total_cost}, hat {self.cash}"
                )
            self.cash -= total_cost
            pos = self._positions.get(event.token_id)
            if pos is None:
                self._positions[event.token_id] = _JournalPosition(
                    market_id=event.market_id,
                    size=size,
                    avg_entry_price=price,
                )
            else:
                total = pos.size + size
                pos.avg_entry_price = (
                    (pos.avg_entry_price * pos.size) + (price * size)
                ) / total
                pos.size = total
        else:
            pos = self._positions.get(event.token_id)
            if pos is None:
                raise ValueError(f"Journal SELL ohne Position: {event.token_id}")
            if size <= 0 or size > pos.size:
                raise ValueError(
                    f"Journal SELL size {size} ausserhalb (0, {pos.size}]"
                )
            self.cash += cost - fee
            realized = (price - pos.avg_entry_price) * size
            self.realized_pnl += realized
            pos.size -= size
            if pos.size == 0:
                del self._positions[event.token_id]
