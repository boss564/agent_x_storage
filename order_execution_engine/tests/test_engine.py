"""Self-Tests für shadow_execution_engine (RiskController, PaperMatchEngine, Engine)."""

from decimal import Decimal

from order_execution_engine.market_data_feed import PolySentinelBookHandler, SnapshotCache
from order_execution_engine.models import (
    Direction,
    OrderSide,
    OrderStatus,
    RejectReason,
    RiskConfig,
    SafetyGuard,
    SignalPayload,
    default_expiration,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    PaperMatchEngine,
    PaperOrder,
    RiskController,
    ShadowExecutionEngine,
)


def _snapshot(asks=(), bids=(), token="0xtokenA") -> MarketSnapshot:
    return MarketSnapshot(token_id=token, asks=tuple(asks), bids=tuple(bids))


def _book() -> MarketSnapshot:
    return _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),
              OrderBookLevel(Decimal("0.62"), Decimal("300"))),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),
              OrderBookLevel(Decimal("0.58"), Decimal("250"))),
    )


def _order(side=OrderSide.BUY, price=Decimal("0.61"), size=Decimal("250"), token="0xtokenA") -> PaperOrder:
    return PaperOrder(
        signal_id=SignalPayload(target_token_id=token, market_id="mkt-1",
                                direction=Direction.UP, confidence=Decimal("70")).signal_id,
        token_id=token, side=side, price=price, size=size,
        expiration=default_expiration(5),
    )


def test_match_full_fill() -> None:
    m = PaperMatchEngine()
    r = m.match(_order(size=Decimal("200")), _book())  # passt in Ask-Stufe 1
    assert r.status == OrderStatus.FILLED
    assert r.avg_execution_price == Decimal("0.61")
    assert r.remaining_size == Decimal("0")
    assert r.total_slippage_bps == Decimal("0")
    print("OK test_match_full_fill")


def test_match_partial_fill() -> None:
    m = PaperMatchEngine()
    # Limit 0.62: walk über beide Stufen, 400 von 500 verfügbar
    r = m.match(_order(size=Decimal("400"), price=Decimal("0.62")), _book())
    assert r.status == OrderStatus.FILLED
    assert len(r.fills) == 2
    assert r.remaining_size == Decimal("0")
    assert r.avg_execution_price == Decimal("0.615")
    assert r.total_slippage_bps > Decimal("0")
    # Limit 0.61: nur Stufe 1 greift -> echte Partial Fill
    r2 = m.match(_order(size=Decimal("400"), price=Decimal("0.61")), _book())
    assert r2.status == OrderStatus.PARTIALLY_FILLED
    assert len(r2.fills) == 1
    assert r2.remaining_size == Decimal("200")
    print("OK test_match_partial_fill")


def test_match_limit_blocks() -> None:
    m = PaperMatchEngine()
    r = m.match(_order(price=Decimal("0.60")), _book())  # bester Ask 0.61 > Limit
    assert r.status == OrderStatus.PENDING
    assert not r.fills
    print("OK test_match_limit_blocks")


def test_match_max_slippage() -> None:
    m = PaperMatchEngine(max_slippage_bps=Decimal("10"))
    r = m.match(_order(size=Decimal("400")), _book())  # 2. Stufe: ~164 bps > 10
    assert r.status == OrderStatus.PARTIALLY_FILLED
    assert len(r.fills) == 1
    print("OK test_match_max_slippage")


def test_match_wrong_token() -> None:
    m = PaperMatchEngine()
    try:
        m.match(_order(), _snapshot(token="0xOTHER"))
        raise AssertionError("Token-Mismatch hätte ValueError werfen müssen")
    except ValueError:
        pass
    print("OK test_match_wrong_token")


def test_match_empty_book_side_no_crash() -> None:
    """Regression: einseitiger Ticker (price=0/size=0) darf nicht abstürzen.

    market_data_feed.on_ticker() erzeugt für eine fehlende Buchseite eine
    Stufe mit price=0/size=0. Ohne Guard im Buch-Walk lief eine BUY-Order
    gegen ask=0 und endete in einem pydantic-ValidationError von FillResult
    (execution_price gt=0) statt in einer sauberen Ablehnung.
    """
    handler = PolySentinelBookHandler(SnapshotCache())
    snap = handler.on_ticker(
        "0xtokenA", best_bid=Decimal("0.60"), best_ask=Decimal("0"), size=Decimal("500")
    )
    r = PaperMatchEngine().match(_order(size=Decimal("100"), price=Decimal("0.90")), snap)
    assert r.status == OrderStatus.PENDING, r.status
    assert r.fills == ()
    assert r.remaining_size == Decimal("100")
    print("OK test_match_empty_book_side_no_crash")


