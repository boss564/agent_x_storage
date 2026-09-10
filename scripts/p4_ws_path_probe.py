#!/usr/bin/env python3
"""A/B WS path probe: same stdlib client as live-shadow Spot feed.

  A — Futures (fstream) from the cluster (where Spot already works)
  B — Spot (stream.binance.com:9443) from the lab host (where the listener ran)

Not a duration test. Default 8s is enough for aggTrade/trade.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.feed import (  # noqa: E402
    _open_ws_socket,
    _ws_recv_text_frames,
)

SPOT_TRADE = "wss://stream.binance.com:9443/ws/btcusdt@trade"
FUTURES_AGG = "wss://fstream.binance.com/ws/btcusdt@aggTrade"


def probe(url: str, seconds: float) -> dict:
    t0 = time.time()
    n = 0
    sample = None
    error = None
    try:
        sock = _open_ws_socket(url, timeout_s=10.0)
        sock.settimeout(1.0)
        deadline = time.time() + seconds
        try:
            for frame in _ws_recv_text_frames(sock):
                n += 1
                if sample is None:
                    sample = frame[:160]
                if time.time() >= deadline:
                    break
        finally:
            try:
                sock.close()
            except OSError:
                pass
    except (OSError, ConnectionError, TimeoutError, socket.timeout) as exc:
        error = f"{type(exc).__name__}: {exc}"[:240]
    elapsed = round(time.time() - t0, 2)
    return {
        "url": url,
        "seconds": seconds,
        "elapsed_s": elapsed,
        "frames": n,
        "rate_per_s": round(n / max(elapsed, 0.01), 2),
        "sample": sample,
        "error": error,
        "alive": n > 0,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", action="append", dest="urls")
    p.add_argument("--seconds", type=float, default=8.0)
    p.add_argument("--place", default="unknown")
    args = p.parse_args()
    urls = args.urls or [SPOT_TRADE, FUTURES_AGG]
    results = [probe(u, args.seconds) for u in urls]
    out = {"place": args.place, "probes": results}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
