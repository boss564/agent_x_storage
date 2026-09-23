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
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict

from order_execution_engine.models import (
    Direction,
    ExecutionMode,
    ExecutionReport,
    FillResult,
    MockEIP712Signature,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
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
        if self._lockout_active:
            return RiskDecision.reject(RejectReason.DRAWDOWN_LOCKOUT)
        if portfolio.current_drawdown_pct(mark_prices) >= self.config.max_drawdown_pct:
            self._lockout_active = True
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
    """

    status: OrderStatus
    fills: tuple[FillResult, ...]
    avg_execution_price: Optional[Decimal]
    total_slippage_bps: Decimal
    remaining_size: Decimal


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


class PaperMatchEngine:
    """Fill- und Slippage-Simulation via Buch-Walk gegen Orderbuch-Tiefe.

    BUY-Orders laufen gegen die Ask-Seite, SELL-Orders gegen die Bid-Seite.
    Ein Fill tritt nur ein, wenn das Limit greift (BUY: ask <= limit,
    SELL: bid >= limit).

    FAK: Rest wird verworfen (zustandslos). GTC: Rest ruht in ``_resting``
    und wird bei ``on_book_update`` nachgewertet.
    """

    def __init__(self, fee_bps: Decimal = Decimal("0"), max_slippage_bps: Optional[Decimal] = None) -> None:
        """Initialisiert die Match-Engine.

        Args:
            fee_bps: Simulierte Gebühr pro Fill in Basispunkten.
            max_slippage_bps: Optionales Slippage-Limit; darüber wird
                die Order nicht ausgeführt (Reject).
        """
        self.fee_bps = fee_bps
        self.max_slippage_bps = max_slippage_bps
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
            return self._match_fak(order, snapshot)
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

    def _cross(
        self, order: PaperOrder, snapshot: MarketSnapshot, size: Decimal,
    ) -> tuple[list[FillResult], Decimal, Decimal]:
        """Kreuzt ``size`` gegen sichtbare Tiefe (Bestand-Walk 1:1).

        Returns:
            (fills, remaining, reference_for_total) — reference für Slippage-bps.
        """
        levels = snapshot.asks if order.side == OrderSide.BUY else snapshot.bids
        remaining = size
        fills: list[FillResult] = []
        notional_sum = Decimal("0")
        volume_sum = Decimal("0")
        reference_price = order.price
        for _lvl in levels:
            if _lvl.price > 0 and _lvl.size > 0:
                reference_price = _lvl.price
                break
        reference_for_total = reference_price

        for level in levels:
            if remaining <= 0:
                break
            if level.price <= 0 or level.size <= 0:
                continue
            if order.side == OrderSide.BUY and level.price > order.price:
                break
            if order.side == OrderSide.SELL and level.price < order.price:
                break
            executed = min(remaining, level.size)
            slip = level.price - reference_price
            if order.side == OrderSide.SELL:
                slip = -slip
            slip_bps = (slip / reference_price) * Decimal("10000")
            if self.max_slippage_bps is not None and slip_bps > self.max_slippage_bps:
                break
            reference_price = level.price
            fee = (level.price * executed) * self.fee_bps / Decimal("10000")
            fills.append(FillResult(
                order_id=order.order_id,
                execution_price=level.price,
                executed_size=executed,
                slippage=slip,
                fee=fee,
            ))
            notional_sum += level.price * executed
            volume_sum += executed
            remaining -= executed

        return fills, remaining, reference_for_total

    def _build_result(
        self,
        fills: list[FillResult],
        remaining: Decimal,
        reference_for_total: Decimal,
        *,
        idle_status: OrderStatus,
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
        )

    def _match_fak(self, order: PaperOrder, snapshot: MarketSnapshot) -> MatchResult:
        """FAK: heutiger Pfad — Rest verworfen, idle = PENDING."""
        fills, remaining, ref = self._cross(order, snapshot, order.size)
        return self._build_result(
            fills, remaining, ref, idle_status=OrderStatus.PENDING,
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
        fills, remaining, ref = self._cross(order, snapshot, order.size)
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
        return self._build_result(
            fills, remaining, ref, idle_status=OrderStatus.RESTING,
        )

    def on_book_update(self, snapshot: MarketSnapshot) -> list[RestingEvaluation]:
        """Nachwertung ruhender GTC-Orders gegen neuen Snapshot."""
        out: list[RestingEvaluation] = []
        for oid, resting in list(self._resting.items()):
            if resting.order.token_id != snapshot.token_id:
                continue
            fills, remaining, ref = self._cross(
                resting.order, snapshot, resting.remaining_size,
            )
            resting.remaining_size = remaining
            result = self._build_result(
                fills, remaining, ref, idle_status=OrderStatus.RESTING,
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
        """
        self.guard = SafetyGuard(mode=mode)
        self.risk = RiskController(risk_config or RiskConfig())
        self.matcher = PaperMatchEngine(fee_bps=(risk_config or RiskConfig()).fee_bps)
        self.portfolio = VirtualPortfolio()
        self.telemetry = telemetry or TelemetryLogger()
        self.invert_weak_signals = invert_weak_signals
        self.confidence_threshold = confidence_threshold
        self.size_fn: SizeFn = size_fn or self._default_size_fn
        self._order_book: dict[uuid.UUID, PaperOrder] = {}

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

    def on_signal(self, signal: SignalPayload, snapshot: MarketSnapshot) -> ExecutionReport:
        """Verarbeitet ein eingehendes Signal komplett (Signal -> Fill).

        Intern wird weiter ein ``TelemetryRecord`` geloggt (Persistenz-
        Boundary). Rueckgabe ist das Hub-DTO ``ExecutionReport``
        (Komposition, kein Ersatz).

        Args:
            signal: SignalPayload aus dem NewsBot.
            snapshot: Aktueller Marktschnappschuss aus PolySentinel.

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

        # Preis: Limit auf bestem verfügbaren Level setzen
        ref_price = snapshot.best_ask() if side == OrderSide.BUY else snapshot.best_bid()
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
        portfolio_snapshot = self.portfolio.snapshot(
            mark_prices={signal.target_token_id: ref_price},
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

        decision = self.risk.check(order, self.portfolio, {signal.target_token_id: ref_price})
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
            order, snapshot,
            signal_id=signal.signal_id,
            market_id=signal.market_id,
            requested_size=requested_size,
            decision_seq=decision_seq,
        )
        order = order.model_copy(update={"status": match.status})
        for fill in match.fills:
            self.portfolio.apply_fill(order, fill, market_id=signal.market_id)
        if match.fills:
            self.portfolio.update_peak_equity({signal.target_token_id: ref_price})
        self._order_book[order.order_id] = order

        record = TelemetryRecord(
            signal_id=signal.signal_id, order_id=order.order_id,
            latency_ms=self._elapsed_ms(t0), approved=True,
            reject_reason=RejectReason.NONE, status=order.status,
            requested_size=requested_size, decision_seq=decision_seq,
        )
        self.telemetry.log(record)
        return self._report(signal, record, match)

    def on_book_update(self, snapshot: MarketSnapshot) -> list[TelemetryRecord]:
        """Ruhende Nachwertung -> Portfolio -> Telemetrie (decision_seq hoch).

        Jede Nachwertung einer ruhenden GTC-Order schreibt einen neuen
        ``TelemetryRecord`` (gleiche ``order_id``, neues ``decision_seq``).
        ``latency_ms=0.0``: Buch-zu-Fill, nicht Signal-zu-Fill (Schema-
        Folgeticket, falls Unterscheidung noetig).
        """
        records: list[TelemetryRecord] = []
        mark = snapshot.best_ask() or snapshot.best_bid()
        for ev in self.matcher.on_book_update(snapshot):
            order = self._order_book.get(ev.order_id)
            if order is None:
                continue
            order = order.model_copy(update={"status": ev.result.status})
            for fill in ev.result.fills:
                self.portfolio.apply_fill(
                    order, fill, market_id=ev.market_id or "unknown",
                )
            self._order_book[ev.order_id] = order
            if ev.result.fills and mark is not None:
                self.portfolio.update_peak_equity({order.token_id: mark})
            if ev.signal_id is None:
                continue  # ohne Signal-Kontext keine Telemetrie (Test-Seam)
            rec = TelemetryRecord(
                signal_id=ev.signal_id,
                order_id=ev.order_id,
                latency_ms=0.0,
                approved=True,
                reject_reason=RejectReason.NONE,
                status=order.status,
                requested_size=ev.requested_size,
                decision_seq=self.telemetry.next_decision_seq(),
            )
            self.telemetry.log(rec)
            records.append(rec)
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
            "open_positions": len(self.portfolio.positions),
            "lockout_active": self.risk.lockout_active,
            "mode": self.guard.mode.value,
        }

    @staticmethod
    def _elapsed_ms(t0: float) -> float:
        """Berechnet verstrichene Millisekunden seit t0 (perf_counter)."""
        return (time.perf_counter() - t0) * 1000.0
