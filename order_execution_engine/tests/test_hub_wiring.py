"""Self-Tests fuer hub_wiring.py (Feed, Reaper-Tick, Journal-Audit)."""

from datetime import timedelta
from decimal import Decimal

from order_execution_engine.hub_wiring import ShadowHub, attach_book_feed
from order_execution_engine.models import (
    Direction,
    OrderSide,
    OrderStatus,
    PaperOrder,
    RejectReason,
    RiskConfig,
    SignalPayload,
    _utcnow,
    default_expiration,
)
from order_execution_engine.shadow_replay import ShadowAuditDivergence
from order_execution_engine.shadow_execution_engine import ShadowExecutionEngine


def _signal(confidence: Decimal = Decimal("80")) -> SignalPayload:
    return SignalPayload(
        target_token_id="0xtokenA",
        market_id="mkt-1",
        direction=Direction.UP,
        confidence=confidence,
    )


def test_attach_book_feed_pushes_snapshot_into_engine() -> None:
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
    )
    binding = attach_book_feed(engine)

    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500")), (Decimal("0.62"), Decimal("500"))],
    )

    snap = binding.cache.get("0xtokenA")
    assert snap is not None
    assert engine.get_snapshot("0xtokenA") is snap
    assert engine.current_marks()["0xtokenA"] == Decimal("0.600")

    rec = engine.on_signal(_signal())  # kein expliziter Snapshot: Feed-Daten
    assert rec.approved
    assert engine.portfolio.positions["0xtokenA"].size == Decimal("100")
    print("OK test_attach_book_feed_pushes_snapshot_into_engine")


def test_attach_book_feed_ws_dispatch_path() -> None:
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("50")),
    )
    binding = attach_book_feed(engine, start_ws_feed=True)
    assert binding.feed is not None

    binding.feed._dispatch({
        "event_type": "book",
        "market": "0xtokenA",
        "bids": [{"price": "0.59", "size": "100"}],
        "asks": [{"price": "0.61", "size": "100"}],
    })
    assert engine.get_snapshot("0xtokenA") is not None
    print("OK test_attach_book_feed_ws_dispatch_path")


def test_reaper_expires_only_when_called() -> None:
    engine = ShadowExecutionEngine()
    order = PaperOrder(
        signal_id=_signal().signal_id,
        token_id="0xtokenA",
        side=OrderSide.BUY,
        price=Decimal("0.61"),
        size=Decimal("10"),
        expiration=default_expiration(1),
    )
    engine.register_order(order)

    assert engine.reap_expired(now=_utcnow()) == []
    assert engine._order_book[order.order_id].status == OrderStatus.PENDING

    expired = engine.reap_expired(now=order.expiration + timedelta(microseconds=1))
    assert len(expired) == 1
    assert expired[0].status == OrderStatus.EXPIRED
    assert engine._order_book[order.order_id].reject_reason is RejectReason.NONE
    assert len(engine.last_expired_orders) == 1
    assert engine.last_expired_orders[0].status == OrderStatus.EXPIRED

    # Idempotent: ein zweiter Tick verfaellt nichts mehr.
    assert engine.reap_expired(now=order.expiration + timedelta(seconds=1)) == []
    print("OK test_reaper_expires_only_when_called")


def test_shadow_replay_audit_matches_live_portfolio() -> None:
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
    )
    binding = attach_book_feed(engine)
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500"))],
    )
    assert engine.on_signal(_signal()).approved

    report = engine.audit_shadow_state(raise_on_divergence=True)
    assert report.ok
    assert report.live_snapshot == report.replay_snapshot
    assert engine.portfolio.snapshot(engine.current_marks()) == report.live_snapshot
    print("OK test_shadow_replay_audit_matches_live_portfolio")


def test_shadow_replay_audit_detects_tampering() -> None:
    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
    )
    binding = attach_book_feed(engine)
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500"))],
    )
    assert engine.on_signal(_signal()).approved

    engine.portfolio.cash -= Decimal("1.00")
    report = engine.audit_shadow_state()
    assert not report.ok
    assert any(f.path == "cash" for f in report.findings)
    try:
        engine.audit_shadow_state(raise_on_divergence=True)
        raise AssertionError("Divergenz haette ShadowAuditDivergence werfen muessen")
    except ShadowAuditDivergence:
        pass
    print("OK test_shadow_replay_audit_detects_tampering")


