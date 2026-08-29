"""Read-only market ticks for paper trading — never order endpoints."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from prototypes.raas_paper_trading.slippage import OrderBook

Level = Tuple[Union[float, str], Union[float, str]]


@dataclass(frozen=True)
class PaperTick:
    symbol: str
    ts: str
    price: float
    source: str  # binance_rest | binance_ws | replay | pyth_stub | mock_ws

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "price": self.price,
            "source": self.source,
        }


class ReplayFeed:
    """Deterministic tick source for tests and offline paper runs."""

    def __init__(self, ticks: Sequence[PaperTick]) -> None:
        self._ticks = list(ticks)

    def __iter__(self) -> Iterator[PaperTick]:
        yield from self._ticks

    def __len__(self) -> int:
        return len(self._ticks)


def fetch_binance_rest_sample(
    symbol: str = "ETHUSDT",
    *,
    limit: int = 20,
    timeout_s: float = 10.0,
) -> List[PaperTick]:
    """Read-only public klines — no API key, no order path.

    Used for optional live smoke; CI uses ReplayFeed.
    """
    url = (
        f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}"
        f"&interval=1m&limit={int(limit)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "agent-x-paper/0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    out: List[PaperTick] = []
    for row in rows:
        # [open_time, open, high, low, close, ...]
        open_ms = int(row[0])
        close = float(row[4])
        ts = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc).isoformat()
        out.append(PaperTick(symbol=symbol.upper(), ts=ts, price=close, source="binance_rest"))
    return out


def assert_no_order_urls(url: str) -> None:
    """Fail-closed guard for any future feed wiring."""
    banned = ("/order", "/order/test", "orderId", "newOrder")
    low = url.lower()
    for b in banned:
        if b.lower() in low:
            raise RuntimeError(f"order_send_forbidden: refused URL containing {b!r}")


def parse_orderbook_snapshot(raw: object) -> OrderBook:
    """Normalize WORM/API depth into bids/asks float tuples."""
    if not isinstance(raw, dict):
        raise ValueError("orderbook_snapshot must be a dict")
    out: OrderBook = {"bids": [], "asks": []}
    for side in ("bids", "asks"):
        for item in raw.get(side) or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            price, qty = float(item[0]), float(item[1])
            if price > 0 and qty > 0:
                out[side].append((price, qty))
    if not out["bids"] or not out["asks"]:
        raise ValueError("orderbook_snapshot needs non-empty bids and asks")
    return out


def orderbook_to_snapshot(book: OrderBook) -> Dict[str, List[List[str]]]:
    """JSON-serializable depth for WORM lines."""
    return {
        "bids": [[str(p), str(q)] for p, q in book.get("bids") or []],
        "asks": [[str(p), str(q)] for p, q in book.get("asks") or []],
    }


def fetch_binance_ticker(
    symbol: str,
    *,
    timeout_s: float = 10.0,
) -> PaperTick:
    """Read-only last price — no API key, no order path."""
    sym = symbol.upper()
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
    assert_no_order_urls(url)
    req = urllib.request.Request(url, headers={"User-Agent": "agent-x-paper/0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    price = float(raw["price"])
    ts = datetime.now(timezone.utc).isoformat()
    return PaperTick(symbol=sym, ts=ts, price=price, source="binance_rest_ticker")


BINANCE_WS_HOST_DEFAULT = "wss://stream.binance.com:9443/ws"


def binance_trade_ws_url(symbol: str, *, base: Optional[str] = None) -> str:
    """Public Binance trade stream — no API key, subscribe-via-URL only."""
    stream = f"{symbol.strip().lower()}@trade"
    root = (base or os.environ.get("LIVE_FEED_WS_URL") or BINANCE_WS_HOST_DEFAULT).rstrip("/")
    if root.endswith("@trade") or "/ws/" in root and "@" in root.split("/")[-1]:
        # Full stream URL already provided
        url = root
    else:
        url = f"{root}/{stream}" if root.endswith("/ws") else f"{root.rstrip('/')}/{stream}"
    assert_no_order_urls(url)
    if not url.startswith(("wss://", "ws://")):
        raise RuntimeError("live_feed: only ws:// or wss:// URLs allowed")
    return url


def parse_binance_ws_message(payload: str, *, default_symbol: str = "ETHUSDT") -> Optional[PaperTick]:
    """Parse a Binance trade/aggTrade JSON frame into PaperTick. Returns None if not a trade."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    event = str(inner.get("e") or "")
    if event not in ("trade", "aggTrade"):
        return None
    try:
        price = float(inner["p"])
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0:
        return None
    symbol = str(inner.get("s") or default_symbol).upper()
    ts_ms = inner.get("T") or inner.get("E")
    if ts_ms is not None:
        ts = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).isoformat()
    else:
        ts = datetime.now(timezone.utc).isoformat()
    return PaperTick(symbol=symbol, ts=ts, price=price, source="binance_ws")


