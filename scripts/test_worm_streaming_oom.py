#!/usr/bin/env python3
"""WORM streaming I/O — OOM regression guard (no full-file read_text)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_drift import load_signal_prices  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm.agents import DataIngestorAgent  # noqa: E402
from prototypes.raas_paper_trading.worm_io import (  # noqa: E402
    iter_jsonl_rows,
    last_signal_row,
    load_signal_mark_prices,
)


def _fail(msg: str) -> None:
    print(f"FAIL {msg}")
    raise SystemExit(1)


def _write_worm(path: Path, n: int) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(
                json.dumps(
                    {
                        "action": "SIGNAL",
                        "signal_id": f"sig-{i}",
                        "mark_price": str(2000.0 + i * 0.01),
                        "m7_latency_ms": 12 if i == n - 1 else None,
                    }
                )
                + "\n"
            )
            if i % 7 == 0:
                f.write(
                    json.dumps({"action": "SIM_FILL", "side": "BUY", "qty": "0.01", "price": "2000"})
                    + "\n"
                )


def test_stream_not_full_read(monkey_guard: bool = True) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        worm = Path(tmp) / "paper_trades.worm.jsonl"
        _write_worm(worm, 500)
        # Guard: Path.read_text must not be used by loaders under test
        if monkey_guard:
            orig = Path.read_text

            def _blocked(self: Path, *a: object, **k: object) -> str:
                if self.name.endswith(".jsonl"):
                    _fail(f"read_text used on {self}")
                return orig(self, *a, **k)  # type: ignore[misc]

            Path.read_text = _blocked  # type: ignore[method-assign]
            try:
                prices = load_signal_prices(worm, max_ticks=50)
                meta = DataIngestorAgent(max_ticks=50).load_transport_meta(worm)
            finally:
                Path.read_text = orig  # type: ignore[method-assign]
        else:
            prices = load_signal_prices(worm, max_ticks=50)
            meta = DataIngestorAgent(max_ticks=50).load_transport_meta(worm)

        if len(prices) != 50:
            _fail(f"expected tail 50 got {len(prices)}")
        if abs(prices[-1] - (2000.0 + 499 * 0.01)) > 1e-9:
            _fail(f"tail price wrong {prices[-1]}")
        if abs(prices[0] - (2000.0 + 450 * 0.01)) > 1e-9:
            _fail(f"tail start wrong {prices[0]}")
        if meta.get("latency_ms") != 12.0:
            _fail(f"transport meta {meta}")


def test_unlimited_streaming_count() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        worm = Path(tmp) / "w.jsonl"
        _write_worm(worm, 120)
        prices = load_signal_mark_prices(worm, max_ticks=None)
        if len(prices) != 120:
            _fail(f"expected 120 got {len(prices)}")
        n = sum(1 for _ in iter_jsonl_rows(worm))
        if n < 120:
            _fail("iter_jsonl_rows short")


def test_last_signal_row_tail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        worm = Path(tmp) / "w.jsonl"
        _write_worm(worm, 80)
        row = last_signal_row(worm, max_bytes=2048)
        if row is None or row.get("signal_id") != "sig-79":
            _fail(f"last signal {row}")


def test_a2_run_reports_max_ticks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        worm = Path(tmp) / "w.jsonl"
        _write_worm(worm, 30)
        out = DataIngestorAgent(max_ticks=10).run(worm)
        if out.get("n_ticks") != 10 or out.get("max_ticks") != 10:
            _fail(f"a2 run {out}")


def main() -> int:
    test_stream_not_full_read()
    test_unlimited_streaming_count()
    test_last_signal_row_tail()
    test_a2_run_reports_max_ticks()
    print("WORM_STREAMING_OOM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
