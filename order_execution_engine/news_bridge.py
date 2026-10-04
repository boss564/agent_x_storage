"""NewsBot → Shadow Execution Engine Bridge (C6).

Charter: diagnostic_only=true, live_execution=false, order_send=false.
Kein Book-Fetch, kein Order-Relayer — nur ``on_signal`` gegen WS-Cache.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping, Optional, Protocol

from order_execution_engine.models import Direction, SignalPayload
from order_execution_engine.market_data_feed import SnapshotCache

_LOG = logging.getLogger(__name__)

# Feste Namespace-UUID für die Messperiode (auch in config_json belegt).
SIGNAL_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


@dataclass(frozen=True)
class MarketTarget:
    """Aufgelöster Polymarket-Markt aus der Allowlist."""

    asset: str
    token_id: str
    market_id: str


class MarketResolver:
    """Statische Allowlist Asset → token_id/market_id (v1, bewusst begrenzt)."""

    def __init__(self, allowlist: Mapping[str, Mapping[str, str]]) -> None:
        self._map: dict[str, MarketTarget] = {}
        for asset, entry in allowlist.items():
            key = asset.strip().upper()
            self._map[key] = MarketTarget(
                asset=key,
                token_id=str(entry["token_id"]),
                market_id=str(entry["market_id"]),
            )

    def resolve(self, target_assets: list[str] | tuple[str, ...] | None) -> Optional[MarketTarget]:
        """Erstes Allowlist-Match aus target_assets; sonst None."""
        if not target_assets:
            return None
        for raw in target_assets:
            hit = self._map.get(str(raw).strip().upper())
            if hit is not None:
                return hit
        return None

    def entries(self) -> dict[str, dict[str, str]]:
        """Allowlist für config_json / Auswertung."""
        return {
            t.asset: {"token_id": t.token_id, "market_id": t.market_id}
            for t in self._map.values()
        }


@dataclass
class BridgePolicy:
    """Minimale Side/Size/Confidence-Vorschrift — eingefroren pro Run."""

    theta: Decimal = Decimal("0.1")
    size_by_impact: dict[str, Decimal] = field(default_factory=lambda: {
        "LOW": Decimal("25"),
        "MEDIUM": Decimal("50"),
        "MID": Decimal("50"),
        "HIGH": Decimal("100"),
    })
    default_size: Decimal = Decimal("25")
    confidence_mode: str = "abs_sentiment_pct"
    _pending_sizes: dict[uuid.UUID, Decimal] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> "BridgePolicy":
        sizes = {
            str(k).upper(): Decimal(str(v))
            for k, v in (cfg.get("size_by_impact") or {}).items()
        }
        return cls(
            theta=Decimal(str(cfg.get("theta", "0.1"))),
            size_by_impact=sizes or cls().size_by_impact,
            default_size=Decimal(str(cfg.get("default_size", "25"))),
            confidence_mode=str(cfg.get("confidence_mode", "abs_sentiment_pct")),
        )

    def direction_from(self, sentiment_score: Any) -> Direction:
        score = Decimal(str(sentiment_score))
        if score >= self.theta:
            return Direction.UP
        if score <= -self.theta:
            return Direction.DOWN
        return Direction.NEUTRAL

    def confidence_from(self, sentiment_score: Any) -> Decimal:
        """Pflichtfeld 0–100. Default: |sentiment| × 100, geklemmt."""
        score = abs(Decimal(str(sentiment_score)))
        if self.confidence_mode == "fixed_80":
            return Decimal("80")
        pct = (score * Decimal("100")).quantize(Decimal("0.01"))
        if pct > Decimal("100"):
            return Decimal("100")
        return pct

    def size_for_impact(self, impact_level: Any) -> Decimal:
        key = str(impact_level or "LOW").strip().upper()
        return self.size_by_impact.get(key, self.default_size)

    def remember_size(self, signal_id: uuid.UUID, size: Decimal) -> None:
        self._pending_sizes[signal_id] = size

    def size_fn(self, signal: SignalPayload, portfolio_snapshot: Any) -> Decimal:
        """Kanon-Seam für ShadowExecutionEngine(size_fn=...)."""
        return self._pending_sizes.pop(signal.signal_id, self.default_size)

    def snapshot(self) -> dict[str, Any]:
        return {
            "theta": str(self.theta),
            "size_by_impact": {k: str(v) for k, v in self.size_by_impact.items()},
            "default_size": str(self.default_size),
            "confidence_mode": self.confidence_mode,
        }


class DedupStore(Protocol):
    def claim(self, item_id: str) -> bool: ...
    def bind_telemetry(self, item_id: str, telemetry_seq: Optional[int]) -> None: ...


class SqliteDedupStore:
    """Dedup über ``dispatched_signals`` (restart-sicher)."""

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    def claim(self, item_id: str) -> bool:
        return bool(self._storage.claim_dispatch(item_id))

    def bind_telemetry(self, item_id: str, telemetry_seq: Optional[int]) -> None:
        self._storage.bind_dispatch_telemetry(item_id, telemetry_seq)


def parse_news_timestamp(raw: str) -> datetime:
    """ISO → aware datetime; naive → UTC."""
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


class NewsBridge:
    """Verdrahtet news_agent_multi/v1 → ``engine.on_signal`` (kein Fetch)."""

    def __init__(
        self,
        engine: Any,
        cache: SnapshotCache,
        resolver: MarketResolver,
        dedup: DedupStore,
        policy: BridgePolicy,
        run_id: int,
        *,
        signal_namespace: uuid.UUID = SIGNAL_NAMESPACE,
        discard_logger: Optional[Callable[[str, str], None]] = None,
        storage: Any = None,
    ) -> None:
        self._engine = engine
        self._cache = cache
        self._resolver = resolver
        self._dedup = dedup
        self._policy = policy
        self._run_id = run_id
        self._namespace = signal_namespace
        self._storage = storage
        self._discard = discard_logger or (
            lambda item_id, reason: _LOG.info(
                "bridge_discard item_id=%s reason=%s run_id=%s",
                item_id, reason, run_id,
            )
        )
        self.discards: list[tuple[str, str]] = []

    def _log_discard(self, item_id: str, reason: str) -> None:
        self.discards.append((item_id, reason))
        self._discard(item_id, reason)
        if self._storage is not None:
            self._storage.log_bridge_discard(item_id, reason)

    def on_news_item(self, item: dict) -> bool:
        """Dispatched ein News-Item. False = Duplikat/verworfen."""
        item_id = item.get("item_id")
        if not item_id:
            return False
        if not self._dedup.claim(str(item_id)):
            return False

        target = self._resolver.resolve(item.get("target_assets") or [])
        if target is None:
            self._log_discard(str(item_id), "unresolved_asset")
            return False

        snapshot = self._cache.get(target.token_id)
        if snapshot is None:
            self._log_discard(str(item_id), "no_book")
            return False

        signal_id = uuid.uuid5(self._namespace, str(item_id))
        raw_ts = item.get("timestamp")
        if not raw_ts:
            self._log_discard(str(item_id), "missing_timestamp")
            return False

        size = self._policy.size_for_impact(item.get("impact_level"))
        self._policy.remember_size(signal_id, size)

        signal = SignalPayload(
            signal_id=signal_id,
            source="newsbot",
            target_token_id=target.token_id,
            market_id=target.market_id,
            direction=self._policy.direction_from(item.get("sentiment_score", 0)),
            confidence=self._policy.confidence_from(item.get("sentiment_score", 0)),
            suggested_price=None,
            timestamp=parse_news_timestamp(str(raw_ts)),
        )
        self._engine.on_signal(signal, snapshot)
        # telemetry_seq wird vom Sink nachgezogen — hier optional None
        self._dedup.bind_telemetry(str(item_id), None)
        return True