class MockWebSocketFeed:
    """Deterministic JSON-frame source for tests — no network."""

    def __init__(self, frames: Sequence[str], *, default_symbol: str = "ETHUSDT") -> None:
        self._frames = list(frames)
        self._default_symbol = default_symbol

    def __iter__(self) -> Iterator[PaperTick]:
        for raw in self._frames:
            tick = parse_binance_ws_message(raw, default_symbol=self._default_symbol)
            if tick is not None:
                yield tick

    def __len__(self) -> int:
        return sum(
            1
            for raw in self._frames
            if parse_binance_ws_message(raw, default_symbol=self._default_symbol) is not None
        )


def _ws_recv_text_frames(sock: socket.socket) -> Iterator[str]:
    """Minimal RFC6455 text-frame reader (server → client, unmasked)."""
    def _read_exact(n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("websocket closed")
            buf += chunk
        return buf

    while True:
        hdr = _read_exact(2)
        opcode = hdr[0] & 0x0F
        masked = (hdr[1] & 0x80) != 0
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", _read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _read_exact(8))[0]
        mask_key = _read_exact(4) if masked else b""
        payload = _read_exact(length)
        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:  # close
            return
        if opcode == 0x9:  # ping → pong
            _ws_send_frame(sock, payload, opcode=0xA)
            continue
        if opcode == 0x1:
            yield payload.decode("utf-8")


def _ws_send_frame(sock: socket.socket, payload: bytes, *, opcode: int) -> None:
    """Client frames must be masked."""
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack("!Q", n)
    sock.sendall(header + mask + masked)


def _open_ws_socket(url: str, *, timeout_s: float = 15.0) -> socket.socket:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("wss", "ws"):
        raise RuntimeError("live_feed: only ws/wss allowed")
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    raw = socket.create_connection((host, port), timeout=timeout_s)
    sock: socket.socket
    if parsed.scheme == "wss":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(raw, server_hostname=host)
    else:
        sock = raw
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "User-Agent: agent-x-paper/0\r\n"
        "\r\n"
    )
    sock.sendall(req.encode("ascii"))
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise ConnectionError("websocket handshake failed")
        buf += chunk
    status_line = buf.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    if "101" not in status_line:
        sock.close()
        raise ConnectionError(f"websocket handshake rejected: {status_line}")
    expected = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    headers = buf.split(b"\r\n\r\n", 1)[0].decode("ascii", errors="replace").lower()
    if expected.lower() not in headers:
        sock.close()
        raise ConnectionError("websocket accept mismatch")
    sock.settimeout(None)
    return sock


