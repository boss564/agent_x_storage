"""Marktdaten-Feed: PolySentinel/Polymarket-CLOB -> MarketSnapshot.

Schließt die Shadow Execution Engine an echte Marktdaten an, OHNE
DB-Abhängigkeit und OHNE jeglichen Sende-Pfad.

Charter-Hinweis: Dieses Modul abonniert ausschließlich Marktdaten-
Kanäle (book/ticker). Es enthält keinen einzigen HTTP-POST- oder
Order-Endpunkt; `SafetyGuard.block_network_call` bleibt der einzige
Umgang mit Order-Relayer-URLs.

Architektur:
    - SnapshotCache: thread-sicherer Ringpuffer (token_id -> MarketSnapshot)
      mit Staleness-Prüfung. Wird von PolySentinel-Callbacks gefüttert.
    - PolySentinelBookHandler: minimale Callback-Schnittstelle, die ein
      PolySentinel-Websocket-Modul aufrufen kann (kein eigenes Netzwerk).
    - PolymarketWsFeed (optional): Read-only-WS-Client fuer den
      Eigenbetrieb, falls PolySentinel nicht als Prozess läuft. Baut
      aus book/price_change-Deltas vollständige Snapshots (Delta-
      Verdichtung im Feed, nicht im Handler).
"""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from typing import Callable, Optional, Protocol

from order_execution_engine.shadow_execution_engine import MarketSnapshot, OrderBookLevel


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class SnapshotCache:
    """Thread-sicherer Cache aktueller Marktschnappschüsse.

    PolySentinel-Callbacks rufen `update()` auf; die Engine liest über
    `get()`/`snapshot_for()`. Jede Aktualisierung ersetzt den Snapshot
    atomar (Schreiber: PolySentinel-Thread, Leser: Engine-Thread).
    """

    def __init__(self, max_age_seconds: float = 10.0) -> None:
        """Initialisiert den Cache.

        Args:
            max_age_seconds: Maximales Alter eines Snapshots, ab dem
                er als stale gilt und `get()` None zurückgibt.
        """
        self._max_age = max_age_seconds
        self._lock = threading.Lock()
        self._snapshots: dict[str, MarketSnapshot] = {}

    def update(self, snapshot: MarketSnapshot) -> None:
        """Schreibt einen neuen Snapshot (atomar, thread-safe).

        Args:
            snapshot: Der aktuelle Marktschnappschuss.
        """
        with self._lock:
            self._snapshots[snapshot.token_id] = snapshot

    def get(self, token_id: str) -> Optional[MarketSnapshot]:
        """Liest den aktuellen Snapshot, falls frisch genug.

        Args:
            token_id: CLOB Token-ID.

        Returns:
            MarketSnapshot oder None (unbekannt oder stale).
        """
        with self._lock:
            snap = self._snapshots.get(token_id)
        if snap is None:
            return None
        if time.time() - snap.received_at > self._max_age:
            return None
        return snap

    def snapshot_for(self, token_id: str, wait_seconds: float = 0.0) -> Optional[MarketSnapshot]:
        """Wartet optional kurz auf ein Update und liefert den Snapshot.

        Args:
            token_id: CLOB Token-ID.
            wait_seconds: Max. Wartezeit auf frische Daten (0 = sofort).

        Returns:
            MarketSnapshot oder None.
        """
        deadline = time.time() + wait_seconds
        while True:
            snap = self.get(token_id)
            if snap is not None or time.time() >= deadline:
                return snap
            time.sleep(0.05)

    def known_tokens(self) -> list[str]:
        """Gibt alle Token mit (nicht zwingend frischem) Snapshot zurück."""
        with self._lock:
            return list(self._snapshots.keys())

    def purge_stale(self) -> int:
        """Entfernt abgelaufene Snapshots (Housekeeping).

        Returns:
            Anzahl entfernter Einträge.
        """
        now = time.time()
        with self._lock:
            stale = [t for t, s in self._snapshots.items() if now - s.received_at > self._max_age]
            for t in stale:
                del self._snapshots[t]
        return len(stale)


# ---------------------------------------------------------------------------
# PolySentinel-Adapter-Schnittstelle
# ---------------------------------------------------------------------------


