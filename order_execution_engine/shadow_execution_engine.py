"""Shadow Execution Engine — autonomer Trockenmodus-Satellit (Dry-Run).

Empfängt Signale (NewsBot), simuliert virtuelle Orders gegen echte
Marktdaten (PolySentinel WebSocket/CLOB), prüft Risikogrenzen und trackt
Performance — vollständig OHNE echtes Geld und OHNE Order-Aussendung.

Charter (hart verdrahtet, siehe models.py):
    diagnostic_only=true, live_execution=false, order_send=false.

Architektur:
    - models.py:  Datenmodelle + SafetyGuard (eine Quelle der Wahrheit).
    - RiskController:  Pre-Trade-Checks + Drawdown-Lockout.
    - PaperMatchEngine:  Buch-Walk gegen Orderbuch-Tiefe, Partial Fills,
      Slippage-Preview.
    - TelemetryLogger:  Latenz- und Performance-Metriken.
    - ShadowExecutionEngine:  Orchestrierung Signal -> Order -> Match -> Fill.
"""

from __future__ import annotations

import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterable, Optional, Any

from pydantic import BaseModel, ConfigDict

from order_execution_engine.fill_simulator import (
    FillMetrics,
    FillSimConfig,
    FillSimulator,
    StalenessPolicy,
)
from order_execution_engine.models import (
    Direction,
    ExecutionMode,
    ExecutionReport,
    ExecutedFillEvent,
    FillResult,
    MockEIP712Signature,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
    PeakEvent,
    PortfolioSnapshot,
    RejectReason,
    RiskConfig,
    SafetyGuard,
    SignalPayload,
    VirtualPortfolio,
    default_expiration,
)


# ---------------------------------------------------------------------------
# Risiko-Entscheid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskDecision:
    """Ergebnis eines Pre-Trade-Risk-Checks.

    Attribute:
        approved: True, wenn die Order zulässig ist.
        reason: Ablehnungsgrund (NONE bei Zulassung).
    """

    approved: bool
    reason: RejectReason = RejectReason.NONE

    @classmethod
    def ok(cls) -> "RiskDecision":
        """Erzeugt eine Zulassung."""
        return cls(approved=True)

    @classmethod
    def reject(cls, reason: RejectReason) -> "RiskDecision":
        """Erzeugt eine Ablehnung mit Begründung."""
        return cls(approved=False, reason=reason)


class RiskController:
    """Pre-Trade-Risk-Checks und Drawdown-Lockout.

    Prüft (in Reihenfolge, First-Match bricht ab):
        1. Drawdown-Lockout (Notfall-Bremse)
        2. Max. Ordergröße (Shares)
        3. Max. Position Size (Notional)
        4. Max. Exposure pro Event
        5. Cash-Ausreichendheit (nur BUY)
    """

    def __init__(self, config: RiskConfig) -> None:
        """Initialisiert den Controller mit Risikoparametern.

        Args:
            config: RiskConfig mit Limits.
        """
        self.config = config
        self._lockout_active = False

    def evaluate_drawdown(
        self,
        portfolio: VirtualPortfolio,
        mark_prices: dict[str, Decimal],
    ) -> bool:
        """Aktualisiert die Drawdown-Notbremse anhand aktueller Marks.

        Rein lesend: Hebt ``peak_equity`` NICHT an. Peak-Anhebungen erfolgen
        ausschließlich engine-seitig (Single-Writer + PeakEvent), damit jede
        echte Anhebung prüfbar ist. Nutzt bewusst nicht
        ``current_drawdown_pct`` (das den Peak nachziehen würde).
        """
        if self._lockout_active:
            return True
        eq = portfolio.equity(mark_prices)
        peak = portfolio.peak_equity
        if peak > 0 and eq < peak and ((peak - eq) / peak) * Decimal("100") >= self.config.max_drawdown_pct:
            self._lockout_active = True
            return True
        return False

    def check(
        self,
        order: PaperOrder,
        portfolio: VirtualPortfolio,
        mark_prices: dict[str, Decimal],
    ) -> RiskDecision:
        """Führt alle Pre-Trade-Checks für eine Order aus.

        Args:
            order: Die zu prüfende Paper-Order.
            portfolio: Aktuelles virtuelles Portfolio.
            mark_prices: Aktuelle Marktpreise pro token_id.

        Returns:
            RiskDecision mit Zulassung oder Ablehnungsgrund.
        """
        if self.evaluate_drawdown(portfolio, mark_prices):
            return RiskDecision.reject(RejectReason.DRAWDOWN_LOCKOUT)

        # --- Order-Level-Checks (F1b: entfernt) ---
        # Zwei Checks wurden hier gelöscht, mit unterschiedlicher Begründung:
        #
        # 116 (`order.size > max_order_size_shares`) war eine FALLE, kein
        # Schutz. Mit F1 hat `max_order_size_shares` seine Schranken-Semantik
        # verloren: Es ist nur noch die Größe, die der Default-Adapter ordert
        # (Strategie-Platzhalter), keine Obergrenze. Die Obergrenze ist
        # `per_order_cap_shares` (engine-seitig geklemmt). Der Check bestrafte
        # damit genau die Orders, die das Cap explizit erlaubt: cap=300,
        # Strategy will 250, legacy=100 → Clamp lässt 250 durch, 116 rejectet.
        # Das Cap-Feature wäre nach oben unbenutzbar gewesen.
        #
        # 118 (`order.notional > max_position_size_usdc`) war per Konstruktion
        # tot. Die Invarianten-Kette trägt: `notional = size × price ≤ size`
        # (Polymarket-Preise in (0, 1]) `≤ cap ≤ max_position_size_usdc`.
        # Der kumulierte Positions-Check unten deckt den Bestandsfall ab.

        market_exposure = portfolio.exposure_per_market().get(order.token_id, Decimal("0"))
        pos = portfolio.positions.get(order.token_id)
        current_notional = pos.size * pos.avg_entry_price if pos else Decimal("0")
        # --- Bestandsbildend (F1, VM1): die eigentliche Positions-Schranke ---
        # Das ist der Check, der vor F1 strukturell unerreichbar war, weil die
        # Ordergröße aus der Config abgeleitet wurde (size == Limit). Mit
        # signal-getriebenem Sizing und engine-seitigem Clamp ist er die
        # alleinige Pre-Trade-Positionsbremse.
        if order.side == OrderSide.BUY and current_notional + order.notional > self.config.max_position_size_usdc:
            return RiskDecision.reject(RejectReason.MAX_POSITION_SIZE)

        # SELL nur gegen bestehende Position (Short-Verbot im Dry-Run)
        if order.side == OrderSide.SELL:
            available = pos.size if pos else Decimal("0")
            if available <= 0 or order.size > available:
                return RiskDecision.reject(RejectReason.MAX_POSITION_SIZE)

        # Event-Exposure: Token -> Market-Mapping über Position oder Mapping-Tabelle
        market_id = pos.market_id if pos else self._resolve_market(order)
        event_exposure = portfolio.exposure_per_market().get(market_id, Decimal("0"))
        if order.side == OrderSide.BUY and event_exposure + order.notional > self.config.max_event_exposure_usdc:
            return RiskDecision.reject(RejectReason.MAX_EVENT_EXPOSURE)

        if order.side == OrderSide.BUY and order.notional > portfolio.cash:
            return RiskDecision.reject(RejectReason.INSUFFICIENT_CASH)

        return RiskDecision.ok()

    def _resolve_market(self, order: PaperOrder) -> str:
        """Löst market_id für neue Positionen auf (Hook für Markt-Mapping).

        Args:
            order: PaperOrder ohne bestehende Position.

        Returns:
            market_id (Default: token_id als Fallback).
        """
        return order.token_id

    def reset_lockout(self) -> None:
        """Hebt den Drawdown-Lockout manuell auf (Operator-Eingriff)."""
        self._lockout_active = False

    @property
    def lockout_active(self) -> bool:
        """Gibt zurück, ob der Drawdown-Lockout aktiv ist."""
        return self._lockout_active


