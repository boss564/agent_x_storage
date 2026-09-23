"""Self-Tests für shadow_execution_engine (RiskController, PaperMatchEngine, Engine)."""

import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from order_execution_engine.market_data_feed import PolySentinelBookHandler, SnapshotCache
from order_execution_engine.models import (
    Direction,
    FillResult,
    OrderSide,
    OrderStatus,
    OrderType,
    RejectReason,
    RiskConfig,
    SafetyGuard,
    SignalPayload,
    VirtualPortfolio,
    default_expiration,
)
from order_execution_engine.persistence import SQLiteShadowStorage, TelemetrySink
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    PaperMatchEngine,
    PaperOrder,
    RiskController,
    ShadowExecutionEngine,
    TelemetryLogger,
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


def test_match_guard_rejects_non_fak() -> None:
    """Zeuge: Guard feuert laut bei non-FAK/GTC — ohne FOK ins Enum aufzunehmen.

    ``OrderType.FOK`` existiert bewusst nicht (kein Inventar ohne Aufgabe).
    Der Probe-Enum beweist den Leser im Matcher; wer FOK spaeter aufnimmt,
    braucht Produzent + All-or-Nothing-Verhalten zuerst.
    """
    from enum import Enum

    Probe = Enum("OrderTypeProbe", {"FOK": "FOK"}, type=str)
    o = _order()
    o = PaperOrder.model_construct(**{**o.model_dump(), "order_type": Probe.FOK})
    try:
        PaperMatchEngine().match(o, _book())
        raise AssertionError("NotImplementedError erwartet fuer non-FAK/GTC")
    except NotImplementedError as exc:
        assert "FOK" in str(exc)
    print("OK test_match_guard_rejects_non_fak")


def test_gtc_partial_fills_and_rests() -> None:
    """GTC gegen duennes Buch -> PARTIALLY_FILLED + Resting-Register."""
    m = PaperMatchEngine()
    # Ask-Tiefe 200; Order 400 -> Rest 200 ruht
    thin = _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    o = _order(size=Decimal("400"), price=Decimal("0.61"))
    o = o.model_copy(update={"order_type": OrderType.GTC})
    r = m.match(o, thin, signal_id=o.signal_id, market_id="mkt-1",
                requested_size=Decimal("400"), decision_seq=1)
    assert r.status is OrderStatus.PARTIALLY_FILLED
    assert r.remaining_size == Decimal("200")
    assert m.resting_count == 1
    print("OK test_gtc_partial_fills_and_rests")


def test_gtc_resting_fills_on_book_update() -> None:
    """Ruhende GTC-Order: neuer Snapshot kreuzt Rest -> FILLED, Register leer."""
    m = PaperMatchEngine()
    thin = _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    crossing = _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    o = _order(size=Decimal("400"), price=Decimal("0.61"))
    o = o.model_copy(update={"order_type": OrderType.GTC})
    r = m.match(o, thin, signal_id=o.signal_id, market_id="mkt-1",
                requested_size=Decimal("400"), decision_seq=1)
    assert r.status is OrderStatus.PARTIALLY_FILLED
    assert m.resting_count == 1
    evals = m.on_book_update(crossing)
    assert len(evals) == 1
    assert evals[0].result.status is OrderStatus.FILLED
    assert evals[0].result.remaining_size == Decimal("0")
    assert m.resting_count == 0
    print("OK test_gtc_resting_fills_on_book_update")


def test_gtc_idle_is_resting_not_pending() -> None:
    """GTC ohne Kreuzung -> RESTING (nicht PENDING); Register gefuellt."""
    m = PaperMatchEngine()
    # Limit unter Ask -> kein Fill
    book = _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    o = _order(size=Decimal("100"), price=Decimal("0.60"))
    o = o.model_copy(update={"order_type": OrderType.GTC})
    r = m.match(o, book, signal_id=o.signal_id)
    assert r.status is OrderStatus.RESTING
    assert not r.fills
    assert m.resting_count == 1
    # Terminal-Ausschluss: RESTING ist nicht FILLED/PARTIALLY
    assert r.status not in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)
    print("OK test_gtc_idle_is_resting_not_pending")