class PolySentinelBookHandler:
    """Empfängt Orderbuch-Updates aus PolySentinel und füllt den Cache.

    Einbindung: PolySentinel ruft bei jedem `book`-Event des CLOB-Websockets
    `on_book_update()` auf. Kein eigenes Netzwerk, keine Persistenz —
    reine Übersetzung in `MarketSnapshot`.
    """

    def __init__(self, cache: SnapshotCache) -> None:
        """Initialisiert den Handler mit einem Ziel-Cache.

        Args:
            cache: SnapshotCache der Engine.
        """
        self._cache = cache

    def on_book_update(
        self,
        token_id: str,
        bids: list[tuple[Decimal, Decimal]],
        asks: list[tuple[Decimal, Decimal]],
        received_at: Optional[float] = None,
    ) -> MarketSnapshot:
        """Übersetzt ein PolySentinel-Book-Event in einen Snapshot.

        Args:
            token_id: CLOB Token-ID.
            bids: [(price, size), ...], absteigend sortiert.
            asks: [(price, size), ...], aufsteigend sortiert.
            received_at: Empfangszeitpunkt (Default: jetzt).

        Returns:
            Der erzeugte und gecachte MarketSnapshot.
        """
        snapshot = MarketSnapshot(
            token_id=token_id,
            bids=tuple(OrderBookLevel(price=p, size=s) for p, s in sorted(bids, key=lambda x: -x[0])),
            asks=tuple(OrderBookLevel(price=p, size=s) for p, s in sorted(asks, key=lambda x: x[0])),
            received_at=received_at or time.time(),
        )
        self._cache.update(snapshot)
        return snapshot

    def on_ticker(self, token_id: str, best_bid: Decimal, best_ask: Decimal, size: Decimal) -> MarketSnapshot:
        """Übersetzt ein Ticker-Event in einen 1-Level-Snapshot (Fallback).

        FESTLEGUNG: Fehlende Seiten (Preis 0 oder None) erzeugen KEINE
        Stufe — ein Ticker mit nur Bid-Seite liefert ein leeres Ask-Buch.
        Die Engine soll nie gegen eine synthetische 0-Stufe matchen.

        Args:
            token_id: CLOB Token-ID.
            best_bid: Bester Bid (0 = keine Bid-Seite bekannt).
            best_ask: Bester Ask (0 = keine Ask-Seite bekannt).
            size: Größe am besten Ask.

        Returns:
            Der erzeugte und gecachte MarketSnapshot.
        """
        bids = [(best_bid, size)] if best_bid > 0 else []
        asks = [(best_ask, size)] if best_ask > 0 else []
        return self.on_book_update(token_id, bids=bids, asks=asks)


class BookEventSource(Protocol):
    """Protokoll für PolySentinel-ähnliche Event-Quellen (loose coupling)."""

    def subscribe_book(self, token_ids: list[str], callback: Callable[..., None]) -> None:
        """Registriert einen Callback für Book-Events der gegebenen Tokens."""
        ...


# ---------------------------------------------------------------------------
# Optionaler Read-only-WS-Client (Skeleton für Eigenbetrieb)
# ---------------------------------------------------------------------------


