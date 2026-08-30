"""Extensible token / macro keywords for keyword_v1.

Short tickers must be matched with word boundaries by the detector.
Not investment advice.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Ticker → phrases. Short codes (eth, sol, uni, …) are word-bounded in sentiment.py.
TOKEN_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "BTC": ("bitcoin", "btc", "satoshi"),
    "ETH": ("ethereum", "eth", "vitalik", "layer2", "layer 2"),
    "SOL": ("solana", "sol"),
    "BNB": ("binance", "bnb"),
    "XRP": ("ripple", "xrp"),
    "LINK": ("chainlink", "link"),
    "AVAX": ("avalanche", "avax"),
    "SUI": ("sui",),
    "UNI": ("uniswap", "uni"),
    "AAVE": ("aave",),
    "DOGE": ("dogecoin", "doge"),
    "PEPE": ("pepe",),
    "SHIB": ("shiba", "shib"),
}

MACRO_KEYWORDS: Tuple[str, ...] = (
    "fed",
    "federal reserve",
    "sec",
    "inflation",
    "rates",
    "bafin",
    "mica",
    "micar",
)

GENERAL_KEYWORDS: Tuple[str, ...] = (
    "crypto",
    "blockchain",
    "token",
    "market",
    "bull",
    "bear",
)

WATCH_TERMS: Tuple[str, ...] = tuple(
    kw for kws in TOKEN_KEYWORDS.values() for kw in kws
)

# Entity catalogs (ids are stable graph nodes; phrases are matched in sentiment.py).
# Single-token phrases are word-bounded. Do not use a generic "news_agent" substring.
CHAIN_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "ethereum": ("ethereum", "eth", "layer2", "layer 2"),
    "solana": ("solana", "sol"),
    "avalanche": ("avalanche", "avax"),
    "sui": ("sui",),
    "polygon": ("polygon", "matic"),
    "arbitrum": ("arbitrum", "arb"),
    "optimism": ("optimism", "op"),
}

BRIDGE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "wormhole": ("wormhole",),
    "layerzero": ("layerzero", "layer zero"),
    "axelar": ("axelar",),
}

PROTOCOL_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "uniswap": ("uniswap", "uni"),
    "aave": ("aave",),
    "chainlink": ("chainlink", "link"),
}

PERSON_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "vitalik": ("vitalik buterin", "vitalik"),
    "saylor": ("michael saylor", "saylor"),
    "cz": ("changpeng zhao", "cz"),
}

ENTITY_CATEGORIES: Tuple[str, ...] = ("chains", "bridges", "protocols", "persons")


def empty_entities() -> Dict[str, List[str]]:
    return {cat: [] for cat in ENTITY_CATEGORIES}