def test_reap_noop_before_expiration() -> None:
    """Vor TTL: reap_expired ist No-Op — Register bleibt, kein Telemetrie-Satz."""
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("400")),
    )
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    thin = _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    o = _order(size=Decimal("400"), price=Decimal("0.61"))
    o = o.model_copy(update={"order_type": OrderType.GTC, "expiration": exp})
    r = eng.matcher.match(
        o, thin, signal_id=o.signal_id, market_id="mkt-1",
        requested_size=Decimal("400"), decision_seq=1,
    )
    eng._order_book[o.order_id] = o.model_copy(update={"status": r.status})
    assert eng.matcher.resting_count == 1
    assert eng.reap_expired(now=exp - timedelta(seconds=1)) == []
    assert eng.matcher.resting_count == 1
    assert eng._order_book[o.order_id].status is not OrderStatus.EXPIRED
    print("OK test_reap_noop_before_expiration")


def test_reap_expired_transitions_resting_to_expired() -> None:
    """Beide Uhr-Seiten: kein Reap vor TTL; danach RESTING→EXPIRED, Register leer.

    on_signal framet heute FAK — Resting wird hier ueber Matcher+Orderbuch
    aufgebaut (gleicher Register-/Book-Pfad wie Produktions-GTC). remaining_size
    auf RestingExpiry = ungefuellter Rest; Cash unveraendert (kein Fill).
    """
    eng = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("400")),
    )
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    thin = _snapshot(
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    o = _order(size=Decimal("400"), price=Decimal("0.61"))
    o = o.model_copy(update={"order_type": OrderType.GTC, "expiration": exp})
    r = eng.matcher.match(
        o, thin, signal_id=o.signal_id, market_id="mkt-1",
        requested_size=Decimal("400"), decision_seq=1,
    )
    assert r.status is OrderStatus.PARTIALLY_FILLED
    assert r.remaining_size == Decimal("200")
    eng._order_book[o.order_id] = o.model_copy(update={"status": r.status})
    cash_before = eng.portfolio.cash

    t_before = exp - timedelta(seconds=1)
    assert eng.reap_expired(now=t_before) == []
    assert eng.matcher.resting_count == 1

    # RestingExpiry.remaining_size am Matcher-Seam (ungefuellter Rest, Audit)
    twin = PaperMatchEngine()
    o2 = _order(size=Decimal("400"), price=Decimal("0.61"))
    o2 = o2.model_copy(update={"order_type": OrderType.GTC, "expiration": exp})
    twin.match(o2, thin, signal_id=o2.signal_id, market_id="mkt-1",
               requested_size=Decimal("400"), decision_seq=1)
    exps = twin.reap_expired(now=exp + timedelta(seconds=1))
    assert len(exps) == 1
    assert exps[0].remaining_size == Decimal("200")

    records = eng.reap_expired(now=exp + timedelta(seconds=1))
    assert eng.matcher.resting_count == 0
    assert len(records) == 1
    assert records[0].status is OrderStatus.EXPIRED
    assert records[0].approved is True
    assert records[0].reject_reason is RejectReason.NONE
    assert eng._order_book[o.order_id].status is OrderStatus.EXPIRED
    assert eng.portfolio.cash == cash_before
    print("OK test_reap_expired_transitions_resting_to_expired")


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
    # Positions-Check (kumuliert) — die einzige Order-Grenze, die bleibt.
    # F1b: Die Order-Level-Checks (ehemals 116/118) sind entfernt. Der
    # Notional-Fall landet jetzt hier, wenn Bestand + Order das Limit kippen.
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
    assert rc.check(_order(size=Decimal("50")), pf, {}).approved
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


def test_decision_seq_correlates_snapshot_and_record() -> None:
    """Snapshot und Telemetrie-Record teilen dieselbe Entscheidungs-Id.

    Regression für die fragile Kopplung `as_of_seq=len(telemetry._records)`:
    Die DB-`seq` wird per AUTOINCREMENT erst beim INSERT vergeben, der
    Sizing-Snapshot entsteht aber vorher. Die Engine muss die Id selbst
    vergeben, sonst rät der Snapshot die künftige Zeilennummer — korrekt
    nur unter vier ungeschriebenen Invarianten.
    """
    seen: list[int] = []

    def spy(signal, snap):
        seen.append(snap.as_of_seq)
        return Decimal("50")

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")), size_fn=spy)
    neutral = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.NEUTRAL, confidence=Decimal("80"))
    up = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                       direction=Direction.UP, confidence=Decimal("80"))

    engine.on_signal(neutral, _book())   # Pre-Order-Reject: Id 1
    rec_fill = engine.on_signal(up, _book())  # Fill: Snapshot + Record teilen Id 2

    seqs = [r.decision_seq for r in engine.telemetry._records]
    assert seqs == [1, 2], seqs
    assert seen == [2], seen
    assert rec_fill.decision_seq == 2
    assert seen[0] == rec_fill.decision_seq, "Snapshot und Record nicht korreliert"
    print("OK test_decision_seq_correlates_snapshot_and_record")