# ---------------------------------------------------------------------------
# Marktdaten-Adapter (PolySentinel-Schnittstelle)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderBookLevel:
    """Eine Orderbuch-Stufe aus PolySentinel.

    Attribute:
        price: Limitpreis der Stufe (0 < p < 1).
        size: Verfügbare Shares an dieser Stufe.
    """

    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class MarketSnapshot:
    """Marktschnappschuss eines Tokens (Bid/Ask-Tiefe).

    Attribute:
        token_id: CLOB Token-ID.
        bids: Kaufseite, sortiert absteigend.
        asks: Verkauitsseite, sortiert aufsteigend.
        received_at: Empfangszeitpunkt (PolySentinel).
    """

    token_id: str
    bids: tuple[OrderBookLevel, ...] = ()
    asks: tuple[OrderBookLevel, ...] = ()
    received_at: float = field(default_factory=time.time)

    def best_bid(self) -> Optional[Decimal]:
        """Gibt den besten Bid zurück (None bei leerer Seite)."""
        return self.bids[0].price if self.bids else None

    def best_ask(self) -> Optional[Decimal]:
        """Gibt den besten Ask zurück (None bei leerer Seite)."""
        return self.asks[0].price if self.asks else None

    def mark_price(self) -> Optional[Decimal]:
        """Mid aus best Bid/Ask; eine Seite allein genuegt als Fallback."""
        bid, ask = self.best_bid(), self.best_ask()
        if bid is not None and ask is not None:
            return (bid + ask) / Decimal("2")
        return bid if bid is not None else ask


# ---------------------------------------------------------------------------
# Match-Simulation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchResult:
    """Ergebnis der Buch-Walk-Simulation.

    Attribute:
        status: OrderStatus nach Simulation.
        fills: Liste der simulierten Partial Fills.
        avg_execution_price: Volumengewichteter Durchschnittspreis.
        total_slippage_bps: Gesamtslippage in Basispunkten (vs. Limit).
        remaining_size: Nicht ausgeführte Restgröße.
        fill_metrics: Additiv (Commit 2) — Beobachtung aus FillSimulator;
            Default None, Bestand-Caller bleiben kompatibel.
    """

    status: OrderStatus
    fills: tuple[FillResult, ...]
    avg_execution_price: Optional[Decimal]
    total_slippage_bps: Decimal
    remaining_size: Decimal
    fill_metrics: Optional[FillMetrics] = None


@dataclass
class _RestingOrder:
    """Ruhende GTC-Order im virtuellen Buch (Matcher-intern)."""

    order: PaperOrder
    remaining_size: Decimal
    signal_id: Optional[uuid.UUID]
    market_id: Optional[str]
    requested_size: Optional[Decimal]
    decision_seq: int
    resting_since: datetime


@dataclass(frozen=True)
class RestingEvaluation:
    """Ergebnis der ruhenden Nachwertung, inkl. Telemetrie-Kontext."""

    order_id: uuid.UUID
    signal_id: Optional[uuid.UUID]
    market_id: Optional[str]
    requested_size: Optional[Decimal]
    decision_seq: int
    result: MatchResult


@dataclass(frozen=True)
class RestingExpiry:
    """Register-Exit ohne Fill: ruhende Order hat TTL erreicht."""

    order_id: uuid.UUID
    signal_id: Optional[uuid.UUID]
    market_id: Optional[str]
    requested_size: Optional[Decimal]
    decision_seq: int
    remaining_size: Decimal  # ungefuellter Rest (Audit, kein Cash-Effekt)