def test_match_slippage_is_measured_vs_reference() -> None:
    """Regression: Slippage misst gegen bestes ausführbares Niveau, nicht gegen das Limit.

    Eine tief im Geld platzierte Order (Limit 0.95, best ask 0.62) wurde
    vorher als 3473 bps Slippage gemeldet, obwohl sie zum Marktpreis
    gefüllt wurde. Echte Walk-Slippage (0.62 -> 0.70) muss erhalten bleiben.
    """
    handler = PolySentinelBookHandler(SnapshotCache())

    deep_itm = handler.on_book_update(
        "0xtokenA", bids=[(Decimal("0.60"), Decimal("100"))], asks=[(Decimal("0.62"), Decimal("10"))]
    )
    r = PaperMatchEngine().match(_order(size=Decimal("10"), price=Decimal("0.95")), deep_itm)
    assert r.avg_execution_price == Decimal("0.62")
    assert r.total_slippage_bps == Decimal("0"), r.total_slippage_bps

    walk = handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.60"), Decimal("100"))],
        asks=[(Decimal("0.62"), Decimal("100")), (Decimal("0.70"), Decimal("100"))],
    )
    r2 = PaperMatchEngine().match(_order(size=Decimal("200"), price=Decimal("0.95")), walk)
    assert r2.avg_execution_price == Decimal("0.66")
    assert r2.total_slippage_bps > Decimal("600"), r2.total_slippage_bps
    print("OK test_match_slippage_is_measured_vs_reference")


def test_risk_controller() -> None:
    from order_execution_engine.models import VirtualPortfolio
    rc = RiskController(RiskConfig())
    pf = VirtualPortfolio()
    # Order zu groß (Notional)
    big = _order(size=Decimal("2000"))  # 0.61*2000 = 1220 > 500
    d = rc.check(big, pf, {})
    assert not d.approved and d.reason == RejectReason.MAX_POSITION_SIZE
    # OK
    ok = _order(size=Decimal("100"))  # 61 USDC
    assert rc.check(ok, pf, {}).approved
    # Cash-Limit: BUY über Cash
    rc2 = RiskController(RiskConfig())
    pf2 = VirtualPortfolio(cash=Decimal("10.00"), peak_equity=Decimal("10.00"))
    d2 = rc2.check(ok, pf2, {})
    assert not d2.approved and d2.reason == RejectReason.INSUFFICIENT_CASH
    print("OK test_risk_controller")


def test_drawdown_lockout() -> None:
    from order_execution_engine.models import VirtualPortfolio
    rc = RiskController(RiskConfig(max_drawdown_pct=Decimal("10")))
    pf = VirtualPortfolio(peak_equity=Decimal("10000"), cash=Decimal("8900"))
    d = rc.check(_order(), pf, {})
    assert not d.approved and d.reason == RejectReason.DRAWDOWN_LOCKOUT
    assert rc.lockout_active
    # bleibt aktiv auch bei Recovery (Notfall-Bremse)
    pf.cash = Decimal("10000")
    d2 = rc.check(_order(), pf, {})
    assert not d2.approved and d2.reason == RejectReason.DRAWDOWN_LOCKOUT
    rc.reset_lockout()
    assert rc.check(_order(), pf, {}).approved
    print("OK test_drawdown_lockout")


def test_engine_end_to_end() -> None:
    eng = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("200")))
    sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                        direction=Direction.UP, confidence=Decimal("70"))
    rec = eng.on_signal(sig, _book())
    assert rec.approved
    assert rec.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)
    assert rec.latency_ms >= 0
    assert eng.portfolio.cash < Decimal("10000.00")
    assert eng.portfolio.positions["0xtokenA"].size > 0
    summary = eng.performance_summary()
    assert summary["open_positions"] == 1
    assert summary["telemetry"]["count"] == 1.0
    print("OK test_engine_end_to_end")


def test_engine_inversion() -> None:
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        invert_weak_signals=True, confidence_threshold=Decimal("60"),
    )
    weak = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                         direction=Direction.UP, confidence=Decimal("40"))
    rec = eng.on_signal(weak, _book())
    # UP + invert -> SELL; ohne offene Position -> Risiko-Ablehnung (Short-Verbot)
    assert not rec.approved
    rejected_order = eng._order_book[rec.order_id]
    assert rejected_order.side == OrderSide.SELL
    assert rec.reject_reason == RejectReason.MAX_POSITION_SIZE
    assert eng.portfolio.cash == Decimal("10000.00")
    assert not eng.portfolio.positions
    print("OK test_engine_inversion")


