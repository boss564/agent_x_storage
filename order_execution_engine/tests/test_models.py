"""Self-Tests für order_execution_engine.models (v0.2 Härtung)."""

import sys
from datetime import timedelta
from decimal import Decimal


from order_execution_engine.models import (
    Direction,
    ExecutionMode,
    FillResult,
    MockEIP712Signature,
    OrderSide,
    OrderStatus,
    PaperOrder,
    Position,
    RejectReason,
    RiskConfig,
    SafetyGuard,
    SignalPayload,
    VirtualPortfolio,
    _utcnow,
    default_expiration,
)


def _make_signal(**kw) -> SignalPayload:
    base = dict(
        target_token_id="0xtokenA",
        market_id="mkt-1",
        direction=Direction.UP,
        confidence=Decimal("72.5"),
    )
    base.update(kw)
    return SignalPayload(**base)


def _make_order(**kw) -> PaperOrder:
    base = dict(
        signal_id=_make_signal().signal_id,
        token_id="0xtokenA",
        side=OrderSide.BUY,
        price=Decimal("0.62"),
        size=Decimal("150"),
        expiration=default_expiration(5),
    )
    base.update(kw)
    return PaperOrder(**base)


def test_signal_inversion() -> None:
    assert _make_signal(direction=Direction.UP).resolved_side() == OrderSide.BUY
    assert _make_signal(direction=Direction.DOWN).resolved_side() == OrderSide.SELL
    assert _make_signal(direction=Direction.NEUTRAL).resolved_side() is None
    inverted = _make_signal(direction=Direction.UP, invert=True)
    assert inverted.resolved_side() == OrderSide.SELL
    print("OK test_signal_inversion")


def test_order_validation() -> None:
    o = _make_order()
    assert o.notional == Decimal("93.000000")
    assert o.status == OrderStatus.PENDING
    assert not o.is_expired()
    try:
        _make_order(expiration=_utcnow() - timedelta(minutes=1))
        raise AssertionError("abgelaufene Order hätte abgelehnt werden müssen")
    except ValueError:
        pass  # erwarteter Pfad: Pydantic-Validator wirft ValueError
    try:
        _make_order(mode=ExecutionMode.DISABLED)
        raise AssertionError("DISABLED-Modus hätte PermissionError werfen müssen")
    except PermissionError:
        pass
    print("OK test_order_validation")


def test_mock_signature() -> None:
    sig = MockEIP712Signature.mock()
    assert sig.is_mock is True
    print("OK test_mock_signature")


def test_portfolio_apply_fill() -> None:
    pf = VirtualPortfolio()
    o = _make_order(size=Decimal("100"))
    fill = FillResult(order_id=o.order_id, execution_price=Decimal("0.62"), executed_size=Decimal("100"))
    realized = pf.apply_fill(o, fill, market_id="mkt-1")
    assert realized == Decimal("0")
    assert pf.cash == Decimal("10000.00") - Decimal("62.00")
    assert pf.positions["0xtokenA"].size == Decimal("100")

    sell = _make_order(side=OrderSide.SELL, size=Decimal("40"))
    f2 = FillResult(order_id=sell.order_id, execution_price=Decimal("0.70"), executed_size=Decimal("40"))
    r2 = pf.apply_fill(sell, f2, market_id="mkt-1")
    assert r2 == Decimal("3.20")  # (0.70-0.62)*40
    assert pf.cash == Decimal("9938.00") + Decimal("28.00")
    assert pf.positions["0xtokenA"].size == Decimal("60")
    assert pf.realized_pnl == Decimal("3.20")
    print("OK test_portfolio_apply_fill")


def test_drawdown_and_peak() -> None:
    pf = VirtualPortfolio()
    pf.peak_equity = Decimal("10500.00")
    pf.cash = Decimal("9400.00")  # Equity sinkt auf 9400
    dd = pf.current_drawdown_pct({})
    assert dd > Decimal("0")
    # Recovery: neuer Peak
    pf.cash = Decimal("10600.00")
    assert pf.current_drawdown_pct({}) == Decimal("0")
    assert pf.peak_equity == Decimal("10600.00")
    print("OK test_drawdown_and_peak")


