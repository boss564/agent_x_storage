"""Chainlink oracle helpers for Wave 38 Agent 2 — code reuse from V3 capture/resolve.

No network required in fixture mode. Topic0 via keccak (not hardcoded literals
in parsers — computed once here as the single source of truth).
"""

from __future__ import annotations

from eth_hash.auto import keccak

# Single source of truth — same as bridge_stufe_a_v3_chainlink_capture.py
TOPIC_ANSWER_UPDATED = "0x" + keccak(b"AnswerUpdated(int256,uint256,uint256)").hex()

SEL_AGGREGATOR = "0x" + keccak(b"aggregator()")[:4].hex()
SEL_LATEST_ROUND = "0x" + keccak(b"latestRoundData()")[:4].hex()
SEL_PHASE_AGGS = "0x" + keccak(b"phaseAggregators(uint16)")[:4].hex()

ANSWER_DECIMALS = 8
ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# Bridge Pre-Reg §3.0 + WAVE38_LIVE_PREREG §2 exclusions (hard block)
EXCLUDED_FEEDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("ethereum", "USDT/USD"),  # Bridge §3.0.1 feed-strict
        ("ethereum", "GNO/ETH"),
        ("gnosis", "GNO/ETH"),
    }
)

PLAUSIBILITY_BANDS_USD: dict[str, tuple[float, float]] = {
    "ETH/USD": (1e2, 1e4),
    "WBTC/USD": (1e3, 1e6),
    "BTC/USD": (1e3, 1e6),
    "USDC/USD": (0.9, 1.1),
    "USDT/USD": (0.9, 1.1),
    "GNO/USD": (1e0, 1e3),
}


def decode_topic_int256(topic: str) -> int:
    val = int(topic, 16)
    if val >= 2**255:
        val -= 2**256
    return val


def decode_topic_uint256(topic: str) -> int:
    return int(topic, 16)


def parse_answer_updated_log(log: dict) -> dict:
    """Parse AnswerUpdated topics/data — Topic0 must already match."""
    topics = log.get("topics") or []
    if len(topics) < 3:
        raise ValueError(f"AnswerUpdated expected >=3 topics, got {len(topics)}")
    data = log.get("data", "0x")
    body = data[2:] if str(data).startswith("0x") else str(data)
    if len(body) < 64:
        raise ValueError(f"AnswerUpdated data too short: {data!r}")
    updated_at = int(body[0:64], 16)
    return {
        "current": str(decode_topic_int256(topics[1])),
        "round_id": str(decode_topic_uint256(topics[2])),
        "updated_at": updated_at,
    }


def encode_answer_updated_topics(current: int, round_id: int) -> list[str]:
    """Build topics for fixture seeding (Topic0 from keccak)."""

    def word(v: int) -> str:
        if v < 0:
            v = (1 << 256) + v
        return "0x" + format(v, "064x")

    return [TOPIC_ANSWER_UPDATED, word(current), word(round_id)]


def is_excluded_feed(chain: str, feed: str) -> bool:
    return (chain.lower(), feed) in EXCLUDED_FEEDS


def plausibility_check(feed_name: str, usd: float) -> tuple[str, str | None]:
    band = PLAUSIBILITY_BANDS_USD.get(feed_name)
    if band is None:
        return "fail", f"no_plausibility_band_for_{feed_name}"
    lo, hi = band
    if lo <= usd <= hi:
        return "pass", None
    return "fail", f"latest_answer_usd={usd:.6g} outside [{lo:g}, {hi:g}]"


def fixture_resolved_plan() -> dict:
    """Synthetic Docs→ABI→On-Chain resolution for offline tests."""
    return {
        "all_resolved": True,
        "capture_release": "RELEASED",
        "fixture": True,
        "chains": {
            "ethereum": {
                "feeds": [
                    {
                        "name": "ETH/USD",
                        "status": "RESOLVED",
                        "proxy": "0x" + ("e1" * 20),
                        "current_aggregator": "0x" + ("a1" * 20),
                        "active_aggregators": [
                            "0x" + ("a1" * 20),
                            "0x" + ("a2" * 20),  # phase history
                        ],
                        "phases": {"1": "0x" + ("a2" * 20), "7": "0x" + ("a1" * 20)},
                        "latest_answer_usd": 2500.0,
                    },
                    {
                        "name": "USDC/USD",
                        "status": "RESOLVED",
                        "proxy": "0x" + ("e2" * 20),
                        "current_aggregator": "0x" + ("b1" * 20),
                        "active_aggregators": ["0x" + ("b1" * 20)],
                        "phases": {"1": "0x" + ("b1" * 20)},
                        "latest_answer_usd": 1.001,
                    },
                    {
                        "name": "USDT/USD",  # excluded by FeedExclusionEnforcer
                        "status": "RESOLVED",
                        "proxy": "0x" + ("e3" * 20),
                        "current_aggregator": "0x" + ("c1" * 20),
                        "active_aggregators": ["0x" + ("c1" * 20)],
                        "phases": {"1": "0x" + ("c1" * 20)},
                        "latest_answer_usd": 1.0,
                    },
                ]
            },
            "gnosis": {
                "feeds": [
                    {
                        "name": "GNO/USD",
                        "status": "RESOLVED",
                        "proxy": "0x" + ("g1" * 20),
                        "current_aggregator": "0x" + ("d1" * 20),
                        "active_aggregators": [
                            "0x" + ("d1" * 20),
                            "0x" + ("d2" * 20),
                            "0x" + ("d3" * 20),
                            "0x" + ("d4" * 20),  # 4 phases like Bridge USDC Gnosis
                        ],
                        "phases": {
                            "1": "0x" + ("d4" * 20),
                            "2": "0x" + ("d3" * 20),
                            "3": "0x" + ("d2" * 20),
                            "4": "0x" + ("d1" * 20),
                        },
                        "latest_answer_usd": 120.0,
                    },
                    {
                        "name": "GNO/ETH",  # excluded
                        "status": "RESOLVED",
                        "proxy": "0x" + ("g2" * 20),
                        "current_aggregator": "0x" + ("e9" * 20),
                        "active_aggregators": ["0x" + ("e9" * 20)],
                        "phases": {"1": "0x" + ("e9" * 20)},
                        "latest_answer_usd": 0.05,
                    },
                ]
            },
        },
    }


def minute_index(ts: int, window_start_ts: int, n_bins: int) -> int | None:
    idx = (ts - window_start_ts) // 60
    if 0 <= idx < n_bins:
        return idx
    return None
