"""Datenmodelle und Safety-Guard für die Shadow Execution Engine.

Dieses Modul definiert die typsicheren Pydantic-Modelle für Signale,
Paper-Orders, Fills, virtuelles Portfolio und Risikokonfiguration sowie
den unumgehbaren SafetyGuard, der die Charter
(diagnostic_only=true, live_execution=false, order_send=false)
durchsetzt.

Härtung (v0.2):
    - SafetyGuard ist manipulationssicher (Flags nach Init unveränderbar).
    - PaperOrder validiert Expiration (abgelaufene Orders werden abgelehnt).
    - OrderStatus um EXPIRED erweitert (vollständiger Lebenszyklus).
    - VirtualPortfolio kann Fills selbständig verarbeiten (apply_fill)
      und führt peak_equity für den Drawdown-Lockout.

Hinweis: Das Modul enthält KEINE Netzwerk-Calls. Jeglicher Versuch,
echte Order-Aussendungen auszulösen, führt zu einem harten Abbruch.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


# ---------------------------------------------------------------------------
# Konstanten: Charter (hart verdrahtet, nicht via Env überschreibbar)
# ---------------------------------------------------------------------------

DIAGNOSTIC_ONLY: Literal[True] = True
LIVE_EXECUTION: Literal[False] = False
ORDER_SEND: Literal[False] = False

DEFAULT_VIRTUAL_CASH: Decimal = Decimal("10000.00")  # 10.000 virtuelles USDC
DEFAULT_MAX_POSITION_SIZE: Decimal = Decimal("500.00")  # Max. $ pro Position
DEFAULT_MAX_EVENT_EXPOSURE: Decimal = Decimal("1000.00")  # Max. $ pro Event
DEFAULT_DRAWDOWN_LIMIT_PCT: Decimal = Decimal("10.0")  # 10 % Drawdown-Lockout
DEFAULT_FEE_BPS: Decimal = Decimal("0.0")  # Gebühren in Basispunkten (taker=0 auf Polymarket)


# ---------------------------------------------------------------------------
# Validatoren
# ---------------------------------------------------------------------------

PolymarketPrice = Annotated[
    Decimal,
    Field(gt=Decimal("0.0"), lt=Decimal("1.0"), description="Limitpreis 0 < p < 1 (Wahrscheinlichkeit)."),
]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"), description="Strikt positiver Dezimalwert.")]
ProbabilityPct = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"), description="Prozent 0–100.")]


def _utcnow() -> datetime:
    """Gibt den aktuellen UTC-Timestamp zurück (timezone-aware)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 1. Enums & Flags
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    """Betriebsmodus der Engine. DRY_RUN ist der einzige produktiv zulässige Modus."""

    DRY_RUN = "DRY_RUN"
    PAPER_TRADING = "PAPER_TRADING"
    DISABLED = "DISABLED"