def test_ankera_cumulative_position_breach() -> None:
    """Anker (a): Zwei Orders auf dasselbe Token — die zweite kippt das Limit.

    Der manuelle Beleg vom 2026-09-20 (vorbelegte Position 90 + Order 61 bei
    Limit 100 → Reject) wird hier dauerhaft. Vor F1 war das strukturell
    unerreichbar: `size` war die Config-Konstante, `size > limit` konnte nie
    eintreten, und MAX_POSITION_SIZE feuerte nie.
    """
    cfg = RiskConfig(per_order_cap_shares=Decimal("100"),
                     max_position_size_usdc=Decimal("100"))
    eng = ShadowExecutionEngine(risk_config=cfg, size_fn=lambda s, p: Decimal("90"))
    sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                        direction=Direction.UP, confidence=Decimal("90"))

    r1 = eng.on_signal(sig, _book())   # 90 * 0.61 = 54.9 < 100 -> fuellt
    assert r1.approved, "erste Order muss fuellen"

    r2 = eng.on_signal(sig, _book())   # 54.9 + 54.9 = 109.8 > 100 -> Reject
    assert not r2.approved and r2.reject_reason == RejectReason.MAX_POSITION_SIZE
    assert r2.requested_size == Decimal("90"), r2.requested_size
    print("OK test_ankera_cumulative_position_breach")


def test_ankerb_clamp_is_measured_not_silent() -> None:
    """Anker (b): requested > cap → Ausführung am Cap, Telemetrie zeigt beide."""
    cfg = RiskConfig(per_order_cap_shares=Decimal("60"),
                     max_position_size_usdc=Decimal("500"))
    eng = ShadowExecutionEngine(risk_config=cfg, size_fn=lambda s, p: Decimal("400"))
    sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                        direction=Direction.UP, confidence=Decimal("90"))
    rec = eng.on_signal(sig, _book())
    order = eng._order_book[rec.order_id]
    assert rec.approved
    assert rec.requested_size == Decimal("400"), rec.requested_size
    assert order.size == Decimal("60"), order.size
    assert rec.requested_size != order.size, "Kappung muss messbar sein"
    print("OK test_ankerb_clamp_is_measured_not_silent")


def test_ankerc_config_invariant_blocks_start() -> None:
    """Anker (c): Config mit cap > max_position_size → Start scheitert."""
    from pydantic import ValidationError
    try:
        RiskConfig(per_order_cap_shares=Decimal("600"),
                   max_position_size_usdc=Decimal("500"))
    except ValidationError as exc:
        msg = str(exc)
        assert "600" in msg and "500" in msg, "Meldung muss beide Werte nennen"
        print("OK test_ankerc_config_invariant_blocks_start")
        return
    raise AssertionError("Invariante hat nicht gefeuert — Start war faelschlich ok")


