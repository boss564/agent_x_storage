"""JSONL WORM fixtures for regime swarm smoke / gate tests (SIGNAL mark_price rows)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def stable_prices(n: int, base: float = 100.0) -> List[float]:
    return [base + (i % 5) * 0.01 for i in range(n)]


def flash_crash_prices(
    n_stable: int = 69,
    *,
    base: float = 100.0,
    crash_price: float = 50.0,
) -> List[float]:
    """Last tick flash move (default −50% vs ~base) — blocks A0 at G0=20%."""
    return stable_prices(n_stable, base) + [crash_price]


def write_signal_worm(
    path: Path,
    prices: List[float],
    *,
    symbol: str = "BTCUSDC",
    transport_meta: Optional[Dict[str, Any]] = None,
) -> None:
    lines: List[str] = []
    for i, price in enumerate(prices):
        row: Dict[str, Any] = {
            "action": "SIGNAL",
            "signal_id": f"sig-{i}",
            "mark_price": str(price),
            "symbol": symbol,
        }
        if transport_meta is not None and i == len(prices) - 1:
            row.update(transport_meta)
        lines.append(json.dumps(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_smoke_worms(root: Path) -> Dict[str, Path]:
    """Write default smoke WORMs under *root* and return paths."""
    flash = root / "flash_crash.jsonl"
    valid = root / "valid_ticks.jsonl"
    write_signal_worm(flash, flash_crash_prices())
    write_signal_worm(valid, stable_prices(70))
    return {"flash_crash": flash, "valid_ticks": valid}