def test_shadow_hub_tick_reaps_and_audits_in_one_step() -> None:
    engine = ShadowExecutionEngine()
    hub = ShadowHub(engine)
    order = PaperOrder(
        signal_id=_signal().signal_id,
        token_id="0xtokenA",
        side=OrderSide.BUY,
        price=Decimal("0.61"),
        size=Decimal("10"),
        expiration=default_expiration(1),
    )
    engine.register_order(order)

    result = hub.tick(now=order.expiration + timedelta(microseconds=1))
    assert len(result.expired_orders) == 1
    assert result.expired_orders[0].status == OrderStatus.EXPIRED
    assert result.audit.ok
    print("OK test_shadow_hub_tick_reaps_and_audits_in_one_step")


def test_reap_does_not_expire_terminal_fak_partial() -> None:
    """FAK-Teilfill ist terminal — Orderbuch-Reaper darf nicht EXPIRED setzen."""
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot,
        OrderBookLevel,
    )

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("400")),
    )
    thin = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("30")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    report = engine.on_signal(_signal(), thin)
    assert report.status is OrderStatus.PARTIALLY_FILLED
    assert report.order_id is not None
    oid = report.order_id
    exp = engine._order_book[oid].expiration
    before_len = len(engine.telemetry._records)

    records = engine.reap_expired(now=exp + timedelta(seconds=1))
    assert records == []
    assert engine.last_expired_orders == ()
    assert engine._order_book[oid].status is OrderStatus.PARTIALLY_FILLED
    assert len(engine.telemetry._records) == before_len
    assert not any(
        r.status is OrderStatus.EXPIRED for r in engine.telemetry._records
    )
    print("OK test_reap_does_not_expire_terminal_fak_partial")


def test_journal_fills_when_resting_signal_id_is_none() -> None:
    """Matcher-Seam signal_id=None: Journal faellt auf order.signal_id zurueck."""
    from order_execution_engine.models import OrderType
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot,
        OrderBookLevel,
        PaperOrder as EngOrder,
    )

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("400")),
    )
    thin = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("200")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    crossing = MarketSnapshot(
        token_id="0xtokenA",
        asks=(OrderBookLevel(Decimal("0.61"), Decimal("500")),),
        bids=(OrderBookLevel(Decimal("0.59"), Decimal("150")),),
    )
    sig = _signal()
    order = EngOrder(
        signal_id=sig.signal_id,
        token_id="0xtokenA",
        side=OrderSide.BUY,
        price=Decimal("0.61"),
        size=Decimal("400"),
        expiration=default_expiration(5),
        order_type=OrderType.GTC,
    )
    # signal_id=None im Matcher-Register (Test-Seam)
    result = engine.matcher.match(
        order, thin, signal_id=None, market_id="mkt-1",
        requested_size=Decimal("400"), decision_seq=1,
    )
    assert result.status is OrderStatus.PARTIALLY_FILLED
    for fill in result.fills:
        engine.portfolio.apply_fill(order, fill, market_id="mkt-1")
        engine._journal_fill(
            order, signal_id=order.signal_id, market_id="mkt-1", fill=fill,
        )
    engine._order_book[order.order_id] = order.model_copy(
        update={"status": result.status},
    )

    n0 = len(engine.execution_journal())
    fills_before = len(engine.fills_for(order.order_id))
    records = engine.on_book_update(crossing)
    crossing_fills = engine.fills_for(order.order_id)[fills_before:]
    assert len(crossing_fills) > 0
    assert len(engine.execution_journal()) == n0 + len(crossing_fills)
    assert all(
        e.signal_id == order.signal_id
        for e in engine.execution_journal()[n0:]
    )
    assert records  # Telemetrie mit order.signal_id
    assert all(r.signal_id == order.signal_id for r in records)
    report = engine.audit_shadow_state(raise_on_divergence=True)
    assert report.ok
    print("OK test_journal_fills_when_resting_signal_id_is_none")


def test_audit_detects_apply_fill_bug() -> None:
    """Unabhaengiger Fold: Fehler in apply_fill selbst wird sichtbar."""
    from order_execution_engine.models import VirtualPortfolio
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot,
        OrderBookLevel,
    )

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
    )
    binding = attach_book_feed(engine)
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500"))],
    )

    original = VirtualPortfolio.apply_fill

    def broken(self, order, fill, market_id):  # noqa: ANN001
        result = original(self, order, fill, market_id)
        # Doppelte Kostenbuchung — Journal sieht nur den echten Fill.
        if order.side is OrderSide.BUY:
            self.cash -= fill.execution_price * fill.executed_size
        return result

    VirtualPortfolio.apply_fill = broken  # type: ignore[method-assign]
    try:
        assert engine.on_signal(_signal()).approved
        report = engine.audit_shadow_state()
        assert not report.ok
        assert any(f.path == "cash" for f in report.findings)
    finally:
        VirtualPortfolio.apply_fill = original  # type: ignore[method-assign]
    print("OK test_audit_detects_apply_fill_bug")


