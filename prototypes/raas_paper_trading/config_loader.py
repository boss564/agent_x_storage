"""Load frozen paper-trading fee/slippage config (P3)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = Path("config/paper_trading_config.json")


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
    config_hash: str
    config_path: str

    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> "PaperTradingSettings":
        p = config_path(path)
        raw = load_paper_trading_config(p)
        fees = raw.get("exchange", {}).get("fees", {})
        slip = raw.get("slippage", {})
        paper = raw.get("paper_trading", {})
        if paper.get("live_execution") is True:
            raise ValueError("paper_trading.live_execution must be false")
        maker = Decimal(str(fees.get("maker", "0.00075")))
        taker = Decimal(str(fees.get("taker", "0.00075")))
        return cls(
            maker_rate=maker,
            taker_rate=taker,
            slippage_mode=str(slip.get("mode", "dynamic")),
            fallback_percent=Decimal(str(slip.get("fallback_percent", "0.001"))),
            orderbook_depth_levels=int(slip.get("orderbook_depth_levels", 10)),
            initial_balance_eur=Decimal(str(paper.get("initial_balance_eur", "1000.0"))),
            exchange_name=str(raw.get("exchange", {}).get("name", "binance")),
            config_hash=config_manifest_hash(p),
            config_path=str(p),
        )