class PaperMatchEngine:
    """Fill- und Slippage-Simulation via Buch-Walk gegen Orderbuch-Tiefe.

    BUY-Orders laufen gegen die Ask-Seite, SELL-Orders gegen die Bid-Seite.
    Ein Fill tritt nur ein, wenn das Limit greift (BUY: ask <= limit,
    SELL: bid >= limit).

    FAK: Rest wird verworfen (zustandslos). GTC: Rest ruht in ``_resting``
    und wird bei ``on_book_update`` nachgewertet.
    """

    def __init__(
        self,
        fee_bps: Decimal = Decimal("0"),
        max_slippage_bps: Optional[Decimal] = None,
        *,
        fill_sim_config: Optional[FillSimConfig] = None,
    ) -> None:
        """Initialisiert die Match-Engine.

        Args:
            fee_bps: Simulierte Gebühr pro Fill in Basispunkten.
            max_slippage_bps: Optionales Slippage-Limit; darüber wird
                die Order nicht ausgeführt (Reject).
            fill_sim_config: Optionale Fill-Tiefe-Knöpfe (Staleness/Queue).
                ``fee_bps`` / ``max_slippage_bps`` kommen **immer** 1:1 von
                den Matcher-Args — keine zweite Wahrheitsquelle.
        """
        self.fee_bps = fee_bps
        self.max_slippage_bps = max_slippage_bps
        # Drift-Risiko 1: Cap/Fee ausschließlich vom Matcher.
        if fill_sim_config is None:
            sim_cfg = FillSimConfig(
                max_slippage_bps=max_slippage_bps, fee_bps=fee_bps,
            )
        else:
            sim_cfg = fill_sim_config.model_copy(update={
                "max_slippage_bps": max_slippage_bps,
                "fee_bps": fee_bps,
            })
        self._fill_sim = FillSimulator(sim_cfg)
        self._resting: dict[uuid.UUID, _RestingOrder] = {}

    @property
    def resting_count(self) -> int:
        """Anzahl ruhender GTC-Orders (Test-Seam)."""
        return len(self._resting)

    def preview_slippage(self, order: PaperOrder, snapshot: MarketSnapshot) -> Decimal:
        """Berechnet erwartete Slippage in bps OHNE Order zu erzeugen.

        Args:
            order: PaperOrder.
            snapshot: Aktueller Marktschnappschuss.

        Returns:
            Erwartete Slippage in Basispunkten (>= 0).
        """
        side_levels = snapshot.asks if order.side == OrderSide.BUY else snapshot.bids
        if not side_levels:
            return Decimal("0")
        ref = side_levels[0].price
        slip = abs(ref - order.price) / order.price * Decimal("10000")
        return slip.quantize(Decimal("0.01"))

    def match(
        self,
        order: PaperOrder,
        snapshot: MarketSnapshot,
        *,
        signal_id: Optional[uuid.UUID] = None,
        market_id: Optional[str] = None,
        requested_size: Optional[Decimal] = None,
        decision_seq: int = 0,
    ) -> MatchResult:
        """Führt den Buch-Walk für eine Order aus.

        Args:
            order: Die zu füllende PaperOrder.
            snapshot: Marktdaten-Schnappschuss (PolySentinel).
            signal_id/market_id/requested_size/decision_seq: Kontext für
                GTC-Resting-Register (Telemetrie bei Nachwertung).

        Returns:
            MatchResult mit Fills, Status und Slippage-Statistik.
        """
        if snapshot.token_id != order.token_id:
            raise ValueError("Snapshot token_id passt nicht zur Order.")
        if order.order_type is OrderType.FAK:
            return self._match_fak(order, snapshot, market_id=market_id)
        if order.order_type is OrderType.GTC:
            return self._match_gtc(
                order, snapshot,
                signal_id=signal_id, market_id=market_id,
                requested_size=requested_size, decision_seq=decision_seq,
            )
        raise NotImplementedError(
            f"OrderType {order.order_type.value}: kein Produzent/Zeuge im "
            f"Dry-Run (aktiv: FAK, GTC; siehe OrderType-Docstring). "
            f"Wert zuerst implementieren, dann aufnehmen."
        )

    def _cross_with_metrics(
        self, order: PaperOrder, snapshot: MarketSnapshot, size: Decimal,
        *, market_id: Optional[str] = None,
    ) -> tuple[list[FillResult], Decimal, Decimal, FillMetrics]:
        """Walk via FillSimulator + Kanon-Tupel (fills, remaining, ref)."""
        fills, metrics = self._fill_sim.cross(
            order, snapshot, size=size, market_id=market_id,
        )
        remaining = size - sum(
            (f.executed_size for f in fills), Decimal("0"),
        )
        levels = snapshot.asks if order.side == OrderSide.BUY else snapshot.bids
        reference_for_total = order.price
        for _lvl in levels:
            if _lvl.price > 0 and _lvl.size > 0:
                reference_for_total = _lvl.price
                break
        return fills, remaining, reference_for_total, metrics

    def _cross(
        self, order: PaperOrder, snapshot: MarketSnapshot, size: Decimal,
        *, market_id: Optional[str] = None,
    ) -> tuple[list[FillResult], Decimal, Decimal]:
        """Kreuzt ``size`` gegen sichtbare Tiefe (Bestand-Walk 1:1).

        Commit 2: dünne Delegation an ``FillSimulator.cross``. Signatur und
        Rückgabe = Kanon ``(fills, remaining, reference_for_total)``.
        ``FillMetrics`` bleiben intern (über ``_cross_with_metrics`` /
        ``match``); externe Caller sehen sie nicht. Entfernung des Rumpfs
        in Commit 3 nach grüner Regression.
        """
        fills, remaining, reference_for_total, _metrics = self._cross_with_metrics(
            order, snapshot, size, market_id=market_id,
        )
        return fills, remaining, reference_for_total

    def _build_result(
        self,
        fills: list[FillResult],
        remaining: Decimal,
        reference_for_total: Decimal,
        *,
        idle_status: OrderStatus,
        fill_metrics: Optional[FillMetrics] = None,
    ) -> MatchResult:
        """Status/avg/slippage — idle_status = PENDING (FAK) oder RESTING (GTC)."""
        total_slip_bps = Decimal("0")
        avg_price: Optional[Decimal] = None
        if fills:
            notional_sum = sum(
                (f.execution_price * f.executed_size for f in fills), Decimal("0")
            )
            volume_sum = sum((f.executed_size for f in fills), Decimal("0"))
            if volume_sum > 0:
                avg_price = notional_sum / volume_sum
                total_slip_bps = (
                    (avg_price - reference_for_total) / reference_for_total * Decimal("10000")
                ).copy_abs()

        if not fills:
            status = idle_status
        elif remaining > 0:
            status = OrderStatus.PARTIALLY_FILLED
        else:
            status = OrderStatus.FILLED

        return MatchResult(
            status=status,
            fills=tuple(fills),
            avg_execution_price=avg_price,
            total_slippage_bps=total_slip_bps,
            remaining_size=remaining,
            fill_metrics=fill_metrics,
        )

    def _match_fak(
        self,
        order: PaperOrder,
        snapshot: MarketSnapshot,
        *,
        market_id: Optional[str] = None,
    ) -> MatchResult:
        """FAK: heutiger Pfad — Rest verworfen, idle = PENDING."""
        fills, remaining, ref, metrics = self._cross_with_metrics(
            order, snapshot, order.size, market_id=market_id,
        )
        return self._build_result(
            fills, remaining, ref,
            idle_status=OrderStatus.PENDING,
            fill_metrics=metrics,
        )

    def _match_gtc(
        self,
        order: PaperOrder,
        snapshot: MarketSnapshot,
        *,
        signal_id: Optional[uuid.UUID],
        market_id: Optional[str],
        requested_size: Optional[Decimal],
        decision_seq: int,
    ) -> MatchResult:
        """GTC: kreuzt, Rest ruht im Register; idle = RESTING."""
        fills, remaining, ref, metrics = self._cross_with_metrics(
            order, snapshot, order.size, market_id=market_id,
        )
        if remaining > 0:
            self._resting[order.order_id] = _RestingOrder(
                order=order,
                remaining_size=remaining,
                signal_id=signal_id,
                market_id=market_id,
                requested_size=requested_size,
                decision_seq=decision_seq,
                resting_since=datetime.now(timezone.utc),
            )
            # Queue-Beobachtung additiv; Kanon-Register bleibt _resting.
            rest = self._fill_sim.place_resting(
                order, snapshot, remaining_size=remaining,
            )
            metrics = metrics.model_copy(update={
                "queue_ahead_at_rest": rest.queue_ahead_at_rest,
                "staleness_applied": rest.staleness_applied,
            })
        return self._build_result(
            fills, remaining, ref,
            idle_status=OrderStatus.RESTING,
            fill_metrics=metrics,
        )

    def on_book_update(self, snapshot: MarketSnapshot) -> list[RestingEvaluation]:
        """Nachwertung ruhender GTC-Orders gegen neuen Snapshot.

        Commit 2: Walk-Umleitung über delegiertes ``_cross`` /
        ``FillSimulator.cross`` mit ``remaining_size`` aus ``_RestingOrder``.
        Kanon-Semantik (Re-Cross gegen sichtbare Tiefe) bleibt — nicht der
        Trade-Through-Observer ``FillSimulator.on_book_update``.
        """
        out: list[RestingEvaluation] = []
        for oid, resting in list(self._resting.items()):
            if resting.order.token_id != snapshot.token_id:
                continue
            fills, remaining, ref, metrics = self._cross_with_metrics(
                resting.order, snapshot, resting.remaining_size,
                market_id=resting.market_id,
            )
            resting.remaining_size = remaining
            result = self._build_result(
                fills, remaining, ref,
                idle_status=OrderStatus.RESTING,
                fill_metrics=metrics,
            )
            out.append(RestingEvaluation(
                order_id=oid,
                signal_id=resting.signal_id,
                market_id=resting.market_id,
                requested_size=resting.requested_size,
                decision_seq=resting.decision_seq,
                result=result,
            ))
            if remaining <= 0:
                del self._resting[oid]
                self._fill_sim._resting_queue.pop(oid, None)
        return out

    def reap_expired(self, now: datetime) -> list[RestingExpiry]:
        """Entfernt abgelaufene ruhende Orders aus dem Register.

        Reiner Matcher-Teil: Transition/Telemetrie gehoert der Engine.
        Vergleichsemantik wie PaperOrder-Konstruktor: ``expiration <= now``
        ist abgelaufen (tz-aware datetime, nicht epoch-int).
        """
        out: list[RestingExpiry] = []
        for oid, resting in list(self._resting.items()):
            if resting.order.expiration > now:
                continue
            out.append(RestingExpiry(
                order_id=oid,
                signal_id=resting.signal_id,
                market_id=resting.market_id,
                requested_size=resting.requested_size,
                decision_seq=resting.decision_seq,
                remaining_size=resting.remaining_size,
            ))
            del self._resting[oid]
        return out