def test_incremental_audit_matches_full_audit() -> None:
    """Inkrementeller Cursor und Voll-Replay liefern denselben Snapshot."""
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot,
        OrderBookLevel,
    )

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("50")),
    )
    binding = attach_book_feed(engine)
    book = (
        [(Decimal("0.59"), Decimal("500"))],
        [(Decimal("0.61"), Decimal("500"))],
    )
    for _ in range(5):
        binding.handler.on_book_update("0xtokenA", bids=book[0], asks=book[1])
        assert engine.on_signal(_signal()).approved
        # Zwischenstands-Audit (Cursor rueckt vor)
        step = engine.audit_shadow_state()
        assert step.ok

    inc = engine.audit_shadow_state(full=False)
    full = engine.audit_shadow_state(full=True)
    assert inc.ok and full.ok
    assert inc.replay_snapshot == full.replay_snapshot
    assert inc.live_snapshot == full.live_snapshot
    assert engine._audited_upto == len(engine.execution_journal())
    print("OK test_incremental_audit_matches_full_audit")


def test_hub_full_audit_every_n_ticks() -> None:
    engine = ShadowExecutionEngine()
    hub = ShadowHub(engine, full_audit_every_n_ticks=2)
    r1 = hub.tick()
    assert r1.full_audit is False
    r2 = hub.tick()
    assert r2.full_audit is True
    assert r2.audit.ok
    print("OK test_hub_full_audit_every_n_ticks")


def test_audit_ok_after_mark_spike_and_revert() -> None:
    """Kurs-Spike zwischen Audits darf peak_equity nicht als Divergenz melden."""
    from order_execution_engine.shadow_execution_engine import (
        MarketSnapshot,
        OrderBookLevel,
    )

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("100")),
    )
    binding = attach_book_feed(engine)
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500"))],
    )
    assert engine.on_signal(_signal()).approved

    hub = ShadowHub(
        engine,
        raise_on_divergence=True,
        full_audit_every_n_ticks=2,
    )
    r1 = hub.tick()
    assert r1.audit.ok

    # Spike: Mid ~0.80 → Live-Peak steigt ohne Journal-Event
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.79"), Decimal("500"))],
        asks=[(Decimal("0.81"), Decimal("500"))],
    )
    # Rueckfall auf alte Marks
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500"))],
    )

    r2 = hub.tick()  # full_audit (tick 2)
    assert r2.audit.ok
    assert r2.full_audit is True

    inc = engine.audit_shadow_state(full=False, raise_on_divergence=True)
    full = engine.audit_shadow_state(full=True, raise_on_divergence=True)
    assert inc.ok and full.ok
    print("OK test_audit_ok_after_mark_spike_and_revert")


def test_journal_fold_error_advances_cursor() -> None:
    """Fold-ValueError wird Finding, Cursor rueckt vor (kein Doppel-Fold)."""
    import uuid
    from order_execution_engine.models import (
        ExecutedFillEvent,
        FillResult,
        OrderSide,
    )

    engine = ShadowExecutionEngine(
        risk_config=RiskConfig(max_order_size_shares=Decimal("50")),
    )
    binding = attach_book_feed(engine)
    binding.handler.on_book_update(
        "0xtokenA",
        bids=[(Decimal("0.59"), Decimal("500"))],
        asks=[(Decimal("0.61"), Decimal("500"))],
    )
    assert engine.on_signal(_signal()).approved
    assert engine.audit_shadow_state().ok
    n_after_ok = engine._audited_upto
    cash_after_ok = engine._journal_auditor.cash

    oid = uuid.uuid4()
    bad = ExecutedFillEvent(
        order_id=oid,
        signal_id=uuid.uuid4(),
        token_id="0xunknown",
        market_id="mkt-x",
        side=OrderSide.SELL,
        limit_price=Decimal("0.50"),
        order_size=Decimal("1"),
        fill=FillResult(
            order_id=oid,
            execution_price=Decimal("0.50"),
            executed_size=Decimal("1"),
        ),
    )
    engine._execution_journal.append(bad)

    report = engine.audit_shadow_state()
    assert not report.ok
    assert any(f.path == "journal" for f in report.findings)
    assert engine._audited_upto == n_after_ok + 1
    # Kein Doppel-Fold der guten Events: Cash unveraendert seit ok-Audit
    assert engine._journal_auditor.cash == cash_after_ok

    # Zweiter Tick: kein erneutes journal-Finding (bereits verbraucht)
    report2 = engine.audit_shadow_state()
    assert not any(f.path == "journal" for f in report2.findings)
    assert report2.ok
    print("OK test_journal_fold_error_advances_cursor")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE HUB-WIRING-TESTS BESTANDEN")
