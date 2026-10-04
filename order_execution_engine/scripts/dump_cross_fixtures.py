#!/usr/bin/env python3
"""Dump Golden FillResult-Listen aus dem Kanon-``_cross`` (vor Delegation).

Einmalig auf dem Vor-Delegations-Stand ausführen:

    python order_execution_engine/scripts/dump_cross_fixtures.py \\
        > order_execution_engine/tests/fixtures/cross_golden.json

Oder schreibt direkt in den Fixture-Pfad (Default).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

from order_execution_engine.models import (
    OrderSide,
    OrderType,
    PaperOrder,
    default_expiration,
)
from order_execution_engine.shadow_execution_engine import (
    MarketSnapshot,
    OrderBookLevel,
    PaperMatchEngine,
)

FIXED_OID = uuid.UUID("11111111-1111-1111-1111-111111111111")
FIXED_SID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _lvl(price: str, size: str) -> OrderBookLevel:
    return OrderBookLevel(Decimal(price), Decimal(size))


def _snap(
    *,
    token: str = "0xtokenA",
    asks: list[tuple[str, str]] | tuple = (),
    bids: list[tuple[str, str]] | tuple = (),
) -> MarketSnapshot:
    return MarketSnapshot(
        token_id=token,
        asks=tuple(_lvl(p, s) for p, s in asks),
        bids=tuple(_lvl(p, s) for p, s in bids),
        received_at=1000.0,
    )


def _order(
    *,
    side: OrderSide = OrderSide.BUY,
    price: str = "0.61",
    size: str = "100",
    token: str = "0xtokenA",
    order_type: OrderType = OrderType.FAK,
) -> PaperOrder:
    return PaperOrder(
        order_id=FIXED_OID,
        signal_id=FIXED_SID,
        token_id=token,
        side=side,
        price=Decimal(price),
        size=Decimal(size),
        expiration=default_expiration(5),
        order_type=order_type,
    )


def _ser_level(level: OrderBookLevel) -> dict:
    return {"price": str(level.price), "size": str(level.size)}


def _ser_snap(snapshot: MarketSnapshot) -> dict:
    return {
        "token_id": snapshot.token_id,
        "asks": [_ser_level(x) for x in snapshot.asks],
        "bids": [_ser_level(x) for x in snapshot.bids],
        "received_at": snapshot.received_at,
    }


def _ser_order(order: PaperOrder) -> dict:
    return {
        "order_id": str(order.order_id),
        "signal_id": str(order.signal_id),
        "token_id": order.token_id,
        "side": order.side.value,
        "price": str(order.price),
        "size": str(order.size),
        "order_type": order.order_type.value,
    }


def _ser_fill(fill) -> dict:
    return {
        "order_id": str(fill.order_id),
        "execution_price": str(fill.execution_price),
        "executed_size": str(fill.executed_size),
        "slippage": str(fill.slippage),
        "fee": str(fill.fee),
        "side": fill.side.value,
        "token_id": fill.token_id,
        "market_id": fill.market_id,
    }


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def add(
        name: str,
        eng: PaperMatchEngine,
        order: PaperOrder,
        snapshot: MarketSnapshot,
        *,
        size: Decimal | None = None,
        market_id: str | None = "mkt-1",
    ) -> None:
        sz = order.size if size is None else size
        fills, remaining, ref = eng._cross(
            order, snapshot, sz, market_id=market_id,
        )
        cases.append({
            "name": name,
            "fee_bps": str(eng.fee_bps),
            "max_slippage_bps": (
                None if eng.max_slippage_bps is None
                else str(eng.max_slippage_bps)
            ),
            "order": _ser_order(order),
            "snapshot": _ser_snap(snapshot),
            "size": str(sz),
            "market_id": market_id,
            "expected_fills": [_ser_fill(f) for f in fills],
            "expected_remaining": str(remaining),
            "expected_reference": str(ref),
        })

    m0 = PaperMatchEngine()
    add("full_fill_ask1", m0, _order(size="200"), _snap(
        asks=[("0.61", "200"), ("0.62", "300")],
        bids=[("0.59", "150"), ("0.58", "250")],
    ))
    add("walk_two_levels", m0, _order(size="400", price="0.62"), _snap(
        asks=[("0.61", "200"), ("0.62", "300")],
        bids=[("0.59", "150"), ("0.58", "250")],
    ))
    add("partial_limit_stop", m0, _order(size="400", price="0.61"), _snap(
        asks=[("0.61", "200"), ("0.62", "300")],
        bids=[("0.59", "150")],
    ))
    add("empty_book", m0, _order(size="100"), _snap(asks=[], bids=[]))
    add("exact_at_limit", m0, _order(size="50", price="0.61"), _snap(
        asks=[("0.61", "50")], bids=[("0.59", "10")],
    ))
    add("size_gt_depth", m0, _order(size="1000", price="0.62"), _snap(
        asks=[("0.61", "200"), ("0.62", "300")], bids=[],
    ))
    add(
        "sell_walk", m0,
        _order(side=OrderSide.SELL, price="0.58", size="300"),
        _snap(
            asks=[("0.61", "200")],
            bids=[("0.59", "150"), ("0.58", "250")],
        ),
    )
    add("zero_size_level_skipped", m0, _order(size="100", price="0.62"), _snap(
        asks=[("0.61", "0"), ("0.61", "40"), ("0.62", "80")],
        bids=[],
    ))
    add("limit_no_cross", m0, _order(size="100", price="0.50"), _snap(
        asks=[("0.61", "200")], bids=[("0.59", "150")],
    ))

    m_fee = PaperMatchEngine(fee_bps=Decimal("10"))
    add("fee_10bps", m_fee, _order(size="100", price="0.60"), _snap(
        asks=[("0.50", "40"), ("0.55", "80")], bids=[],
    ))

    m_cap = PaperMatchEngine(max_slippage_bps=Decimal("500"))
    add("cap_stops_level2", m_cap, _order(size="100", price="0.60"), _snap(
        asks=[("0.50", "50"), ("0.53", "50")], bids=[],
    ))

    add(
        "market_id_none", m0, _order(size="10", price="0.61"),
        _snap(asks=[("0.61", "10")], bids=[]),
        market_id=None,
    )
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests" / "fixtures" / "cross_golden.json",
        help="Ziel-JSON (Default: tests/fixtures/cross_golden.json)",
    )
    parser.add_argument(
        "--stdout", action="store_true",
        help="Nur nach stdout schreiben (kein Datei-Write)",
    )
    args = parser.parse_args()
    payload = json.dumps(build_cases(), indent=2) + "\n"
    if args.stdout:
        sys.stdout.write(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