class OrderStatus(str, Enum):
    """Lebenszyklus-Status einer Paper-Order."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED_BY_RISK = "REJECTED_BY_RISK"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderSide(str, Enum):
    """Orderseite (BUY/SELL auf CLOB-Token)."""

    BUY = "BUY"
    SELL = "SELL"


class Direction(str, Enum):
    """Signal-Richtung des NewsBots."""

    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


class RejectReason(str, Enum):
    """Begründung für Risiko-Ablehnungen (Telemetrie)."""

    NONE = "NONE"
    MAX_POSITION_SIZE = "MAX_POSITION_SIZE"
    MAX_EVENT_EXPOSURE = "MAX_EVENT_EXPOSURE"
    DRAWDOWN_LOCKOUT = "DRAWDOWN_LOCKOUT"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INVALID_PRICE = "INVALID_PRICE"
    EXPIRED = "EXPIRED"
    SAFETY_GUARD = "SAFETY_GUARD"


# ---------------------------------------------------------------------------
# 2. Order & Signal Payloads
# ---------------------------------------------------------------------------


class SignalPayload(BaseModel):
    """Eingehendes News-/Handelssignal aus dem NewsBot.

    Attribute:
        signal_id: Eindeutige Signal-ID (UUID, vom NewsBot vergeben).
        source: Herkunftskomponente (z. B. "newsbot", "manual").
        target_token_id: Polymarket CLOB Token-ID (ERC-1155, hex).
        market_id: Zugehörige Markt-/Event-ID für Exposure-Checks.
        direction: Signal-Richtung (UP/DOWN/NEUTRAL).
        confidence: Modell-Konfidenz in Prozent (0–100).
        suggested_price: Optionaler Referenzpreis des Signals (0 < p < 1).
        timestamp: UTC-Eingangszeit des Signals.
        invert: Inversions-Flag (schwache Signale als Kontra-Indikator).
    """

    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    signal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str = Field(default="newsbot", max_length=64)
    target_token_id: str = Field(min_length=1, max_length=128)
    market_id: str = Field(min_length=1, max_length=128)
    direction: Direction
    confidence: ProbabilityPct = Field(description="Konfidenz 0–100 (%).")
    suggested_price: Optional[PolymarketPrice] = Field(default=None)
    timestamp: datetime = Field(default_factory=_utcnow)
    invert: bool = Field(default=False, description="Signal invertieren (Kontra-Indikator).")

    def resolved_side(self) -> Optional[OrderSide]:
        """Ermittelt die effektive Orderseite inkl. Inversions-Logik.

        Returns:
            OrderSide.BUY bei UP, OrderSide.SELL bei DOWN; None bei NEUTRAL.
            Das invert-Flag kehrt BUY/SELL um.
        """
        if self.direction == Direction.NEUTRAL:
            return None
        side = OrderSide.BUY if self.direction == Direction.UP else OrderSide.SELL
        if self.invert:
            side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
        return side


class PaperOrder(BaseModel):
    """Polymarket-CLOB-konforme Paper-Order (kein Netzwerk-Versand!).

    Attribute:
        order_id: Eindeutige Order-ID (intern generiert).
        signal_id: Referenz auf das auslösende Signal.
        token_id: Polymarket CLOB Token-ID.
        side: BUY oder SELL.
        price: Limitpreis (0 < p < 1).
        size: Ordergröße in Shares.
        expiration: ISO-Expiration (CLOB-Feld, nur formatprüfend).
        status: Aktueller Order-Status.
        created_at: Erzeugungszeitpunkt (UTC).
        mode: Ausführungsmodus (immer DRY_RUN/PAPER_TRADING).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    order_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    signal_id: uuid.UUID
    token_id: str = Field(min_length=1, max_length=128)
    side: OrderSide
    price: PolymarketPrice = Field(description="Limitpreis 0 < p < 1.")
    size: PositiveDecimal = Field(description="Ordergröße in Shares.")
    expiration: datetime
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    mode: ExecutionMode = Field(default=ExecutionMode.DRY_RUN)
    created_at: datetime = Field(default_factory=_utcnow)
    reject_reason: RejectReason = Field(default=RejectReason.NONE)

    @property
    def notional(self) -> Decimal:
        """Rechnet price * size in USDC-Notional um."""
        return (self.price * self.size).quantize(Decimal("0.000001"))

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Prüft, ob die Order abgelaufen ist.

        Args:
            now: Referenzzeitpunkt (Default: aktuelle UTC-Zeit).

        Returns:
            True, wenn expiration erreicht/überschritten wurde.
        """
        ref = now or _utcnow()
        return ref >= self.expiration

    @model_validator(mode="after")
    def _enforce_dry_run(self) -> "PaperOrder":
        """Verhindert, dass Orders außerhalb erlaubter Dry-Run-Modi existieren."""
        if self.mode == ExecutionMode.DISABLED:
            raise PermissionError("ExecutionMode.DISABLED: keine Order-Instanzen erlaubt.")
        if self.expiration <= self.created_at:
            raise ValueError("Order abgelehnt: expiration muss in der Zukunft liegen.")
        return self


class MockEIP712Signature(BaseModel):
    """Dummy-EIP-712-Signaturstruktur (nur Formatprüfung, kein echtes Signing).

    Attribute:
        signature_type: CLOB-Signaturtyp (0=EOA, 1=Magic-Link, 2=Browser-Wallet).
        r, s: Signatur-Komponenten (hex, Dummy-Werte).
        v: Recovery-ID (27/28).
        domain_verifying_contract: Dummy-Verifier-Adresse.
        is_mock: Muss immer True sein — markiert nicht-signierte Dummy-Daten.
    """

    model_config = ConfigDict(frozen=True)

    signature_type: Literal[0, 1, 2] = Field(default=0)
    r: str = Field(default="0x" + "00" * 32, pattern=r"^0x[0-9a-fA-F]{64}$")
    s: str = Field(default="0x" + "00" * 32, pattern=r"^0x[0-9a-fA-F]{64}$")
    v: Literal[27, 28] = Field(default=27)
    domain_verifying_contract: str = Field(default="0x" + "00" * 20, pattern=r"^0x[0-9a-fA-F]{40}$")
    is_mock: Literal[True] = True

    @classmethod
    def mock(cls) -> "MockEIP712Signature":
        """Erzeugt eine valide Dummy-Signatur für Format-Checks."""
        return cls()


class FillResult(BaseModel):
    """Ergebnis einer simulierten Fill-Ausführung.

    Attribute:
        order_id: Zugehörige Paper-Order.
        execution_price: Tatsächlich simulierter Ausführungspreis.
        executed_size: Tatsächlich ausgeführte Share-Menge.
        slippage: Preisverschiebung vs. Limit (positiv = Nachteil).
        fee: Simulierte Gebühr in USDC.
        filled_at: Zeitpunkt der simulierten Ausführung.
        latency_ms: Latenz Signal-Eingang bis virtuelle Ausführung.
    """

    model_config = ConfigDict(frozen=True)

    order_id: uuid.UUID
    execution_price: PolymarketPrice
    executed_size: PositiveDecimal
    slippage: Decimal = Field(default=Decimal("0"))
    fee: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    filled_at: datetime = Field(default_factory=_utcnow)
    latency_ms: Optional[float] = Field(default=None, ge=0.0)


# ---------------------------------------------------------------------------
# 3. Portfolio & Risk Models
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """Offene virtuelle Position pro Token.

    Attribute:
        token_id: CLOB Token-ID.
        market_id: Zugehöriges Event (für Exposure-Aggregation).
        side: Netto-Richtung der Position.
        avg_entry_price: Gewichteter Durchschnittseinstieg.
        size: Aktuelle Positionsgröße in Shares.
        realized_pnl: Realisierter PnL dieser Position.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    token_id: str = Field(min_length=1, max_length=128)
    market_id: str = Field(min_length=1, max_length=128)
    side: OrderSide
    avg_entry_price: PolymarketPrice
    size: PositiveDecimal
    realized_pnl: Decimal = Field(default=Decimal("0"))

    def add_shares(self, additional_size: Decimal, price: Decimal) -> None:
        """Erhöht die Position und aktualisiert den gewichteten Entry.

        Args:
            additional_size: Zugekaufte Shares (> 0).
            price: Kaufpreis (0 < p < 1).
        """
        if additional_size <= 0:
            raise ValueError("additional_size muss positiv sein.")
        total = self.size + additional_size
        self.avg_entry_price = ((self.avg_entry_price * self.size) + (price * additional_size)) / total
        self.size = total

    def reduce_shares(self, closed_size: Decimal, price: Decimal) -> Decimal:
        """Reduziert die Position und realisiert PnL (Durchschnittskostenmethode).

        FESTLEGUNG (GoBD-relevant, dokumentierte Kostenmethode): Realisierter
        PnL wird gegen den gewichteten Durchschnittseinstieg gerechnet
        (§ 256 HGB analog, permanente Verfahrenswahl). Für Steuerzwecke kann
        FIFO abweichen — bei Umstellung auf FIFO sind Lots pro Position
        erforderlich (höherer Zustands- und Testaufwand).

        Args:
            closed_size: Geschlossene Shares (> 0, <= size).
            price: Verkaufspreis (0 < p < 1).

        Returns:
            Realisierter PnL des Anteils in USDC.
        """
        if closed_size <= 0 or closed_size > self.size:
            raise ValueError("closed_size muss in (0, size] liegen.")
        realized = (price - self.avg_entry_price) * closed_size
        self.size -= closed_size
        self.realized_pnl += realized
        return realized