def test_ankerd_meta_every_reject_reason_has_a_producer() -> None:
    """Anker (d, Meta): Jeder `RejectReason`-Wert hat einen lebenden Produzenten.

    Ersetzt den alten Anker (d), der die drei F1-Labels auf Unterscheidbarkeit
    prüfte. Mit F1b sterben zwei der Label-Sites (eine Falle, eine Tautologie),
    also auch ihr Zeuge. An seine Stelle tritt der Wächter gegen die nächste
    Scheinschutz-Generation: ein Enum-Wert, den jeder Diagnostics-Konsument
    für möglich halten muss, der aber nie kommt.

    Dieser Anker fängt beide Richtungen:
      - Enum-Wert ohne Produzenten -> Wert muss weg (oder ein Produzent her).
      - Produzent ohne Enum-Wert   -> strukturell unmöglich (Code nutzt das Enum).

    Bewusste Ausnahmen: `NONE` (Marker für genehmigte Signale) und Werte, die
    ausschliesslich über `OrderStatus` laufen, nicht über `RejectReason`.
    """
    import re
    from pathlib import Path as _P

    src = _P("order_execution_engine/shadow_execution_engine.py").read_text()
    produced = set(re.findall(r"RejectReason\.([A-Z_]+)", src))
    allowed_without_producer = {"NONE"}

    orphans = [
        r.name for r in RejectReason
        if r.name not in produced and r.name not in allowed_without_producer
    ]
    assert not orphans, (
        f"RejectReason ohne Produzenten: {orphans}. "
        f"Ein Wert ohne Produzenten ist Scheinschutz im Enum — entweder "
        f"Produzent herstellen oder Wert entfernen."
    )
    print("OK test_ankerd_meta_every_reject_reason_has_a_producer")


def test_anker_counter_lifetime_across_restart() -> None:
    """VM3: Zähler überlebt einen Prozessneustart (Replay-Korrelation)."""
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        eng = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("100")))
        sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.UP, confidence=Decimal("80"))
        eng.on_signal(sig, _book())
        eng.on_signal(sig, _book())
        TelemetrySink(store, eng.telemetry).drain()
        assert store.latest_decision_seq() == 2, store.latest_decision_seq()

        # "Neustart": neuer Logger, Zähler aus der DB initialisiert
        logger2 = TelemetryLogger(initial_decision_seq=store.latest_decision_seq())
        eng2 = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
                                     telemetry=logger2)
        rec = eng2.on_signal(sig, _book())
        assert rec.decision_seq == 3, f"Kollision nach Neustart: {rec.decision_seq}"
        store.close()
    print("OK test_anker_counter_lifetime_across_restart")


