"""Load frozen paper-trading fee/slippage config (P3)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_CONFIG_PATH = Path("config/paper_trading_config.json")

PAIR_MANIFEST_SCHEMA = "raas_pair_manifest_v1"

VALID_VOLATILITY_PROFILES = frozenset({"low", "medium", "high", "unknown"})


@dataclass(frozen=True)
class PaperPair:
    """Shadow pair — fixed notional per symbol (no equity feedback)."""

    symbol: str
    notional_eur: Decimal
    volatility_profile: str

    def __post_init__(self) -> None:
        sym = self.symbol.upper()
        object.__setattr__(self, "symbol", sym)
        profile = self.volatility_profile.lower()
        if profile not in VALID_VOLATILITY_PROFILES:
            profile = "unknown"
        object.__setattr__(self, "volatility_profile", profile)


def _repo_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "config" / "paper_trading_config.json").is_file():
        return cwd
    return Path(__file__).resolve().parents[2]


def config_path(explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        return explicit
    return _repo_root() / DEFAULT_CONFIG_PATH


def load_paper_trading_config(
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    p = config_path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"Paper config missing: {p}. "
            "Add config/paper_trading_config.json before fee/slippage runs."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def config_manifest_hash(path: Optional[Path] = None) -> str:
    """SHA-256 of canonical JSON — freeze before 30-day eval."""
    data = load_paper_trading_config(path)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def pair_manifest_payload(
    symbol: str,
    raw: Dict[str, Any],
    *,
    pair: Optional[PaperPair] = None,
) -> Dict[str, Any]:
    """Fill-affecting params per symbol — excludes other pairs and analytical labels."""
    sym = symbol.upper()
    shadow = raw.get("shadow_fill", {})
    fees = raw.get("exchange", {}).get("fees", {})
    slip = raw.get("slippage", {})
    if pair is not None:
        notional = str(pair.notional_eur)
    else:
        notional = str(shadow.get("notional_eur", "100.0"))
    return {
        "schema": PAIR_MANIFEST_SCHEMA,
        "symbol": sym,
        "exchange": {
            "name": raw.get("exchange", {}).get("name", "binance"),
            "fees": {
                "maker": fees.get("maker"),
                "taker": fees.get("taker"),
            },
        },
        "slippage": {
            "mode": slip.get("mode"),
            "fallback_percent": slip.get("fallback_percent"),
            "orderbook_depth_levels": slip.get("orderbook_depth_levels"),
        },
        "shadow_fill": {
            "notional_eur": notional,
            "attach_orderbook": shadow.get("attach_orderbook", True),
        },
    }


def pair_manifest_hash(
    symbol: str,
    path: Optional[Path] = None,
    *,
    raw: Optional[Dict[str, Any]] = None,
    pair: Optional[PaperPair] = None,
) -> str:
    """Per-symbol definition hash — stable when only other pairs change."""
    p = config_path(path)
    data = raw if raw is not None else load_paper_trading_config(p)
    if pair is None and raw is None:
        settings_pairs = _parse_pairs(
            data.get("pairs"),
            default_notional=Decimal(
                str(data.get("shadow_fill", {}).get("notional_eur", "100.0"))
            ),
        )
        for candidate in settings_pairs:
            if candidate.symbol == symbol.upper():
                pair = candidate
                break
    payload = pair_manifest_payload(symbol, data, pair=pair)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PaperTradingSettings:
    """Parsed config for ledger / slippage."""

    maker_rate: Decimal
    taker_rate: Decimal
    slippage_mode: str
    fallback_percent: Decimal
    orderbook_depth_levels: int
    initial_balance_eur: Decimal
    exchange_name: str
    depth_symbols: tuple[str, ...]
    pairs: tuple[PaperPair, ...]
    depth_rest_limit: int
    depth_worm_path: str
    depth_interval_s: int
    shadow_notional_eur: Decimal
    attach_orderbook: bool
    config_hash: str
    config_path: str

    def pair_for(self, symbol: str) -> Optional[PaperPair]:
        sym = symbol.upper()
        for pair in self.pairs:
            if pair.symbol == sym:
                return pair
        return None

    def notional_for(self, symbol: str) -> Decimal:
        pair = self.pair_for(symbol)
        return pair.notional_eur if pair is not None else self.shadow_notional_eur

    def volatility_profile_for(self, symbol: str) -> Optional[str]:
        pair = self.pair_for(symbol)
        return pair.volatility_profile if pair is not None else None

    def pair_manifest_hash_for(self, symbol: str) -> str:
        raw = load_paper_trading_config(Path(self.config_path))
        return pair_manifest_hash(
            symbol,
            pair=self.pair_for(symbol),
            raw=raw,
        )

    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> "PaperTradingSettings":
        p = config_path(path)
        raw = load_paper_trading_config(p)
        fees = raw.get("exchange", {}).get("fees", {})
        slip = raw.get("slippage", {})
        paper = raw.get("paper_trading", {})
        depth = raw.get("depth_ingest", {})
        shadow = raw.get("shadow_fill", {})
        if paper.get("live_execution") is True:
            raise ValueError("paper_trading.live_execution must be false")
        maker = Decimal(str(fees.get("maker", "0.00075")))
        taker = Decimal(str(fees.get("taker", "0.00075")))
        default_notional = Decimal(str(shadow.get("notional_eur", "100.0")))
        pairs = _parse_pairs(raw.get("pairs"), default_notional=default_notional)
        if pairs:
            depth_symbols = tuple(p.symbol for p in pairs)
        else:
            symbols = depth.get("symbols") or ["ETHUSDC", "BTCUSDC"]
            depth_symbols = tuple(str(s).upper() for s in symbols)
        return cls(
            maker_rate=maker,
            taker_rate=taker,
            slippage_mode=str(slip.get("mode", "dynamic")),
            fallback_percent=Decimal(str(slip.get("fallback_percent", "0.001"))),
            orderbook_depth_levels=int(slip.get("orderbook_depth_levels", 10)),
            initial_balance_eur=Decimal(str(paper.get("initial_balance_eur", "1000.0"))),
            exchange_name=str(raw.get("exchange", {}).get("name", "binance")),
            depth_symbols=depth_symbols,
            pairs=pairs,
            depth_rest_limit=int(depth.get("rest_limit", 10)),
            depth_worm_path=str(depth.get("worm_path", "logs/worm/depth_snapshots.jsonl")),
            depth_interval_s=int(depth.get("interval_s", 60)),
            shadow_notional_eur=default_notional,
            attach_orderbook=bool(shadow.get("attach_orderbook", True)),
            config_hash=config_manifest_hash(p),
            config_path=str(p),
        )


def _parse_pairs(
    raw_pairs: Any,
    *,
    default_notional: Decimal,
) -> Tuple[PaperPair, ...]:
    if not raw_pairs:
        return ()
    out: list[PaperPair] = []
    for row in raw_pairs:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym:
            continue
        notional = Decimal(str(row.get("notional_eur", default_notional)))
        profile = str(row.get("volatility_profile", "unknown"))
        out.append(
            PaperPair(
                symbol=sym,
                notional_eur=notional,
                volatility_profile=profile,
            )
        )
    return tuple(out)