class PolymarketWsFeed:
    """Minimaler READ-ONLY-Websocket-Client für den Polymarket CLOB-Stream.

    NUR Subscriptions auf Marktdaten-Kanäle. Sendet niemals Orders —
    der Charter verbietet das; dieses Modul besitzt keinen Signier- oder
    POST-Pfad überhaupt. Wird nur genutzt, wenn PolySentinel nicht als
    eigener Prozess läuft.

    Beispiel-Nutzung:
        feed = PolymarketWsFeed(PolySentinelBookHandler(cache))
        await feed.run(["0xtokenA", "0xtokenB"])
    """

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(self, handler: PolySentinelBookHandler) -> None:
        """Initialisiert den Feed mit einem Buch-Handler.

        Args:
            handler: PolySentinelBookHandler (füllt den SnapshotCache).
        """
        self._handler = handler
        # Pro Token gepflegter Buch-Zustand fuer Delta-Verdichtung
        # (book = Vollbuch, price_change = Deltas mit size=0 = Entfernung).
        self._books: dict[str, dict[str, dict[Decimal, Decimal]]] = {}

    @staticmethod
    def subscription_payload(token_ids: list[str]) -> dict:
        """Baut das Market-Channel-Subscribe-Frame (Doku: assets_ids = Token-IDs).

        Polymarket erwartet CLOB-Token-IDs unter ``assets_ids``, nicht unter
        ``token_ids``. Ein leeres ``assets_ids`` abonniert nichts.
        """
        return {
            "type": "market",
            "assets_ids": list(token_ids),
            "custom_feature_enabled": True,
        }

    async def run(self, token_ids: list[str]) -> None:  # pragma: no cover
        """Startet den Read-only-Stream (blockierend, via asyncio).

        Args:
            token_ids: CLOB Token-IDs — werden als ``assets_ids`` abonniert.
        """
        try:
            import websockets  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "websockets-Paket fehlt: pip install websockets (Read-only-Feed)"
            ) from e

        async with websockets.connect(self.WS_URL) as ws:
            await ws.send(json.dumps(self.subscription_payload(token_ids)))
            async for raw in ws:
                self.ingest_raw(raw)

    def _ensure_book(self, token: str) -> dict[str, dict[Decimal, Decimal]]:
        """Holt (oder erzeugt) den Buch-Zustand eines Tokens."""
        return self._books.setdefault(token, {"bids": {}, "asks": {}})

    def _apply_change(self, token: str, side: str, price: Decimal, size: Decimal) -> None:
        """Wendet ein Delta auf den Buch-Zustand an (size=0 entfernt Level).

        Args:
            token: CLOB Token-ID.
            side: "BUY"/"bid" -> bids, sonst asks.
            price: Preis-Level.
            size: Neue Größe (0 = Level streichen).
        """
        book = self._ensure_book(token)
        key = "bids" if side.lower() in ("buy", "bid", "bids") else "asks"
        # Validierung am Adapter-Rand: korrupte Level (negatives size,
        # nicht-positiver Preis) verwerfen statt ins Buch zu übernehmen.
        if price <= 0 or size < 0:
            return
        if size == 0:
            book[key].pop(price, None)
        else:
            book[key][price] = size

    def _emit_snapshot(self, token: str) -> None:
        """Emittiert einen vollständigen Snapshot aus dem Buch-Zustand."""
        book = self._ensure_book(token)
        bids = sorted(book["bids"].items(), key=lambda kv: -kv[0])
        asks = sorted(book["asks"].items(), key=lambda kv: kv[0])
        self._handler.on_book_update(token, bids=bids, asks=asks)

    def ingest_raw(self, raw: str | bytes) -> None:
        """Parst eine WS-Payload (dict oder list[dict]) und dispatcht Events."""
        data = json.loads(raw)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._dispatch(item)
            return
        if isinstance(data, dict):
            self._dispatch(data)

    def _dispatch(self, msg: dict) -> None:
        """Verteilt eingehende Marktdaten-Events an den Handler.

        Unterstützt die Polymarket-CLOB-Eventformate:
            - book: Vollbuch {market, bids: [{price, size}], asks: [...]}
            - price_change: Delta {market, changes: [{side, price, size}]}
            - ticker: 1-Level-Fallback {asset_id, best_bid, best_ask, size}

        Args:
            msg: Rohe JSON-Nachricht des Streams.
        """
        event_type = msg.get("event_type")
        token = msg.get("market") or msg.get("asset_id") or msg.get("token_id")

        if event_type == "book" and token:
            book = self._ensure_book(str(token))
            for side_key, entries in (("bids", msg.get("bids") or []), ("asks", msg.get("asks") or [])):
                for entry in entries:
                    price, size = Decimal(str(entry["price"])), Decimal(str(entry["size"]))
                    if price > 0 and size >= 0:
                        book[side_key][price] = size
            self._emit_snapshot(str(token))
        elif event_type == "price_change":
            # Newer CLOB: price_changes[{asset_id,price,size,side}]; legacy: market+changes.
            changes = msg.get("price_changes") or msg.get("changes") or []
            for change in changes:
                if not isinstance(change, dict):
                    continue
                tok = (
                    change.get("asset_id")
                    or change.get("market")
                    or token
                )
                if not tok:
                    continue
                self._apply_change(
                    str(tok),
                    side=str(change.get("side") or change.get("Side") or ""),
                    price=Decimal(str(change["price"])),
                    size=Decimal(str(change["size"])),
                )
                self._emit_snapshot(str(tok))
        elif event_type == "ticker" and token:
            self._handler.on_ticker(
                token_id=str(token),
                best_bid=Decimal(str(msg.get("best_bid", "0"))),
                best_ask=Decimal(str(msg.get("best_ask", "0"))),
                size=Decimal(str(msg.get("size", "0"))),
            )