def test_exposure_per_market() -> None:
    pf = VirtualPortfolio()
    pf.positions["t1"] = Position(token_id="t1", market_id="mA", side=OrderSide.BUY,
                                  avg_entry_price=Decimal("0.50"), size=Decimal("100"))
    pf.positions["t2"] = Position(token_id="t2", market_id="mA", side=OrderSide.BUY,
                                  avg_entry_price=Decimal("0.40"), size=Decimal("50"))
    pf.positions["t3"] = Position(token_id="t3", market_id="mB", side=OrderSide.BUY,
                                  avg_entry_price=Decimal("0.60"), size=Decimal("20"))
    exp = pf.exposure_per_market()
    assert exp["mA"] == Decimal("70.0")
    assert exp["mB"] == Decimal("12.0")
    print("OK test_exposure_per_market")


def test_safety_guard() -> None:
    g = SafetyGuard()
    g.assert_safe()  # DRY_RUN ok
    g.assert_safe(ExecutionMode.PAPER_TRADING)
    try:
        g.assert_safe(ExecutionMode.DISABLED)
        raise AssertionError("DISABLED hätte PermissionError werfen müssen")
    except PermissionError:
        pass
    try:
        g.order_send = True  # type: ignore[misc]
        raise AssertionError("Tampering hätte blockiert werden müssen")
    except PermissionError:
        pass
    try:
        g.mode = ExecutionMode.DISABLED  # type: ignore[misc]
        raise AssertionError("Modus-Tampering hätte blockiert werden müssen")
    except PermissionError:
        pass
    try:
        SafetyGuard.block_network_call("https://clob.polymarket.com/orders")
        raise AssertionError("Netzwerk-Call hätte blockiert werden müssen")
    except PermissionError as e:
        assert "order_send=false" in str(e)
    try:
        SafetyGuard(mode=ExecutionMode.DISABLED)
        raise AssertionError("Init mit DISABLED hätte fehlschlagen müssen")
    except PermissionError:
        pass
    print("OK test_safety_guard")


def test_safety_guard_module_monkeypatch() -> None:
    """Regression: Modul-Level-Patch der Charter-Flags darf den Guard nicht umgehen.

    Vorher las `assert_safe()` nur die bei Init eingefrorenen Instanz-Kopien.
    Ein `models.LIVE_EXECUTION = True` blieb dadurch unbemerkt und der Guard
    meldete fälschlich GRÜN — die Charter ist aber eine Eigenschaft des
    Moduls, nicht der Instanz.
    """
    import order_execution_engine.models as models_mod

    g = SafetyGuard()
    g.assert_safe()  # Baseline: DRY_RUN grün

    for flag, patch in (("ORDER_SEND", True), ("LIVE_EXECUTION", True), ("DIAGNOSTIC_ONLY", False)):
        original = getattr(models_mod, flag)
        setattr(models_mod, flag, patch)
        try:
            g.assert_safe()
            raise AssertionError(f"Modul-Patch {flag}={patch} wurde nicht erkannt")
        except PermissionError:
            pass
        finally:
            setattr(models_mod, flag, original)

    g.assert_safe()  # Nach Restore wieder grün
    print("OK test_safety_guard_module_monkeypatch")


def test_safety_guard_class_freeze() -> None:
    """Die Guard-KLASSE ist gegen Attribut-Überschreiben gehärtet.

    `SafetyGuard.live_execution = True` muss ein PermissionError werfen —
    andernfalls wäre der Guard über den Klassennamespace manipulierbar.
    Nur die Instanz wird bei `__init__` aus den Modul-Konstanten neu befüllt.
    """
    try:
        vars(SafetyGuard)["live_execution"] = True
        raise AssertionError("class-__dict__-Patch hätte scheitern müssen")
    except TypeError:
        pass
    try:
        SafetyGuard.live_execution = True  # type: ignore[misc]
        raise AssertionError("Klassen-Attribut-Patch hätte blockiert werden müssen")
    except PermissionError:
        pass
    print("OK test_safety_guard_class_freeze")


def test_risk_config_defaults() -> None:
    rc = RiskConfig()
    assert rc.max_position_size_usdc == Decimal("500.00")
    assert rc.max_event_exposure_usdc == Decimal("1000.00")
    assert rc.max_drawdown_pct == Decimal("10.0")
    print("OK test_risk_config_defaults")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            fn()
    print("ALLE TESTS BESTANDEN")
