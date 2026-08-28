"""Slippage models for paper fills — simulation only (P3)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

Level = Tuple[Union[float, Decimal], Union[float, Decimal]]
OrderBook = Dict[str, List[Level]]


def _f(x: Union[float, Decimal]) -> float:
    return float(x)


def mid_price(orderbook: OrderBook) -> float:
    asks = orderbook.get("asks") or []
    bids = orderbook.get("bids") or []
    if not asks or not bids:
        raise ValueError("orderbook needs non-empty asks and bids")
    return (_f(asks[0][0]) + _f(bids[0][0])) / 2.0


def calculate_fixed_slippage(
    mid: float,
    *,
    side: str,
    fallback_percent: float,
) -> Tuple[float, float]:
    """Fixed slippage around mid (buy pays more, sell receives less)."""
    if side == "buy":
        eff = mid * (1.0 + fallback_percent)
        return eff, fallback_percent
    if side == "sell":
        eff = mid * (1.0 - fallback_percent)
        return eff, fallback_percent
    raise ValueError(f"side must be buy|sell, got {side!r}")


def calculate_dynamic_slippage(
    order_size: float,
    orderbook: OrderBook,
    side: str = "buy",
    *,
    orderbook_depth_levels: int = 10,
    fallback_percent: float = 0.001,
) -> Tuple[float, float]:
    """Walk the book for effective price and slippage vs mid.

    Args:
        order_size: size in base asset units
        orderbook: {"asks": [(price, qty), ...], "bids": [...]}
        side: "buy" (lift asks) or "sell" (hit bids)

    Returns:
        (effective_price, slippage_percent) — slippage signed adverse for side
    """
    if order_size <= 0:
        raise ValueError("order_size must be positive")

    m = mid_price(orderbook)
    if side == "buy":
        levels = list(orderbook.get("asks") or [])[:orderbook_depth_levels]
    elif side == "sell":
        levels = list(orderbook.get("bids") or [])[:orderbook_depth_levels]
    else:
        raise ValueError(f"side must be buy|sell, got {side!r}")

    if not levels:
        eff, slip = calculate_fixed_slippage(
            m, side=side, fallback_percent=fallback_percent
        )
        return eff, slip

    remaining = float(order_size)
    total_cost = 0.0
    total_filled = 0.0

    for price, quantity in levels:
        if remaining <= 0:
            break
        px, qty = _f(price), _f(quantity)
        if px <= 0 or qty <= 0:
            continue
        fill = min(remaining, qty)
        total_cost += fill * px
        total_filled += fill
        remaining -= fill

    if total_filled <= 0:
        eff, slip = calculate_fixed_slippage(
            m, side=side, fallback_percent=fallback_percent
        )
        return eff, slip

    effective_price = total_cost / total_filled
    if side == "buy":
        slippage_percent = (effective_price - m) / m if m > 0 else fallback_percent
    else:
        slippage_percent = (m - effective_price) / m if m > 0 else fallback_percent

    return effective_price, slippage_percent


def synthetic_orderbook(
    mid: float,
    *,
    spread_bps: float = 5.0,
    depth_levels: int = 10,
    qty_per_level: float = 1.0,
) -> OrderBook:
    """Deterministic book for smoke/compare when no live depth feed."""
    half = mid * (spread_bps / 10000.0) / 2.0
    asks: List[Level] = []
    bids: List[Level] = []
    for i in range(depth_levels):
        asks.append((mid + half + i * half * 0.5, qty_per_level))
        bids.append((mid - half - i * half * 0.5, qty_per_level))
    return {"asks": asks, "bids": bids}


def execution_price(
    *,
    mid: float,
    order_size: float,
    side: str,
    mode: str,
    orderbook: Optional[OrderBook],
    fallback_percent: float,
    orderbook_depth_levels: int,
) -> Tuple[float, float, str]:
    """Unified entry: returns (price, slippage_pct, mode_used)."""
    if mode == "fixed" or orderbook is None:
        px, slip = calculate_fixed_slippage(
            mid, side=side, fallback_percent=fallback_percent
        )
        return px, slip, "fixed"
    px, slip = calculate_dynamic_slippage(
        order_size,
        orderbook,
        side,
        orderbook_depth_levels=orderbook_depth_levels,
        fallback_percent=fallback_percent,
    )
    return px, slip, "dynamic"
