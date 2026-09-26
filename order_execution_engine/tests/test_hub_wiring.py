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


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE HUB-WIRING-TESTS BESTANDEN")