class BinanceWebSocketFeed:
    """Read-only Binance trade stream. Inject ``frames`` to skip the network (tests)."""

    def __init__(
        self,
        url: str,
        *,
        frames: Optional[Iterable[str]] = None,
        default_symbol: str = "ETHUSDT",
        stop: Optional[Callable[[], bool]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        on_reconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        assert_no_order_urls(url)
        if not url.startswith(("wss://", "ws://")):
            raise RuntimeError("live_feed: only ws:// or wss:// URLs allowed")
        self.url = url
        self._frames = list(frames) if frames is not None else None
        self._default_symbol = default_symbol
        self._stop = stop
        self._on_disconnect = on_disconnect
        self._on_reconnect = on_reconnect

    def __iter__(self) -> Iterator[PaperTick]:
        if self._frames is not None:
            yield from MockWebSocketFeed(self._frames, default_symbol=self._default_symbol)
            return
        # Reconnect loop: drop → disconnect callback; next successful open → reconnect
        ever_connected = False
        pending_reconnect = False
        while True:
            if self._stop is not None and self._stop():
                return
            sock: Optional[socket.socket] = None
            try:
                sock = _open_ws_socket(self.url)
                if pending_reconnect and self._on_reconnect is not None:
                    self._on_reconnect()
                pending_reconnect = False
                ever_connected = True
                for raw in _ws_recv_text_frames(sock):
                    if self._stop is not None and self._stop():
                        return
                    tick = parse_binance_ws_message(raw, default_symbol=self._default_symbol)
                    if tick is not None:
                        yield tick
                # Clean server close
                if ever_connected and self._on_disconnect is not None:
                    self._on_disconnect()
                    pending_reconnect = True
            except (ConnectionError, OSError, TimeoutError, ssl.SSLError):
                if ever_connected and not pending_reconnect and self._on_disconnect is not None:
                    self._on_disconnect()
                    pending_reconnect = True
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if self._stop is not None and self._stop():
                return
            time.sleep(1.0)


@dataclass(frozen=True)
class RecvPulse:
    """Local accept pulse for cross-venue connectivity — no price field (Pre-Reg §5)."""

    venue: str  # v1 | v2
    recv_ts: str


COINBASE_WS_DEFAULT = "wss://ws-feed.exchange.coinbase.com"


def coinbase_matches_subscribe_msg(product_id: str = "ETH-USD") -> str:
    return json.dumps(
        {
            "type": "subscribe",
            "product_ids": [product_id],
            "channels": ["matches"],
        }
    )


def coinbase_frame_is_match(payload: str, *, product_id: str = "ETH-USD") -> bool:
    """True if frame is a match/trade for product — price is ignored (connectivity only)."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    if str(data.get("type") or "") not in ("match", "last_match"):
        return False
    return str(data.get("product_id") or "") == product_id


class CoinbaseMatchRecvFeed:
    """Read-only Coinbase matches → RecvPulse (t_recv only). Inject frames for tests."""

    def __init__(
        self,
        url: str = COINBASE_WS_DEFAULT,
        *,
        product_id: str = "ETH-USD",
        frames: Optional[Iterable[str]] = None,
        stop: Optional[Callable[[], bool]] = None,
        venue: str = "v2",
    ) -> None:
        assert_no_order_urls(url)
        if not url.startswith(("wss://", "ws://")):
            raise RuntimeError("live_feed: only ws:// or wss:// URLs allowed")
        self.url = url
        self.product_id = product_id
        self._frames = list(frames) if frames is not None else None
        self._stop = stop
        self.venue = venue

    def __iter__(self) -> Iterator[RecvPulse]:
        if self._frames is not None:
            for raw in self._frames:
                if coinbase_frame_is_match(raw, product_id=self.product_id):
                    yield RecvPulse(venue=self.venue, recv_ts=datetime.now(timezone.utc).isoformat())
            return
        while True:
            if self._stop is not None and self._stop():
                return
            sock: Optional[socket.socket] = None
            try:
                sock = _open_ws_socket(self.url)
                _ws_send_frame(
                    sock,
                    coinbase_matches_subscribe_msg(self.product_id).encode("utf-8"),
                    opcode=0x1,
                )
                for raw in _ws_recv_text_frames(sock):
                    if self._stop is not None and self._stop():
                        return
                    if coinbase_frame_is_match(raw, product_id=self.product_id):
                        yield RecvPulse(
                            venue=self.venue,
                            recv_ts=datetime.now(timezone.utc).isoformat(),
                        )
            except (ConnectionError, OSError, TimeoutError, ssl.SSLError):
                pass
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if self._stop is not None and self._stop():
                return
            time.sleep(1.0)


def fetch_binance_depth(
    symbol: str,
    *,
    limit: int = 10,
    timeout_s: float = 10.0,
) -> OrderBook:
    """Read-only public depth — no API key, no order path (Paket 2 / Phase B)."""
    sym = symbol.upper()
    url = f"https://api.binance.com/api/v3/depth?symbol={sym}&limit={int(limit)}"
    assert_no_order_urls(url)
    req = urllib.request.Request(url, headers={"User-Agent": "agent-x-paper/0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return parse_orderbook_snapshot(raw)