class VirtualPortfolio(BaseModel):
    """Virtuelles Portfolio (Paper-Trading, kein echtes Geld).

    Attribute:
        cash: Verfügbares virtuelles USDC-Guthaben.
        start_balance: Anfangsguthaben (Default 10.000 USDC).
        positions: Offene Positionen (Schlüssel: token_id).
        realized_pnl: Kumulierter realisierter PnL.
        peak_equity: Höchststand des Eigenkapitals (Drawdown-Basis).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    cash: Decimal = Field(default=DEFAULT_VIRTUAL_CASH, ge=Decimal("0"))
    start_balance: Decimal = Field(default=DEFAULT_VIRTUAL_CASH, gt=Decimal("0"))
    positions: dict[str, Position] = Field(default_factory=dict)
    realized_pnl: Decimal = Field(default=Decimal("0"))
    peak_equity: Decimal = Field(default=DEFAULT_VIRTUAL_CASH)

    def equity(self, mark_prices: dict[str, Decimal]) -> Decimal:
        """Berechnet Eigenkapital = Cash + marktwertbewertete Positionen.

        Args:
            mark_prices: Aktuelle Preise pro token_id (0 < p < 1).

        Returns:
            Gesamtes virtuelles Eigenkapital in USDC.
        """
        unrealized = Decimal("0")
        for token_id, pos in self.positions.items():
            mark = mark_prices.get(token_id)
            if mark is None:
                mark = pos.avg_entry_price
            unrealized += pos.size * mark
        return self.cash + unrealized

    def update_peak_equity(self, mark_prices: dict[str, Decimal]) -> Decimal:
        """Aktualisiert peak_equity nach oben (für Drawdown-Basis).

        Args:
            mark_prices: Aktuelle Preise pro token_id.

        Returns:
            Neuer (oder bestehender) peak_equity-Wert.
        """
        eq = self.equity(mark_prices)
        if eq > self.peak_equity:
            self.peak_equity = eq
        return self.peak_equity

    def current_drawdown_pct(self, mark_prices: dict[str, Decimal]) -> Decimal:
        """Berechnet Drawdown in Prozent gegenüber peak_equity.

        Args:
            mark_prices: Aktuelle Preise pro token_id.

        Returns:
            Drawdown in Prozent (0 wenn Equity >= Peak).
        """
        self.update_peak_equity(mark_prices)
        eq = self.equity(mark_prices)
        if eq >= self.peak_equity:
            return Decimal("0")
        return ((self.peak_equity - eq) / self.peak_equity) * Decimal("100")

    def exposure_per_market(self) -> dict[str, Decimal]:
        """Aggregiert notionale Exposure je market_id.

        Returns:
            Mapping market_id -> notional USDC.
        """
        result: dict[str, Decimal] = {}
        for pos in self.positions.values():
            notional = pos.size * pos.avg_entry_price
            result[pos.market_id] = result.get(pos.market_id, Decimal("0")) + notional
        return result

    def apply_fill(self, order: PaperOrder, fill: FillResult, market_id: str) -> Decimal:
        """Verbucht einen simulierten Fill auf Cash, Position und PnL.

        Args:
            order: Die (Teil-)ausgeführte Paper-Order.
            fill: Das FillResult mit execution_price und executed_size.
            market_id: Zugehörige Event-ID (für die neue Position nötig).

        Returns:
            Realisierter PnL dieses Fills (0 bei reiner Eröffnung).

        Raises:
            ValueError: Wenn Cash für einen Kauf nicht ausreicht.
        """
        if fill.order_id != order.order_id:
            raise ValueError("fill.order_id passt nicht zur übergebenen Order.")
        cost = fill.execution_price * fill.executed_size
        realized = Decimal("0")

        if order.side == OrderSide.BUY:
            total_cost = cost + fill.fee
            if total_cost > self.cash:
                raise ValueError(f"INSUFFICIENT_CASH: benötigt {total_cost}, vorhanden {self.cash}.")
            self.cash -= total_cost
            pos = self.positions.get(order.token_id)
            if pos is None:
                self.positions[order.token_id] = Position(
                    token_id=order.token_id,
                    market_id=market_id,
                    side=OrderSide.BUY,
                    avg_entry_price=fill.execution_price,
                    size=fill.executed_size,
                )
            else:
                pos.add_shares(fill.executed_size, fill.execution_price)
        else:  # SELL
            self.cash += cost - fill.fee
            pos = self.positions.get(order.token_id)
            if pos is None:
                raise ValueError("SELL-Fill ohne offene Position.")
            realized = pos.reduce_shares(fill.executed_size, fill.execution_price)
            self.realized_pnl += realized
            if pos.size == 0:
                del self.positions[order.token_id]
        return realized


class RiskConfig(BaseModel):
    """Pre-Trade-Risikoparameter.

    Attribute:
        max_position_size_usdc: Max. Notional pro Einzelposition.
        max_event_exposure_usdc: Max. kumuliertes Notional pro Event.
        max_drawdown_pct: Drawdown-Schwelle für Lockout (z. B. 10 %).
        max_order_size_shares: Max. Ordergröße in Shares.
        fee_bps: Simulierte Gebühr in Basispunkten.
        slippage_bps: Baseline-Slippage in Basispunkten.
    """

    model_config = ConfigDict(frozen=True)

    max_position_size_usdc: PositiveDecimal = Field(default=DEFAULT_MAX_POSITION_SIZE)
    max_event_exposure_usdc: PositiveDecimal = Field(default=DEFAULT_MAX_EVENT_EXPOSURE)
    max_drawdown_pct: ProbabilityPct = Field(default=DEFAULT_DRAWDOWN_LIMIT_PCT)
    max_order_size_shares: PositiveDecimal = Field(default=Decimal("1000.0"))
    fee_bps: Decimal = Field(default=DEFAULT_FEE_BPS, ge=Decimal("0"))
    slippage_bps: Decimal = Field(default=Decimal("5.0"), ge=Decimal("0"))


# ---------------------------------------------------------------------------
# 4. Hardcoded Guard Rail
# ---------------------------------------------------------------------------


class _CharterMeta(type):
    """Metaklasse, die Charter-Flags im Klassen-Namespace sperrt.

    Ohne diese Sperre könnte `SafetyGuard.live_execution = True` die Klasse
    selbst manipulieren. Instanzen gewinnen zwar weiterhin über `__init__`,
    aber die Klasse bliebe als Angriffsfläche bestehen.
    """

    def __setattr__(cls, name: str, value: object) -> None:  # noqa: N805
        if name in SafetyGuard._IMMUTABLE_ATTRS:
            raise PermissionError(
                f"order_send=false Charter-Verletzung: Klassen-Attribut "
                f"'{name}' ist unveränderbar."
            )
        super().__setattr__(name, value)


class SafetyGuard(metaclass=_CharterMeta):
    """Unumgehbare Charter-Enforcement-Klasse.

    Durchsetzung von diagnostic_only=true, live_execution=false,
    order_send=false. Jede Code-Stelle, die potenziell Netzwerk-Calls an
    Orderbook-Relayer auslösen könnte, MUSS zuvor `SafetyGuard.assert_safe()`
    aufrufen. Der Guard ist zustandslos, manipulationssicher
    (Flags nach Initialisierung unveränderbar) und kann nicht deaktiviert
    werden.
    """

    _ALLOWED_MODES: frozenset[ExecutionMode] = frozenset(
        {ExecutionMode.DRY_RUN, ExecutionMode.PAPER_TRADING}
    )
    _IMMUTABLE_ATTRS: frozenset[str] = frozenset(
        {"diagnostic_only", "live_execution", "order_send", "mode"}
    )

    def __init__(self, mode: ExecutionMode = ExecutionMode.DRY_RUN) -> None:
        """Initialisiert den Guard (hart verdrahtete Charter-Werte).

        Args:
            mode: Startmodus (Default DRY_RUN). Nicht-erlaubte Modi
                werden sofort mit PermissionError abgelehnt.
        """
        object.__setattr__(self, "diagnostic_only", DIAGNOSTIC_ONLY)
        object.__setattr__(self, "live_execution", LIVE_EXECUTION)
        object.__setattr__(self, "order_send", ORDER_SEND)
        object.__setattr__(self, "mode", mode)
        if mode not in self._ALLOWED_MODES:
            raise PermissionError("order_send=false Charter-Verletzung: unerlaubter Initial-Modus.")

    def __setattr__(self, name: str, value: object) -> None:
        """Blockiert nachträgliche Änderungen an Charter-Flags.

        Raises:
            PermissionError: Bei jedem Schreibzugriff auf ein geschütztes Attribut.
        """
        if name in self._IMMUTABLE_ATTRS:
            raise PermissionError(
                f"order_send=false Charter-Verletzung: '{name}' ist nach Init unveränderbar."
            )
        object.__setattr__(self, name, value)

    def assert_safe(self, mode: Optional[ExecutionMode] = None) -> None:
        """Prüft alle Charter-Flags; wirft bei Verletzung PermissionError.

        Args:
            mode: Optionaler Modus-Override zur Prüfung.

        Raises:
            PermissionError: Immer, wenn order_send/live_execution
                angefordert wird oder ein nicht-erlaubter Modus aktiv ist.
        """
        # Modul-Level-Werte haben Vorrang vor den eingefrorenen Instanz-Kopien.
        # Begründung: `m.LIVE_EXECUTION = True` (Monkeypatch am Modul) würde die
        # Instanz-Kopie nicht berühren und der Guard bliebe fälschlich grün.
        # Die Charter ist eine Eigenschaft des Moduls, nicht der Instanz.
        _mod = sys.modules[__name__]
        if _mod.ORDER_SEND is not False or self.order_send is not False:
            raise PermissionError("order_send=false Charter-Verletzung: Netzwerk-Versand blockiert.")
        if _mod.LIVE_EXECUTION is not False or self.live_execution is not False:
            raise PermissionError("order_send=false Charter-Verletzung: live_execution ist verboten.")
        if _mod.DIAGNOSTIC_ONLY is not True or self.diagnostic_only is not True:
            raise PermissionError("order_send=false Charter-Verletzung: diagnostic_only erforderlich.")
        active = mode or self.mode
        if active not in self._ALLOWED_MODES:
            raise PermissionError("order_send=false Charter-Verletzung: unerlaubter ExecutionMode.")

    @staticmethod
    def block_network_call(url: str, payload: Optional[BaseModel] = None) -> None:
        """Harter Abbruch jedes Netzwerk-Versands (z. B. Relayer REST-Call).

        Args:
            url: Ziel-URL des blockierten Calls (für Logging gedacht).
            payload: Optionales Payload-Objekt (wird nicht versendet).

        Raises:
            PermissionError: Immer — order_send=false.
        """
        _ = (url, payload)  # Explizit ungenutzt: kein Versand erfolgt.
        raise PermissionError(
            "order_send=false Charter-Verletzung: Netzwerk-Call an "
            f"'{url}' wurde hart blockiert. Diese Engine sendet niemals Orders."
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def default_expiration(minutes: int = 5) -> datetime:
    """Erzeugt einen Default-Expiration-Zeitpunkt (UTC).

    Args:
        minutes: Gültigkeitsdauer ab jetzt.

    Returns:
        Zeitpunkt jetzt + minutes.
    """
    return _utcnow() + timedelta(minutes=minutes)