def test_requested_size_null_table() -> None:
    """Pinned die vollständige Erwartungstabelle für `requested_size`.

    Die `NULL`-Doktrin lebt in der DDL (`NULL = vor Messbeginn, nicht:
    fehlend`), also prüft ihr Zeuge die **Datenbank**, nicht das
    In-Memory-Record. Diese Tabelle macht eine Semantik zur behaupteten,
    die sonst implizit von der Reihenfolge im Code getroffen würde:

        Pfad                    | requested_size
        ------------------------|---------------
        ungültiger Preis        | NULL   (Sizing lief nie)
        leere Buchseite         | NULL   (INVALID_PRICE-Pfad)
        Drawdown-Lockout        | gesetzt (Lockout sitzt NACH dem Sizing)
        Risk-Reject             | gesetzt
        Approved                | gesetzt

    Der Lockout ist der interessante Fall: `RiskController.check()` läuft
    nach dem Sizing, also hat die Strategie bereits angefragt. Eine künftige
    Pipeline-Umordnung, die das ändert, wird hier rot statt still.
    """
    import sqlite3

    def _recorded(engine: ShadowExecutionEngine) -> list[tuple]:
        conn = sqlite3.connect(str(_db))
        rows = conn.execute(
            "SELECT approved, reject_reason, requested_size FROM telemetry ORDER BY seq"
        ).fetchall()
        conn.close()
        return rows

    with tempfile.TemporaryDirectory() as tmp:
        _db = Path(tmp) / "u1" / "shadow" / "shadow.db"

        # (1) ungültiger Preis: keine Order-Seite -> Sizing lief nie
        e1 = ShadowExecutionEngine(risk_config=RiskConfig(max_order_size_shares=Decimal("100")))
        empty = MarketSnapshot(token_id="0xtokenA", bids=(), asks=())
        sig = SignalPayload(target_token_id="0xtokenA", market_id="mkt-1",
                            direction=Direction.UP, confidence=Decimal("80"))
        r1 = e1.on_signal(sig, empty)
        assert r1.reject_reason == RejectReason.INVALID_PRICE
        assert r1.requested_size is None, r1.requested_size

        # (2) Drawdown-Lockout: Sizing lief, Lockout greift danach
        e2 = ShadowExecutionEngine(
            risk_config=RiskConfig(max_order_size_shares=Decimal("100"),
                                   max_drawdown_pct=Decimal("10")),
            size_fn=lambda s, p: Decimal("70"))
        e2.portfolio.peak_equity = Decimal("10000")
        e2.portfolio.cash = Decimal("8000")   # 20 % Drawdown -> Lockout
        r2 = e2.on_signal(sig, _book())
        assert r2.reject_reason == RejectReason.DRAWDOWN_LOCKOUT
        assert r2.requested_size == Decimal("70"), r2.requested_size

        # (3) Risk-Reject: angefordert, gekappt, und *danach* abgelehnt —
        # so bleibt der Risk-Reject-Pfad mit gesetztem requested_size sichtbar.
        # Die ablehnende Wirkung kommt aus dem Event-Exposure (kleiner als
        # das, was der Clamp durchlässt).
        e3 = ShadowExecutionEngine(
            risk_config=RiskConfig(max_order_size_shares=Decimal("1000"),
                                   per_order_cap_shares=Decimal("100"),
                                   max_position_size_usdc=Decimal("500"),
                                   max_event_exposure_usdc=Decimal("20")),
            size_fn=lambda s, p: Decimal("500"))
        r3 = e3.on_signal(sig, _book())
        assert not r3.approved, (r3.approved, r3.reject_reason)
        assert r3.reject_reason == RejectReason.MAX_EVENT_EXPOSURE, r3.reject_reason
        assert r3.requested_size == Decimal("500"), r3.requested_size

        # (4) Approved
        e4 = ShadowExecutionEngine(
            risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
            size_fn=lambda s, p: Decimal("50"))
        r4 = e4.on_signal(sig, _book())
        assert r4.approved and r4.requested_size == Decimal("50")

        # Alle vier in EINER DB — die Tabelle wird am persistierten Zustand
        # geprüft, nicht am In-Memory-Record.
        store = SQLiteShadowStorage.for_user(Path(tmp), "u1")
        for e in (e1, e2, e3, e4):
            TelemetrySink(store, e.telemetry).drain()
        rows = sqlite3.connect(str(_db)).execute(
            "SELECT approved, reject_reason, requested_size FROM telemetry ORDER BY seq"
        ).fetchall()
        store.close()

    table = [(r[1], r[2]) for r in rows]
    assert table[0] == ("INVALID_PRICE", None), table[0]
    assert table[1] == ("DRAWDOWN_LOCKOUT", "70"), table[1]
    assert table[2][0] == "MAX_EVENT_EXPOSURE", table[2]
    assert table[2][1] == "500", table[2]
    assert table[3] == ("NONE", "50"), table[3]
    print("OK test_requested_size_null_table")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE ENGINE-TESTS BESTANDEN")