# ---------------------------------------------------------------------------
# Telemetrie
# ---------------------------------------------------------------------------


class TelemetryRecord(BaseModel):
    """Telemetrie-Satz an der Persistenz-Grenze (telemetry-Tabelle).

    Frozen: Fakt, kein Zustand. ADR 13 (Enum-Wache): ``reject_reason`` ist
    immer ein ``RejectReason``-Enum — durchgesetzt durch die Felddeklaration
    (Pydantic-Validierung bei Konstruktion), nicht mehr per ``__post_init__``.
    Das ist keine Abschwaechung: Die Wache greift jetzt auf jedem
    Konstruktionspfad, nicht nur im Dataclass-``__post_init__``.

    Attribute:
        signal_id: Signal-UUID.
        order_id: Order-UUID (None bei Risiko-Ablehnung vor Ordererstellung).
        latency_ms: Signal-Eingang bis Fill-Abschluss.
        approved: Risikoentscheid.
        reject_reason: Ablehnungsgrund. Vertrag: immer ein RejectReason-Enum,
            niemals None — auf dem genehmigten Pfad `RejectReason.NONE`.
        status: Finaler Orderstatus.
        requested_size: Ungekappte Strategie-Groesse (None = nie angefragt).
        decision_seq: Engine-seitige monotone Entscheidungs-Id (Replay).
    """

    model_config = ConfigDict(frozen=True)

    signal_id: uuid.UUID
    order_id: Optional[uuid.UUID]
    latency_ms: float
    approved: bool
    status: Optional[OrderStatus]
    reject_reason: RejectReason = RejectReason.NONE
    requested_size: Optional[Decimal] = None
    decision_seq: int = 0
    fill_metrics: Optional[FillMetrics] = None
    """Additiv Commit 2 — nicht persistiert (Spaltenliste unverändert)."""


class TelemetryLogger:
    """Latenz- und Performance-Logging für den Dry-Run.

    Führt einen engine-eigenen, monotonen `decision_seq`-Zähler. Zweck:
    Sizing-Snapshots und Telemetrie-Records mit *derselben* Id stempeln,
    damit eine Entscheidung später rekonstruierbar ist (Replay).

    Warum nicht die Datenbank-`seq`: Die wird per AUTOINCREMENT erst beim
    INSERT vergeben, also *nach* der Entscheidung. Ein Snapshot müsste sie
    raten — und das stimmt nur unter vier ungeschriebenen Invarianten
    (genau eine Senke, genau ein Record pro Signal, keine Lücken, keine
    parallelen Writer). Die Korrelationsrichtung gehört umgekehrt: Die
    Engine vergibt die Id, die Storage übernimmt sie später.
    """

    def __init__(self, initial_decision_seq: int = 0) -> None:
        """Initialisiert den Logger (leerer Puffer).

        Args:
            initial_decision_seq: Startwert des Zählers. Nach einem
                Prozessneustart MUSS hier `storage.latest_decision_seq()`
                übergeben werden — sonst beginnt der Zähler wieder bei 1 und
                die Snapshot<->Record-Korrelation kollidiert still über
                Sessions hinweg. Der Zähler ist nur replaysicher, solange er
                die Historie kennt (F1, VM3).
        """
        self._records: list[TelemetryRecord] = []
        self._decision_seq: int = initial_decision_seq

    def next_decision_seq(self) -> int:
        """Vergibt die nächste Entscheidungs-Id (monoton, engine-seitig).

        Returns:
            Fortlaufende Id, beginnend bei 1.
        """
        self._decision_seq += 1
        return self._decision_seq

    def log(self, record: TelemetryRecord) -> None:
        """Schreibt einen Telemetrie-Eintrag.

        Args:
            record: Das aufzuzeichnende Ereignis.
        """
        self._records.append(record)

    def latencies_ms(self) -> list[float]:
        """Gibt alle gemessenen Latenzen zurück (ms)."""
        return [r.latency_ms for r in self._records]

    def stats(self) -> dict[str, float]:
        """Berechnet Latenz-Statistiken über alle Einträge.

        Returns:
            Dict mit count/min/median/p95/max (ms).
        """
        lat = self.latencies_ms()
        if not lat:
            return {"count": 0.0, "min_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
        sorted_lat = sorted(lat)
        p95_idx = min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))
        return {
            "count": float(len(lat)),
            "min_ms": min(lat),
            "median_ms": statistics.median(lat),
            "p95_ms": sorted_lat[p95_idx],
            "max_ms": max(lat),
        }

    def reject_rate(self) -> float:
        """Gibt den Anteil der Risiko-Ablehnungen zurück (0.0–1.0)."""
        if not self._records:
            return 0.0
        rejected = sum(1 for r in self._records if not r.approved)
        return rejected / len(self._records)


# ---------------------------------------------------------------------------
# Hauptklasse: Orchestrierung
# ---------------------------------------------------------------------------


# Signatur des Sizing-Seams. Bewusst schmal:
#  - Input: Signal (Conviction) + read-only PortfolioSnapshot (Zeuge)
#  - Output: Decimal (angeforderte Groesse) — kein Ergebnisobjekt.
#    *Warum* die Groesse so ist, ist Strategie-Telemetrie; *was* angefordert
#    wurde, ist Engine-Telemetrie (requested_size). Layer-Ehrlichkeit.
SizeFn = Callable[[SignalPayload, PortfolioSnapshot], Decimal]


