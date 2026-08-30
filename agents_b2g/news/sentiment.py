"""Keyword sentiment — no LLM, no API key.

Heuristic only. Scores are diagnostic, not investment advice.
"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

from agents_b2g.news.config import (
    BRIDGE_KEYWORDS,
    CHAIN_KEYWORDS,
    ENTITY_CATEGORIES,
    GENERAL_KEYWORDS,
    MACRO_KEYWORDS,
    PERSON_KEYWORDS,
    PROTOCOL_KEYWORDS,
    TOKEN_KEYWORDS,
    WATCH_TERMS,
    empty_entities,
)

_ENTITY_CATALOGS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "chains": CHAIN_KEYWORDS,
    "bridges": BRIDGE_KEYWORDS,
    "protocols": PROTOCOL_KEYWORDS,
    "persons": PERSON_KEYWORDS,
}

BULLISH = (
    "etf approval",
    "etf inflows",
    "all-time high",
    "ath",
    "rally",
    "surge",
    "breakout",
    "adoption",
    "institutional",
    "bullish",
    "rallying",
    "record high",
    "inflow",
    "spot etf",
    "halving",
    "accumulat",
)

BEARISH = (
    "hack",
    "exploit",
    "hacked",
    "sec charges",
    "lawsuit",
    "crash",
    "crashs",
    "plunge",
    "sell-off",
    "selloff",
    "liquidation",
    "bankrupt",
    "fraud",
    "outflow",
    "bearish",
    "collapse",
    "rug pull",
    "insolvent",
    "default",
    "ban ",
    "banned",
)

# Short / ambiguous tokens: word boundary only (WHETHER, unique, also, sold, …).
_WORD_BOUND_MAX = 4


def _hits_keyword(text_lower: str, keyword: str) -> bool:
    kw = keyword.lower().strip()
    if not kw:
        return False
    if " " in kw:
        return kw in text_lower
    if len(kw) <= _WORD_BOUND_MAX:
        return re.search(rf"\b{re.escape(kw)}\b", text_lower) is not None
    return kw in text_lower


def _any_keyword(text_lower: str, keywords: Sequence[str]) -> bool:
    return any(_hits_keyword(text_lower, kw) for kw in keywords)


def _hits_entity_keyword(text_lower: str, keyword: str) -> bool:
    """Word-bound every single token (matic ≠ automatic, op ≠ open, cz ≠ because)."""
    kw = keyword.lower().strip()
    if not kw:
        return False
    if " " in kw:
        return kw in text_lower
    return re.search(rf"\b{re.escape(kw)}\b", text_lower) is not None


def detect_entities(text: str) -> Dict[str, List[str]]:
    """Stable graph ids per category. Empty lists when nothing matches."""
    low = text.lower()
    found = empty_entities()
    for category in ENTITY_CATEGORIES:
        catalog = _ENTITY_CATALOGS[category]
        for name, keywords in catalog.items():
            if any(_hits_entity_keyword(low, kw) for kw in keywords):
                found[category].append(name)
    return found


def detect_assets(text: str) -> List[str]:
    """Tickers in config order, then MACRO, then GENERAL (only if no ticker and no MACRO)."""
    low = text.lower()
    found: List[str] = []
    for token, keywords in TOKEN_KEYWORDS.items():
        if _any_keyword(low, keywords):
            found.append(token)
    if _any_keyword(low, MACRO_KEYWORDS):
        found.append("MACRO")
    if not found and _any_keyword(low, GENERAL_KEYWORDS):
        found.append("GENERAL")
    return found


def detect_symbols(text: str) -> List[str]:
    """Ticker symbols only (no MACRO/GENERAL)."""
    return [a for a in detect_assets(text) if a not in ("MACRO", "GENERAL")]


def classify_coin(title: str) -> str:
    """Word-bounded ETH vs default BTC. WHETHER / Together / Ethics / Netherlands are not ETH."""
    t = title.upper()
    if "ETHEREUM" in t or re.search(r"\bETH\b", t):
        return "ETH"
    return "BTC"


def is_relevant(title: str, summary: str, *, watch: Sequence[str] = WATCH_TERMS) -> bool:
    """Ticker or MACRO with word boundaries — substring 'eth' in whether is not ETH."""
    text = f"{title} {summary}"
    assets = detect_assets(text)
    if any(a not in ("GENERAL",) for a in assets):
        return True
    defaults = {w.lower() for w in WATCH_TERMS}
    extra = [w for w in watch if w.lower() not in defaults]
    if not extra:
        return False
    low = text.lower()
    return any(_hits_keyword(low, term) for term in extra)


def score_sentiment(title: str, summary: str) -> Dict[str, object]:
    """Return sentiment in {-1, 0, 1}, confidence 0..1, reason, symbols, assets, entities."""
    text = f"{title} {summary}".lower()
    assets = detect_assets(text)
    entities = detect_entities(text)
    symbols = [a for a in assets if a not in ("MACRO", "GENERAL")]
    bull = [w for w in BULLISH if w in text]
    bear = [w for w in BEARISH if w in text]
    n_b, n_s = len(bull), len(bear)
    if n_b == 0 and n_s == 0:
        return {
            "sentiment": 0,
            "label": "NEUTRAL",
            "confidence": 0.15 if symbols else 0.05,
            "reason": "no polarity keywords",
            "symbols": symbols,
            "assets": assets,
            "entities": entities,
        }
    if n_b > n_s:
        conf = min(0.95, 0.45 + 0.15 * n_b)
        return {
            "sentiment": 1,
            "label": "BULLISH",
            "confidence": round(conf, 3),
            "reason": "keywords: " + ", ".join(bull[:4]),
            "symbols": symbols,
            "assets": assets,
            "entities": entities,
        }
    if n_s > n_b:
        conf = min(0.95, 0.45 + 0.15 * n_s)
        return {
            "sentiment": -1,
            "label": "BEARISH",
            "confidence": round(conf, 3),
            "reason": "keywords: " + ", ".join(bear[:4]),
            "symbols": symbols,
            "assets": assets,
            "entities": entities,
        }
    return {
        "sentiment": 0,
        "label": "NEUTRAL",
        "confidence": 0.35,
        "reason": "mixed keywords",
        "symbols": symbols,
        "assets": assets,
        "entities": entities,
    }
