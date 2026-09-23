"""Shadow-Audit: Rekonstruiert Portfolio-Zustand aus dem Ledger. Read-only.

Faltet Fills mit Fold-Spalten (side/token_id/market_id). Legacy-NULLs werden
als unfaltbar gezaehlt — keine Richtungsvermutung. decision_seq-Luecken in der
Telemetrie werden markiert, nicht abgebrochen.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional

from order_execution_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    Position,
    VirtualPortfolio,
)
from order_execution_engine.persistence import SQLiteShadowStorage
from order_execution_engine.shadow_execution_engine import TelemetryRecord


@dataclass(frozen=True)
class ReplayResult:
    """Ergebnis einer Read-only-Rekonstruktion."""

    snapshot: PortfolioSnapshot
    gaps: tuple[int, ...]  # fehlende decision_seq-Werte (markiert)
    fills_folded: int
    unfilled_rows: int  # Legacy-NULLs / unfaltbare Zeilen


class ShadowReplay:
    """Faltet das Persistenz-Ledger zu einem PortfolioSnapshot."""

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
        for row in self._storage.read_fills_all():
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
        return ReplayResult(
            snapshot=portfolio.snapshot(marks, as_of_seq=seq_out),
            gaps=gaps,
            fills_folded=folded,
            unfilled_rows=unfilled,
        )

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