def test_engine_neutral_rejected() -> None:
    eng = ShadowExecutionEngine()
    neutral = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.NEUTRAL, confidence=Decimal("80"))
    rec = eng.on_signal(neutral, _book())
    assert not rec.approved and rec.reject_reason == RejectReason.INVALID_PRICE
    print("OK test_engine_neutral_rejected")


def test_engine_guard_integrity() -> None:
    eng = ShadowExecutionEngine()
    try:
        eng.guard.order_send = True  # type: ignore[misc]
        raise AssertionError("Guard-Tampering hätte blockiert werden müssen")
    except PermissionError:
        pass
    try:
        SafetyGuard.block_network_call("https://clob.polymarket.com/orders")
        raise AssertionError("Netzwerk-Call hätte blockiert werden müssen")
    except PermissionError:
        pass
    print("OK test_engine_guard_integrity")


def test_size_fn_injection_is_observable() -> None:
    """Zeuge für den Sizing-Seam: eine injizierte `size_fn` wirkt.

    Der Default-Adapter ist per Definition verhaltensgleich mit der
    Legacy-Konstante — kein Test, der den Default benutzt, kann den Seam
    also von der Konstante unterscheiden. Der Zeuge muss sich vom Default
    *unterscheiden*, sonst beweist er nichts.

    Deshalb: halbierte Größe injizieren und prüfen, dass die Order die
    injizierte Größe trägt. Wird der Seam durch die Legacy-Konstante
    ersetzt (Mutant), wird genau dieser Test rot.
    """
    half = Decimal("50")
    calls: list[tuple[str, Decimal]] = []

    def halving_size_fn(signal, snapshot):
        # Der Snapshot muss ein read-only Zeuge sein, kein VirtualPortfolio.
        calls.append((type(snapshot).__name__, snapshot.cash))
        return half

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
        size_fn=halving_size_fn,
    )
    sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                        direction=Direction.UP, confidence=Decimal("80"))
    rec = engine.on_signal(sig, _book())

    assert rec.approved, rec.reject_reason
    assert calls, "size_fn wurde nie aufgerufen — Seam nicht durchlaufen"
    assert calls[0][0] == "PortfolioSnapshot", calls[0][0]
    # Die Order trägt die injizierte Größe, nicht die Konstante.
    order = engine._order_book[rec.order_id]
    assert order.size == half, f"erwartet {half}, bekam {order.size}"
    assert order.size != engine.risk.config.max_order_size_shares
    print("OK test_size_fn_injection_is_observable")


def test_default_size_fn_preserves_legacy_behaviour() -> None:
    """Der Default-Adapter reproduziert die Legacy-Konstante exakt.

    Komplement zum Zeugen-Test: Er belegt, dass F1c verhaltensneutral ist.
    """
    cfg = RiskConfig(max_order_size_shares=Decimal("100"))
    engine = ShadowExecutionEngine(risk_config=cfg)
    sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                        direction=Direction.UP, confidence=Decimal("80"))
    rec = engine.on_signal(sig, _book())
    assert rec.approved, rec.reject_reason
    order = engine._order_book[rec.order_id]
    assert order.size == cfg.max_order_size_shares
    print("OK test_default_size_fn_preserves_legacy_behaviour")


def test_portfolio_snapshot_is_deeply_frozen() -> None:
    """Der Snapshot ist zur Laufzeit dicht — nicht nur statisch.

    Pydantics `frozen=True` schützt nur die Attribut-Zuweisung. Ohne tiefes
    Einfrieren könnte die Sizing-Funktion über das Mapping die Positionen
    mutieren, und der Seam wäre ein `Protocol` mit Umweg.
    """
    from order_execution_engine.models import PortfolioSnapshot
    snap = PortfolioSnapshot(cash=Decimal("1000"), equity=Decimal("1000"),
                             positions={"0xA": Decimal("10")}, as_of_seq=7)
    try:
        snap.positions["0xA"] = Decimal("999999")  # type: ignore[index]
        raise AssertionError("Mapping war mutierbar — kein tiefer Freeze")
    except TypeError:
        pass
    try:
        snap.cash = Decimal("0")  # type: ignore[misc]
        raise AssertionError("Attribut war mutierbar")
    except Exception as exc:
        assert "frozen" in str(exc).lower() or isinstance(exc, (AttributeError, TypeError))
    assert snap.as_of_seq == 7
    print("OK test_portfolio_snapshot_is_deeply_frozen")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE ENGINE-TESTS BESTANDEN")
