"""WORM fill replay — fixed-tuple A/B for slippage modes (P3, post-processing only)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from prototypes.raas_paper_trading.config_loader import PaperTradingSettings
from prototypes.raas_paper_trading.depth_snapshot import (
    AGE_STRATA_5_30,
    AGE_STRATA_GT_30,
    AGE_STRATA_LT_5,
    AGE_STRATA_UNKNOWN,
    age_stratum,
    snapshot_age_seconds,
)
from prototypes.raas_paper_trading.feed import parse_orderbook_snapshot
from prototypes.raas_paper_trading.ledger import FeeSchedule, SlippageSettings
from prototypes.raas_paper_trading.slippage import (
    OrderBook,
    SYNTHETIC_QTY_PER_LEVEL,
    SYNTHETIC_SPREAD_BPS,
    synthetic_orderbook,
)

TWOPLACES = Decimal("0.01")
EIGHTPLACES = Decimal("0.00000001")


def _d(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FillTuple:
    """Immutable fill identity for clean A/B — no equity feedback."""

    side: str
    qty: Decimal
    mark_price: Decimal
    signal_id: str
    ts: str
    run_id: str
    worm_line_hash: Optional[str] = None
    orderbook: Optional[OrderBook] = None
    depth_source: Optional[str] = None
    snapshot_ts: Optional[str] = None
    snapshot_age_s: Optional[float] = None

    def to_dict(self) -> Dict[str, str]:
        base = {
            "side": self.side,
            "qty": str(self.qty),
            "mark_price": str(self.mark_price),
            "signal_id": self.signal_id,
            "ts": self.ts,
            "run_id": self.run_id,
            "worm_line_hash": self.worm_line_hash or "",
        }
        if self.depth_source:
            base["depth_source"] = self.depth_source
        if self.snapshot_ts:
            base["snapshot_ts"] = self.snapshot_ts
        if self.snapshot_age_s is not None:
            base["snapshot_age_s"] = str(self.snapshot_age_s)
        return base


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def load_fills_from_worm(path: Path) -> List[FillTuple]:
    """Extract SIM_FILL rows as fixed tuples (side, qty, mark_price)."""
    fills: List[FillTuple] = []
    run_id = path.parent.name if path.name == "paper_trades.worm.jsonl" else path.stem
    for row in iter_jsonl(path):
        if row.get("action") != "SIM_FILL":
            continue
        if row.get("live_execution") is True or row.get("order_send") is True:
            raise ValueError(f"live/order_send forbidden in replay source: {path}")
        side = str(row.get("side", "")).upper()
        if side not in ("BUY", "SELL"):
            continue
        mark_raw = row.get("mark_price") or row.get("mid_price")
        if mark_raw is None:
            # Fall back to recorded execution price — weaker but allows replay
            mark_raw = row.get("price")
        if mark_raw is None:
            continue
        qty = _d(row.get("qty", "0"))
        if qty <= 0:
            continue
        ob: Optional[OrderBook] = None
        depth_source = row.get("depth_source")
        snap = row.get("orderbook_snapshot")
        if snap:
            try:
                ob = parse_orderbook_snapshot(snap)
            except ValueError:
                ob = None
        age_raw = row.get("snapshot_age_s")
        age_s: Optional[float]
        if age_raw is not None and age_raw != "":
            age_s = float(age_raw)
        elif row.get("snapshot_ts") and row.get("ts"):
            try:
                age_s = snapshot_age_seconds(str(row["ts"]), str(row["snapshot_ts"]))
            except ValueError:
                age_s = None
        else:
            age_s = None
        fills.append(
            FillTuple(
                side=side,
                qty=qty,
                mark_price=_d(mark_raw),
                signal_id=str(row.get("signal_id", "")),
                ts=str(row.get("ts", "")),
                run_id=str(row.get("run_id") or run_id),
                worm_line_hash=str(row.get("hash") or ""),
                orderbook=ob,
                depth_source=str(depth_source) if depth_source else None,
                snapshot_ts=str(row["snapshot_ts"]) if row.get("snapshot_ts") else None,
                snapshot_age_s=age_s,
            )
        )
    return fills


def discover_worm_paths(
    *,
    worm_paths: Optional[Sequence[Union[str, Path]]] = None,
    worm_dir: Optional[Path] = None,
    audit_path: Optional[Path] = None,
    persist_dir: Optional[Path] = None,
) -> List[Path]:
    """Collect worm JSONL files from explicit paths, persist dir, or audit worm_path."""
    found: List[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            return
        seen.add(key)
        if p.is_file():
            found.append(p)
        elif p.is_dir():
            for child in sorted(p.rglob("paper_trades.worm.jsonl")):
                _add(child)

    if worm_paths:
        for raw in worm_paths:
            p = Path(raw)
            if p.is_file():
                _add(p)
            elif p.is_dir():
                _add(p)
            else:
                for match in Path(".").glob(str(p)):
                    _add(match)

    if worm_dir and worm_dir.is_dir():
        _add(worm_dir)

    if persist_dir and persist_dir.is_dir():
        _add(persist_dir)

    if audit_path and audit_path.is_file():
        for row in iter_jsonl(audit_path):
            wp = row.get("summary", {}).get("worm_path")
            if wp:
                _add(Path(str(wp)))
            run_id = row.get("run_id")
            if run_id and persist_dir:
                _add(persist_dir / str(run_id) / "paper_trades.worm.jsonl")

    return found


def load_all_fills(
    *,
    worm_paths: Optional[Sequence[Union[str, Path]]] = None,
    worm_dir: Optional[Path] = None,
    audit_path: Optional[Path] = None,
    persist_dir: Optional[Path] = None,
) -> List[FillTuple]:
    paths = discover_worm_paths(
        worm_paths=worm_paths,
        worm_dir=worm_dir,
        audit_path=audit_path,
        persist_dir=persist_dir,
    )
    fills: List[FillTuple] = []
    for p in paths:
        fills.extend(load_fills_from_worm(p))
    return fills


def _orderbook_for_fill(
    fill: FillTuple,
    *,
    settings: PaperTradingSettings,
    spread_bps: float,
    qty_per_level: float,
    orderbook: Optional[OrderBook],
) -> OrderBook:
    if orderbook is not None:
        return orderbook
    return synthetic_orderbook(
        float(fill.mark_price),
        spread_bps=spread_bps,
        depth_levels=settings.orderbook_depth_levels,
        qty_per_level=qty_per_level,
    )


def replay_interpretation(
    *,
    spread_bps: float,
    fallback_percent: Decimal,
    qty_per_level: float,
) -> List[str]:
    """Methodological guardrails — not performance claims."""
    return [
        (
            "Ergebnisrichtung durch spread_bps gegen fallback_percent festgelegt "
            f"({spread_bps} bps vs {fallback_percent * 100:.3f}%); kein Modellbefund."
        ),
        (
            f"Fills mit order_size ≤ qty_per_level ({qty_per_level}) bleiben im ersten Level; "
            "dynamische Slippage ist dann konstant (~spread_bps/2), Größenabhängigkeit greift "
            "nicht. Replay misst die gewichtete Kostenschiebung der Modellwahl über die "
            "Fill-Verteilung — nicht, welches Modell zutrifft (echte Buchtiefe fehlt)."
        ),
    ]


def per_fill_cost(
    fill: FillTuple,
    *,
    slippage_mode: str,
    settings: PaperTradingSettings,
    fees: FeeSchedule,
    spread_bps: float = SYNTHETIC_SPREAD_BPS,
    qty_per_level: float = SYNTHETIC_QTY_PER_LEVEL,
    orderbook: Optional[OrderBook] = None,
) -> Dict[str, Any]:
    """Cost for one fixed tuple — independent of ledger path / equity."""
    slip = SlippageSettings(
        mode=slippage_mode,
        fallback_percent=settings.fallback_percent,
        depth_levels=settings.orderbook_depth_levels,
    )
    book = _orderbook_for_fill(
        fill,
        settings=settings,
        spread_bps=spread_bps,
        qty_per_level=qty_per_level,
        orderbook=orderbook if orderbook is not None else fill.orderbook,
    )
    side = fill.side.lower()
    exec_px, slip_pct, used_mode = slip.apply(
        mid_price=fill.mark_price,
        qty=fill.qty,
        side=side,
        orderbook=book if slippage_mode == "dynamic" else None,
    )
    notional = (fill.qty * exec_px).quantize(TWOPLACES)
    fee = fees.fee_eur(notional, taker=True)
    slip_cost = (abs(exec_px - fill.mark_price) * fill.qty).quantize(TWOPLACES)
    return {
        "slippage_mode": slippage_mode,
        "mode_used": used_mode,
        "execution_price": str(exec_px),
        "slippage_percent": str(slip_pct.quantize(EIGHTPLACES)),
        "fee_eur": str(fee),
        "slippage_cost_eur": str(slip_cost),
        "notional_eur": str(notional),
    }


def _empty_age_strata() -> Dict[str, Dict[str, Any]]:
    base = {
        "fill_count": 0,
        "slippage_cost_delta_eur": Decimal("0"),
        "fee_delta_eur": Decimal("0"),
    }
    return {
        AGE_STRATA_LT_5: dict(base),
        AGE_STRATA_5_30: dict(base),
        AGE_STRATA_GT_30: dict(base),
        AGE_STRATA_UNKNOWN: dict(base),
    }


def _strata_to_report(strata: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    labels = {
        AGE_STRATA_LT_5: "< 5 s",
        AGE_STRATA_5_30: "5–30 s",
        AGE_STRATA_GT_30: "> 30 s",
        AGE_STRATA_UNKNOWN: "unknown",
    }
    for key, bucket in strata.items():
        out[key] = {
            "label": labels.get(key, key),
            "fill_count": bucket["fill_count"],
            "slippage_cost_delta_eur": str(
                Decimal(bucket["slippage_cost_delta_eur"]).quantize(TWOPLACES)
            ),
            "fee_delta_eur": str(Decimal(bucket["fee_delta_eur"]).quantize(TWOPLACES)),
        }
    return out


def replay_slippage_ab(
    fills: Sequence[FillTuple],
    *,
    settings: Optional[PaperTradingSettings] = None,
    spread_bps: float = SYNTHETIC_SPREAD_BPS,
    qty_per_level: float = SYNTHETIC_QTY_PER_LEVEL,
) -> Dict[str, Any]:
    """Replay fixed tuples under fixed vs dynamic slippage — per-fill A/B."""
    cfg = settings or PaperTradingSettings.from_file()
    fees = FeeSchedule.from_rates(cfg.maker_rate, cfg.taker_rate, note=cfg.exchange_name)

    rows: List[Dict[str, Any]] = []
    sum_fee_fixed = Decimal("0")
    sum_fee_dynamic = Decimal("0")
    sum_slip_fixed = Decimal("0")
    sum_slip_dynamic = Decimal("0")
    multi_level_fills = 0
    fills_with_snapshot = 0
    fills_live_depth = 0
    age_strata = _empty_age_strata()

    for fill in fills:
        if fill.qty > Decimal(str(qty_per_level)):
            multi_level_fills += 1
        if fill.orderbook is not None:
            fills_with_snapshot += 1
            if fill.depth_source == "binance_rest_depth":
                fills_live_depth += 1
        fixed = per_fill_cost(
            fill,
            slippage_mode="fixed",
            settings=cfg,
            fees=fees,
            spread_bps=spread_bps,
            qty_per_level=qty_per_level,
        )
        dynamic = per_fill_cost(
            fill,
            slippage_mode="dynamic",
            settings=cfg,
            fees=fees,
            spread_bps=spread_bps,
            qty_per_level=qty_per_level,
            orderbook=fill.orderbook,
        )
        fee_f = Decimal(fixed["fee_eur"])
        fee_d = Decimal(dynamic["fee_eur"])
        slip_f = Decimal(fixed["slippage_cost_eur"])
        slip_d = Decimal(dynamic["slippage_cost_eur"])
        sum_fee_fixed += fee_f
        sum_fee_dynamic += fee_d
        sum_slip_fixed += slip_f
        sum_slip_dynamic += slip_d
        slip_delta = (slip_d - slip_f).quantize(TWOPLACES)
        fee_delta = (fee_d - fee_f).quantize(TWOPLACES)
        stratum = age_stratum(fill.snapshot_age_s)
        age_strata[stratum]["fill_count"] += 1
        age_strata[stratum]["slippage_cost_delta_eur"] += slip_delta
        age_strata[stratum]["fee_delta_eur"] += fee_delta
        rows.append(
            {
                "fill": fill.to_dict(),
                "fixed": fixed,
                "dynamic": dynamic,
                "fee_delta_eur": str(fee_delta),
                "slippage_cost_delta_eur": str(slip_delta),
                "age_stratum": stratum,
                "snapshot_age_s": fill.snapshot_age_s,
            }
        )

    total_fee_delta = (sum_fee_dynamic - sum_fee_fixed).quantize(TWOPLACES)
    total_slip_delta = (sum_slip_dynamic - sum_slip_fixed).quantize(TWOPLACES)

    return {
        "schema": "raas_paper_slippage_replay_v1",
        "fill_count": len(rows),
        "protocol": "fixed_tuple_ab",
        "metrics": {
            "fee_delta_eur": str(total_fee_delta),
            "slippage_cost_delta_eur": str(total_slip_delta),
            "fee_fixed_total_eur": str(sum_fee_fixed.quantize(TWOPLACES)),
            "fee_dynamic_total_eur": str(sum_fee_dynamic.quantize(TWOPLACES)),
            "slippage_fixed_total_eur": str(sum_slip_fixed.quantize(TWOPLACES)),
            "slippage_dynamic_total_eur": str(sum_slip_dynamic.quantize(TWOPLACES)),
        },
        "snapshot_age_strata": _strata_to_report(age_strata),
        "synthetic_book": {
            "spread_bps": spread_bps,
            "qty_per_level": qty_per_level,
            "fills_past_level_1": multi_level_fills,
            "fills_with_orderbook_snapshot": fills_with_snapshot,
            "fills_binance_rest_depth": fills_live_depth,
        },
        "dynamic_book_note": (
            "Dynamic replay uses orderbook_snapshot on each SIM_FILL when present; "
            "otherwise synthetic_orderbook from mark_price "
            f"(spread_bps={spread_bps}, qty_per_level={qty_per_level})."
        ),
        "interpretation": replay_interpretation(
            spread_bps=spread_bps,
            fallback_percent=cfg.fallback_percent,
            qty_per_level=qty_per_level,
        ),
        "rows": rows,
        "diagnostic_only": True,
        "not_investment_advice": True,
        "live_execution": False,
        "config_hash": cfg.config_hash,
    }