class ShadowExecutionEngine:
    """Orchestrations-Hauptklasse des Trockenmodus.

    Pipeline pro Signal:
        1. Guard-Check (Charter)
        2. Inversions-Logik (resolved_side)
        3. Order Framing (PaperOrder + Mock-EIP-712)
        4. Pre-Trade-Risk (RiskController)
        5. Match-Simulation (PaperMatchEngine, PolySentinel-Snapshot)
        6. Portfolio-Buchung (apply_fill)
        7. Telemetrie (Latenz, Entscheidung)

    Das Modul sendet niemals Netzwerk-Requests; der SafetyGuard baut bei
    jedem Versuch sofort ab (order_send=false).
    """

    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
        invert_weak_signals: bool = False,
        confidence_threshold: Decimal = Decimal("55"),
        size_fn: Optional[SizeFn] = None,
        telemetry: Optional[TelemetryLogger] = None,
        fill_sim_config: Optional[FillSimConfig] = None,
    ) -> None:
        """Initialisiert die Engine.

        Args:
            risk_config: Risikoparameter (Default: Standardlimits).
            mode: ExecutionMode (nur DRY_RUN/PAPER_TRADING erlaubt).
            invert_weak_signals: Globaler Inversions-Schalter für Signale
                unterhalb des Confidence-Thresholds.
            confidence_threshold: Schwelle für "schwache Signale" (%).
            size_fn: Injektierbare Sizing-Funktion
                `(signal, portfolio_snapshot) -> desired_size`. Bestimmt die
                *angeforderte* Ordergröße — die Risikoschranken bleiben
                davon unberührt und greifen danach. Default
                (`_default_size_fn`) reproduziert das bisherige Verhalten
                exakt: fixe Größe aus `max_order_size_shares`.
            telemetry: Optionaler Logger. Nach einem Prozessneustart mit
                `TelemetryLogger(initial_decision_seq=storage.latest_decision_seq())`
                übergeben, sonst kollidiert der Zähler über Sessions hinweg.
            fill_sim_config: Optional Fill-Tiefe-Config (Commit 1; Match
                bleibt unberührt — Simulator steht daneben).
        """
        cfg = risk_config or RiskConfig()
        self.guard = SafetyGuard(mode=mode)
        self.risk = RiskController(cfg)
        # Commit 2: ein FillSimulator — Cap/Fee 1:1 vom Matcher; Staleness-
        # Knöpfe optional über fill_sim_config (fee/slippage werden überschrieben).
        self.matcher = PaperMatchEngine(
            fee_bps=cfg.fee_bps, fill_sim_config=fill_sim_config,
        )
        self._fill_sim = self.matcher._fill_sim
        self.portfolio = VirtualPortfolio()
        self.telemetry = telemetry or TelemetryLogger()
        self.invert_weak_signals = invert_weak_signals
        self.confidence_threshold = confidence_threshold
        self.size_fn: SizeFn = size_fn or self._default_size_fn
        self._order_book: dict[uuid.UUID, PaperOrder] = {}
        # Fill-Log fuer TelemetrySink / Replay-Zeugen (order_id -> Fills)
        self._fills_by_order: dict[uuid.UUID, list[FillResult]] = {}
        # Hub: passives Book-Cache + In-Memory-Journal fuer Selbst-Audit
        self._market_snapshots: dict[str, MarketSnapshot] = {}
        self._mark_prices: dict[str, Decimal] = {}
        self._execution_journal: list[ExecutedFillEvent] = []
        self._peak_events: list[PeakEvent] = []
        self._last_expired_orders: tuple[PaperOrder, ...] = ()
        # Nur register_order-IDs: Orderbuch-Reaper darf Match-/FAK-Terminals
        # nicht nachtraeglich auf EXPIRED setzen.
        self._registered_only: set[uuid.UUID] = set()
        # Inkrementelles Journal-Audit (Cursor + Fold-Zustand)
        self._journal_auditor: Optional[Any] = None  # JournalReplay, lazy
        self._audited_upto: int = 0
        # Befund 3: Ceiling-Fold + Equity-Memo ueber Audit-Ticks
        from order_execution_engine.shadow_replay import PeakCeilingChecker
        self._ceiling_checker = PeakCeilingChecker(
            start_balance=self.portfolio.start_balance,
        )

    def _preflight_staleness(
        self,
        signal: SignalPayload,
        snapshot: MarketSnapshot,
        *,
        now: float,
    ) -> Optional[RejectReason]:
        """Fail-closed Frischeprüfung vor dem Matcher (Anker D).

        Das Literal ``RejectReason.STALE_SNAPSHOT`` steht bewusst hier —
        der Regex-Scan in ``test_ankerd_meta_*`` findet nur Produzenten
        in dieser Datei. ``FillSimulator.is_stale`` liefert nur bool.
        """
        now_ms = now * 1000.0
        signal_ts_ms = signal.timestamp.timestamp() * 1000.0
        if self._fill_sim.is_stale(
            snapshot, now_ms=now_ms, signal_timestamp_ms=signal_ts_ms,
        ):
            if self._fill_sim.staleness_policy is StalenessPolicy.NEXT_TICK:
                # Parken via bestehendes GTC-Resting (Commit 2 verdichtet
                # staleness_applied=NEXT_TICK am place_resting-Seam).
                return None
            return RejectReason.STALE_SNAPSHOT
        return None

    def fills_for(self, order_id: uuid.UUID) -> list[FillResult]:
        """Liefert persistierbare Fills zu einer Order (Test-/Sink-Seam)."""
        return list(self._fills_by_order.get(order_id, []))

    # ------------------------------------------------------------------
    # Hub-Vertrag: Feed-Cache, Register, Journal-Audit
    # ------------------------------------------------------------------

    def register_order(self, order: PaperOrder) -> None:
        """Registriert eine Order im Orderbuch (Reaper/Hub ohne Match-Pfad).

        Umgeht den ``RiskController`` absichtlich — nur fuer Hub-/Operator-
        Lebenszyklus (TTL-Reaper), nicht fuer Signal-Matching.
        """
        self.guard.assert_safe()
        self._order_book[order.order_id] = order
        self._registered_only.add(order.order_id)

    def get_snapshot(self, token_id: str) -> Optional[MarketSnapshot]:
        """Gibt den zuletzt injizierten Snapshot für ein Token zurück."""
        return self._market_snapshots.get(token_id)

    def current_marks(self) -> dict[str, Decimal]:
        """Gibt die aktuell bekannten Mark-Preise zurück."""
        return dict(self._mark_prices)

    def execution_journal(self) -> tuple[ExecutedFillEvent, ...]:
        """Unveränderliche Kopie des In-Memory-Fill-Journals."""
        return tuple(self._execution_journal)

    def peak_events(self) -> tuple[PeakEvent, ...]:
        """Unveränderliche Kopie des PeakEvent-Stroms (Stufe 2)."""
        return tuple(self._peak_events)

    def restore_peak_events(self, events: Iterable[PeakEvent]) -> int:
        """Stellt den PeakEvent-Strom nach Reload aus der Persistenz her.

        Nur auf leerem Strom; seq lueckenlos ab 0. Setzt den
        ``PeakCeilingChecker`` zurueck (Befund 4).
        """
        self.guard.assert_safe()
        loaded = list(events)
        if self._peak_events:
            raise ValueError(
                "restore_peak_events nur auf leerem Strom (Reload-Pfad); "
                "live Anhebungen bleiben Single-Writer-Sache (_record_peak)."
            )
        for expected, event in enumerate(loaded):
            if event.seq != expected:
                raise ValueError(
                    f"PeakEvent-Strom nicht lückenlos: erwartet seq={expected}, "
                    f"erhalten seq={event.seq}."
                )
        self._peak_events.extend(loaded)
        self._ceiling_checker.reset()
        return len(loaded)

    @property
    def last_expired_orders(self) -> tuple[PaperOrder, ...]:
        """PaperOrders, die der letzte ``reap_expired``-Aufruf verfallen hat."""
        return self._last_expired_orders

    def _record_peak(self, marks: dict[str, Decimal]) -> None:
        """Hebt peak_equity an und zeugt jede echte Anhebung als PeakEvent.

        Single-Writer: Nur hier darf der Live-Peak steigen, damit Stufe 2
        (``check_peak_ceiling``) jede Anhebung gegen das Journal prüfen kann.
        """
        before = self.portfolio.peak_equity
        after = self.portfolio.update_peak_equity(marks)
        if after > before:
            self._peak_events.append(PeakEvent(
                seq=len(self._peak_events),
                marks=dict(marks),
                journal_pos=len(self._execution_journal),
                peak_equity=after,
            ))

    def _store_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Speichert Snapshot + Mark; Drawdown-Bremse marktgetrieben."""
        self._market_snapshots[snapshot.token_id] = snapshot
        mark = snapshot.mark_price()
        if mark is not None:
            self._mark_prices[snapshot.token_id] = mark
        self._record_peak(self._mark_prices)
        self.risk.evaluate_drawdown(self.portfolio, self._mark_prices)

    def _journal_fill(
        self,
        order: PaperOrder,
        *,
        signal_id: uuid.UUID,
        market_id: str,
        fill: FillResult,
    ) -> None:
        """Append-only Journal-Hook (Hub-Audit; parallel zu ``_fills_by_order``)."""
        self._execution_journal.append(ExecutedFillEvent(
            order_id=order.order_id,
            signal_id=signal_id,
            token_id=order.token_id,
            market_id=market_id,
            side=order.side,
            limit_price=order.price,
            order_size=order.size,
            fill=fill,
        ))

    def _ensure_journal_auditor(self):
        """Lazy JournalReplay an Startkapital des Live-Portfolios."""
        from order_execution_engine.shadow_replay import JournalReplay

        if self._journal_auditor is None:
            self._journal_auditor = JournalReplay(
                start_balance=self.portfolio.start_balance,
            )
            self._audited_upto = 0
        return self._journal_auditor

    def audit_shadow_state(
        self,
        raise_on_divergence: bool = False,
        *,
        full: bool = False,
        peak_tolerance: Decimal = Decimal("0"),
    ) -> "AuditReport":
        """Live-Portfolio gegen unabhaengiges Journal-Replay pruefen.

        Standard: inkrementell (nur Events ab ``_audited_upto``).
        ``full=True``: Fold von vorn, Kontrolle gegen den Cursor-Pfad.

        Peak Stufe 1: Floor + Monotonie (keine Gleichheit).
        Peak Stufe 2: ``check_peak_ceiling`` — Live-Peak darf nicht hoeher
        sein als Journal-Replay-Equity am PeakEvent (Event-Marks); zusaetzlich
        ``peak_equity.ceiling.unwitnessed`` wenn Live-Peak ohne PeakEvent.
        """
        from order_execution_engine.shadow_replay import (
            AuditFinding,
            AuditReport,
            JournalReplay,
            ShadowAuditDivergence,
            diff_audit_state,
        )

        self.guard.assert_safe()
        marks = dict(self._mark_prices)
        journal = self._execution_journal
        fold_findings: tuple[AuditFinding, ...] = ()

        if full:
            prev_peak = (
                self._journal_auditor.last_live_peak
                if self._journal_auditor is not None
                else None
            )
            auditor = JournalReplay(start_balance=self.portfolio.start_balance)
            fold_findings, consumed = auditor.apply_events(journal)
            auditor.touch_marks(marks)
            auditor.last_live_peak = prev_peak
            self._journal_auditor = auditor
            self._audited_upto = consumed
        else:
            auditor = self._ensure_journal_auditor()
            new_events = journal[self._audited_upto:]
            fold_findings, consumed = auditor.apply_events(new_events)
            self._audited_upto += consumed
            auditor.touch_marks(marks)

        live_snapshot = self.portfolio.snapshot(marks, as_of_seq=0)
        replay_snapshot = auditor.snapshot(marks, as_of_seq=0)
        live_peak = self.portfolio.peak_equity
        findings = fold_findings + diff_audit_state(
            live_snapshot,
            replay_snapshot,
            live_realized_pnl=self.portfolio.realized_pnl,
            replay_realized_pnl=auditor.realized_pnl,
            live_peak_equity=live_peak,
            replay_peak_equity=auditor.peak_equity,
            previous_live_peak=auditor.last_live_peak,
        )
        peak_findings = self._ceiling_checker.check(
            self._peak_events,
            journal,
            tolerance=peak_tolerance,
            live_peak=live_peak,
        )
        findings = findings + peak_findings
        # Monotonie-Anker: Peak ohne PeakEvent nicht festschreiben
        if not any(
            f.path == "peak_equity.ceiling.unwitnessed" for f in peak_findings
        ):
            auditor.last_live_peak = live_peak
        report = AuditReport(
            ok=not findings,
            findings=findings,
            live_snapshot=live_snapshot,
            replay_snapshot=replay_snapshot,
        )
        if findings and raise_on_divergence:
            raise ShadowAuditDivergence(findings)
        return report

    def _report(
        self,
        signal: SignalPayload,
        record: TelemetryRecord,
        match: Optional[MatchResult] = None,
    ) -> ExecutionReport:
        """Komposition: Telemetrie-Record + optionales MatchResult.

        Kein neuer Zustand — alles abgeleitet. Persistenz laeuft weiter
        ueber ``TelemetryRecord``; der Report ist Hub-Seite.
        """
        fills = match.fills if match is not None else ()
        # Pre-Order-Rejects setzen status=None am Record; Hub braucht Enum.
        status = (
            record.status
            if record.status is not None
            else OrderStatus.REJECTED_BY_RISK
        )
        return ExecutionReport(
            signal_id=record.signal_id,
            order_id=record.order_id,
            market_id=signal.market_id,
            approved=record.approved,
            status=status,
            reject_reason=record.reject_reason,
            requested_size=record.requested_size,
            executed_size=sum(
                (f.executed_size for f in fills), Decimal("0"),
            ),
            avg_execution_price=(
                match.avg_execution_price if match is not None else None
            ),
            total_slippage_bps=(
                match.total_slippage_bps if match is not None else Decimal("0")
            ),
            remaining_size=(
                match.remaining_size if match is not None else Decimal("0")
            ),
            decision_seq=record.decision_seq,
            latency_ms=record.latency_ms,
            fills=fills,
        )

    def _default_size_fn(self, signal: SignalPayload,
                         snapshot: PortfolioSnapshot) -> Decimal:
        """Default-Sizing: fixe Größe aus dem Risiko-Limit.

        Bewahrt das bisherige Verhalten (die Order war immer exakt
        `max_order_size_shares`) und macht F1c damit zu einem reinen
        Refactoring. Eine echte Strategie ersetzt diese Funktion über
        `size_fn=` — sie gehört nicht in die Engine.
        """
        return self.risk.config.max_order_size_shares

    def on_signal(
        self,
        signal: SignalPayload,
        snapshot: Optional[MarketSnapshot] = None,
    ) -> ExecutionReport:
        """Verarbeitet ein eingehendes Signal komplett (Signal -> Fill).

        Intern wird weiter ein ``TelemetryRecord`` geloggt (Persistenz-
        Boundary). Rueckgabe ist das Hub-DTO ``ExecutionReport``
        (Komposition, kein Ersatz).

        Args:
            signal: SignalPayload aus dem NewsBot.
            snapshot: Marktschnappschuss; fehlt er, wird der letzte
                Hub-/Feed-Snapshot fuer ``signal.target_token_id`` genutzt.

        Returns:
            ExecutionReport mit Latenz, Entscheidung und optionalen Fills.
        """
        t0 = time.perf_counter()
        self.guard.assert_safe()

        # Inversions-Logik: schwache Signale ggf. umkehren (Kontra-Indikator)
        if self.invert_weak_signals and signal.confidence < self.confidence_threshold:
            signal = signal.model_copy(update={"invert": not signal.invert})

        side = signal.resolved_side()
        if side is None:
            record = TelemetryRecord(
                signal_id=signal.signal_id, order_id=None,
                latency_ms=self._elapsed_ms(t0), approved=False,
                reject_reason=RejectReason.INVALID_PRICE, status=None,
                decision_seq=self.telemetry.next_decision_seq(),
            )
            self.telemetry.log(record)
            return self._report(signal, record)

        if snapshot is not None:
            self._store_snapshot(snapshot)
        active = snapshot or self._market_snapshots.get(signal.target_token_id)
        if active is None or active.token_id != signal.target_token_id:
            record = TelemetryRecord(
                signal_id=signal.signal_id, order_id=None,
                latency_ms=self._elapsed_ms(t0), approved=False,
                reject_reason=RejectReason.INVALID_PRICE, status=None,
                decision_seq=self.telemetry.next_decision_seq(),
            )
            self.telemetry.log(record)
            return self._report(signal, record)

        # Preis: Limit auf bestem verfügbaren Level setzen
        ref_price = active.best_ask() if side == OrderSide.BUY else active.best_bid()
        if ref_price is None:
            record = TelemetryRecord(
                signal_id=signal.signal_id, order_id=None,
                latency_ms=self._elapsed_ms(t0), approved=False,
                reject_reason=RejectReason.INVALID_PRICE, status=None,
                decision_seq=self.telemetry.next_decision_seq(),
            )
            self.telemetry.log(record)
            return self._report(signal, record)

        # Sizing über den injizierbaren Seam. Der Portfolio-Snapshot ist
        # read-only; die Sizing-Funktion sieht den Zustand, kann ihn aber
        # nicht mutieren. Der Default reproduziert das bisherige Verhalten.
        # Die Entscheidungs-Id vergibt die Engine — Snapshot und
        # Telemetrie-Record teilen sie (Replay-Korrelation).
        decision_seq = self.telemetry.next_decision_seq()
        marks = dict(self._mark_prices)
        marks[signal.target_token_id] = ref_price
        portfolio_snapshot = self.portfolio.snapshot(
            mark_prices=marks,
            as_of_seq=decision_seq,
        )
        # --- Sizing-Seam (F1c) + engine-seitiger Clamp (F1, VM2) ---
        # `desired` ist der ungekappte Strategie-Vorschlag. Er wird *immer*
        # aufgezeichnet (requested_size), auch wenn er verworfen oder gekappt
        # wird — sonst wäre die Kappung still, und genau das war der Bug.
        #
        # Der Clamp liegt bewusst hier und nicht im Adapter: Ein
        # adapter-interner Clamp würde `desired` verschlucken, `requested_size`
        # wäre der bereits gekappte Wert, und `requested != executed` wäre nie
        # beobachtbar. Die Telemetrie-Motivation stürbe per Konstruktion.
        #
        # Eine Zusicherung im Strategie-Code wäre ein Versprechen, hier ist es
        # eine Garantie — dieselbe Validierung, die der Rückgabewert ohnehin
        # erfährt (negativ/null/NaN), eine Zeile weiter.
        desired = self.size_fn(signal, portfolio_snapshot)
        requested_size = desired
        size = min(desired, self.risk.config.effective_per_order_cap_shares)
        order = PaperOrder(
            signal_id=signal.signal_id,
            token_id=signal.target_token_id,
            side=side,
            price=ref_price,
            size=size,
            expiration=default_expiration(5),
            mode=self.guard.mode,
        )

        # Fill-Tiefe Commit 1: Signal-Ref + Staleness-Preflight (vor Match).
        # match()/_cross bleiben unangetastet — Simulator steht daneben.
        self._fill_sim.register_signal_ref(order.order_id, signal.suggested_price)
        stale_reason = self._preflight_staleness(signal, active, now=time.time())
        if stale_reason is not None:
            record = TelemetryRecord(
                signal_id=signal.signal_id, order_id=order.order_id,
                latency_ms=self._elapsed_ms(t0), approved=False,
                reject_reason=stale_reason, status=None,
                requested_size=requested_size, decision_seq=decision_seq,
            )
            self.telemetry.log(record)
            return self._report(signal, record)

        decision = self.risk.check(order, self.portfolio, marks)
        if not decision.approved:
            order = order.model_copy(update={"status": OrderStatus.REJECTED_BY_RISK, "reject_reason": decision.reason})
            self._order_book[order.order_id] = order
            record = TelemetryRecord(
                signal_id=signal.signal_id, order_id=order.order_id,
                latency_ms=self._elapsed_ms(t0), approved=False,
                reject_reason=decision.reason, status=order.status,
                requested_size=requested_size, decision_seq=decision_seq,
            )
            self.telemetry.log(record)
            return self._report(signal, record)

        match = self.matcher.match(
            order, active,
            signal_id=signal.signal_id,
            market_id=signal.market_id,
            requested_size=requested_size,
            decision_seq=decision_seq,
        )
        order = order.model_copy(update={"status": match.status})
        for fill in match.fills:
            self.portfolio.apply_fill(order, fill, market_id=signal.market_id)
            self._journal_fill(
                order,
                signal_id=signal.signal_id,
                market_id=signal.market_id,
                fill=fill,
            )
        if match.fills:
            self._record_peak(marks)
            self._fills_by_order[order.order_id] = list(match.fills)
        self._order_book[order.order_id] = order

        record = TelemetryRecord(
            signal_id=signal.signal_id, order_id=order.order_id,
            latency_ms=self._elapsed_ms(t0), approved=True,
            reject_reason=RejectReason.NONE, status=order.status,
            requested_size=requested_size, decision_seq=decision_seq,
            fill_metrics=match.fill_metrics,
        )
        self.telemetry.log(record)
        return self._report(signal, record, match)

    def on_book_update(self, snapshot: MarketSnapshot) -> list[TelemetryRecord]:
        """Ruhende Nachwertung -> Portfolio -> Telemetrie (decision_seq hoch).

        Speichert zuerst den Hub-/Feed-Snapshot (Mark-Cache). Jede Nachwertung
        einer ruhenden GTC-Order schreibt einen neuen ``TelemetryRecord``
        (gleiche ``order_id``, neues ``decision_seq``). ``latency_ms=0.0``:
        Buch-zu-Fill, nicht Signal-zu-Fill.

        Telemetrie wird immer geschrieben: Fehlt ``signal_id`` im Matcher-
        Register, greift der Fallback ``order.signal_id`` (wie beim Journal).
        """
        self.guard.assert_safe()
        self._store_snapshot(snapshot)
        records: list[TelemetryRecord] = []
        for ev in self.matcher.on_book_update(snapshot):
            order = self._order_book.get(ev.order_id)
            if order is None:
                continue
            order = order.model_copy(update={"status": ev.result.status})
            market_id = ev.market_id or "unknown"
            # Journal immer: Matcher-Seam kann signal_id=None haben; Order
            # traegt die kanonische UUID (sonst Live/Journal-Divergenz).
            sid = ev.signal_id or order.signal_id
            for fill in ev.result.fills:
                self.portfolio.apply_fill(order, fill, market_id=market_id)
                self._journal_fill(
                    order,
                    signal_id=sid,
                    market_id=market_id,
                    fill=fill,
                )
            self._order_book[ev.order_id] = order
            if ev.result.fills:
                bucket = self._fills_by_order.setdefault(ev.order_id, [])
                bucket.extend(ev.result.fills)
                # Mid-Mark-Cache (wie _store_snapshot), nicht best_ask/bid allein
                self._record_peak(self._mark_prices)
            rec = TelemetryRecord(
                signal_id=sid,
                order_id=ev.order_id,
                latency_ms=0.0,
                approved=True,
                reject_reason=RejectReason.NONE,
                status=order.status,
                requested_size=ev.requested_size,
                decision_seq=self.telemetry.next_decision_seq(),
                fill_metrics=ev.result.fill_metrics,
            )
            self.telemetry.log(rec)
            records.append(rec)
        return records

    def reap_expired(self, now: Optional[datetime] = None) -> list[TelemetryRecord]:
        """RESTING/offen -> EXPIRED. Takt-Produzent = Hub/Cron/Test.

        Register-Exit ohne Fill: kein Cash-Effekt, kein Reject. Kein
        Auto-Resubmit — Folge-GTC ist ein neuer ``match``-Aufruf des Hubs.
        Mit Default-``expiration`` ist jede ruhende GTC faktisch GTD, sobald
        dieser Pfad getickt wird.

        Zweite Schleife: nur ``register_order``-IDs. Match-/FAK-Terminals
        (z. B. PARTIALLY_FILLED ohne Resting) bleiben unberuehrt.
        """
        now = now or datetime.now(timezone.utc)
        records: list[TelemetryRecord] = []
        expired_orders: list[PaperOrder] = []
        handled: set[uuid.UUID] = set()

        for exp in self.matcher.reap_expired(now):
            order = self._order_book.get(exp.order_id)
            if order is None:
                continue
            order = order.model_copy(update={"status": OrderStatus.EXPIRED})
            self._order_book[exp.order_id] = order
            handled.add(exp.order_id)
            expired_orders.append(order)
            sid = exp.signal_id or order.signal_id
            rec = TelemetryRecord(
                signal_id=sid,
                order_id=exp.order_id,
                latency_ms=0.0,
                approved=True,  # risiko-genehmigt; Verfall ist Lebenszyklus
                reject_reason=RejectReason.NONE,
                status=OrderStatus.EXPIRED,
                requested_size=exp.requested_size,
                decision_seq=self.telemetry.next_decision_seq(),
            )
            self.telemetry.log(rec)
            records.append(rec)

        # Nur register_order-Pfad (Hub), nie Match-/FAK-Abschluesse
        _OPEN = frozenset({
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.RESTING,
        })
        for oid in list(self._registered_only):
            if oid in handled:
                self._registered_only.discard(oid)
                continue
            order = self._order_book.get(oid)
            if order is None or order.status not in _OPEN:
                self._registered_only.discard(oid)
                continue
            if order.expiration > now:
                continue
            updated = order.model_copy(update={"status": OrderStatus.EXPIRED})
            self._order_book[oid] = updated
            self._registered_only.discard(oid)
            expired_orders.append(updated)
            rec = TelemetryRecord(
                signal_id=order.signal_id,
                order_id=order.order_id,
                latency_ms=0.0,
                approved=True,
                reject_reason=RejectReason.NONE,
                status=OrderStatus.EXPIRED,
                requested_size=order.size,
                decision_seq=self.telemetry.next_decision_seq(),
            )
            self.telemetry.log(rec)
            records.append(rec)

        self._last_expired_orders = tuple(expired_orders)
        return records

    def preview(self, signal: SignalPayload, snapshot: MarketSnapshot) -> Decimal:
        """Slippage-Preview für ein Signal OHNE Orderausführung.

        Args:
            signal: SignalPayload.
            snapshot: Marktschnappschuss.

        Returns:
            Erwartete Slippage in bps.
        """
        side = signal.resolved_side()
        if side is None:
            return Decimal("0")
        price = snapshot.best_ask() if side == OrderSide.BUY else snapshot.best_bid()
        if price is None:
            return Decimal("0")
        probe = PaperOrder(
            signal_id=signal.signal_id,
            token_id=signal.target_token_id,
            side=side,
            price=price,
            size=Decimal("1"),
            expiration=default_expiration(1),
            mode=self.guard.mode,
        )
        return self.matcher.preview_slippage(probe, snapshot)

    def performance_summary(self) -> dict[str, object]:
        """Aggregiertes Performance-Reporting.

        Returns:
            Dict mit Telemetrie-Stats, Equity, Realized PnL, Lockout-Status.
        """
        marks = {tid: p.avg_entry_price for tid, p in self.portfolio.positions.items()}
        return {
            "telemetry": self.telemetry.stats(),
            "reject_rate": self.telemetry.reject_rate(),
            "cash": str(self.portfolio.cash),
            "equity": str(self.portfolio.equity(marks)),
            "realized_pnl": str(self.portfolio.realized_pnl),
            "peak_equity": str(self.portfolio.peak_equity),
            "peak_events": len(self._peak_events),
            "open_positions": len(self.portfolio.positions),
            "lockout_active": self.risk.lockout_active,
            "mode": self.guard.mode.value,
        }

    @staticmethod
    def _elapsed_ms(t0: float) -> float:
        """Berechnet verstrichene Millisekunden seit t0 (perf_counter)."""
        return (time.perf_counter() - t0) * 1000.0
