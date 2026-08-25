"""Descriptive lag curves from rescued Stufe-A-v2 draw JSONs.

Not confirmatory. Does not retune V2_UNSPEZIFISCH.
Peak lags are hypothesis-generating for a future Z pre-reg only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SEALED_POSITIVE_DRAWS = (2, 3, 5, 11, 12, 17)  # 0-based; sealed v2 run


def _load_draws(path: str) -> list[dict]:
    if os.path.isdir(path):
        rows = []
        for name in sorted(os.listdir(path)):
            if name.startswith("bridge_stufe_a_v2_draw_") and name.endswith(".json"):
                with open(os.path.join(path, name), encoding="utf-8") as fh:
                    rows.append(json.load(fh))
        return rows
    with open(path, encoding="utf-8") as fh:
        body = json.load(fh)
    if isinstance(body, dict) and "draws" in body:
        return list(body["draws"])
    raise SystemExit(f"no draws in {path}")


def _series(tests: list[dict], pair: str, metric: str, direction: str) -> list[tuple[int, float, bool]]:
    rows = [
        t
        for t in tests
        if t["pair"] == pair and t["metric"] == metric and t["direction"] == direction
    ]
    rows.sort(key=lambda t: t["lag_min"])
    return [(int(t["lag_min"]), float(t["observed"]), bool(t["bh_reject"])) for t in rows]


def _peak(series: list[tuple[int, float, bool]]) -> tuple[int, float] | None:
    if not series:
        return None
    lag, val, _ = max(series, key=lambda r: r[1])
    return lag, val


def main() -> int:
    parser = argparse.ArgumentParser(description="Descriptive v2 lag curves (rescue)")
    parser.add_argument("--input", default="bridge_stufe_a_v2_ergebnis.json")
    parser.add_argument("--positive-only", action="store_true", default=True)
    args = parser.parse_args()
    draws = _load_draws(args.input)
    if not draws:
        print("no draw files yet", file=sys.stderr)
        return 1
    selected = [d for d in draws if d.get("effect_present") or d.get("label") == "V2_POSITIVBEFUND"]
    if not selected:
        print("no V2_POSITIVBEFUND draws in input yet")
        return 0
    print("descriptive only — not confirmatory")
    print(f"positive draws in this file: {[d['draw'] for d in selected]}")
    print(f"sealed positive draws (0-based): {list(SEALED_POSITIVE_DRAWS)}")
    for row in selected:
        tests = row.get("tests") or []
        if not tests:
            print(f"draw {row['draw']}: no tests vector")
            continue
        print(f"\n=== draw {row['draw']} {row.get('label')} n_sig={row.get('n_sig')} ===")
        for pair in ("treatment", "control"):
            for metric in ("hawkes", "cte"):
                for direction in ("ab", "ba"):
                    ser = _series(tests, pair, metric, direction)
                    peak = _peak(ser)
                    hits = [lag for lag, _, sig in ser if sig]
                    peak_s = f"peak τ={peak[0]} val={peak[1]:.6g}" if peak else "empty"
                    print(f"  {pair} {metric} {direction}: {peak_s}; bh_reject lags={hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
