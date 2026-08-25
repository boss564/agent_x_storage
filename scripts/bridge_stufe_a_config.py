"""Frozen Stufe-A pre-reg constants. Do not edit after 2026-08-17 without a new pre-reg."""

from __future__ import annotations

from datetime import datetime, timezone

# Observation window (inclusive, UTC). 90 calendar days.
WINDOW_START_UTC = datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END_UTC = datetime(2026, 8, 17, 23, 59, 59, tzinfo=timezone.utc)

LAGS_MIN: tuple[int, ...] = tuple(range(0, 31))
N_LAGS = len(LAGS_MIN)
N_DIRECTIONS = 2
N_METRICS = 2  # Hawkes gamma, CTE
N_PAIRS = 2  # treatment, control
N_TESTS = N_DIRECTIONS * N_LAGS * N_METRICS * N_PAIRS  # 248

ALPHA = 0.05
FDR_Q = 0.05
N_SURROGATES = 1000
JITTER_SECONDS = 300.0  # ±5 minutes
N_MIN_EVENTS = 100
DRIVER_COVERAGE_MIN = 0.80
DELTA_TAU_SEC = 60.0
BRIDGE_STUFE_A_SEED = 20260817

# OmniBridge multi-token mediators (not AMB, not native xDAI bridge).
OMNIBRIDGE_ETH = "0x88ad09518695c6c3712AC10a214bE5109a655671"
OMNIBRIDGE_GNOSIS = "0xf6A78083ca3e2a662D6dd1703c939c8aCE2e268d"

EVENT_TOKENS_BRIDGING_INITIATED = "TokensBridgingInitiated(address,address,uint256,bytes32)"
EVENT_TOKENS_BRIDGED = "TokensBridged(address,address,uint256,bytes32)"
TOPIC_TOKENS_BRIDGING_INITIATED = "0x59a9a8027b9c87b961e254899821c9a276b5efc35d1f7409ea4f291470f1629a"
TOPIC_TOKENS_BRIDGED = "0x9afd47907e25028cdaca89d193518c302bbb128617d5a992c5abd45815526593"

# Uniswap Universal Router versions from universal-router-sdk CHAIN_CONFIGS
# (fetched 2026-08-17). Union, so a mid-window migration is not HARKing.
UNISWAP_UR_ETH: tuple[str, ...] = (
    "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD",  # V1.2
    "0x66a9893cc07d91d95644aedd05d03f95e1dba8af",  # V2.0
    "0x4C82D1fBFe28C977cBB58D8C7FF8FCF9F70a2cCA",  # V2.1.1
    "0x0542093271A31f6FC1DADB232bd59eeb27de780F",  # V2.2.0
)
UNISWAP_UR_ARBITRUM: tuple[str, ...] = (
    "0x5E325eDA8064b456f4781070C0738d849c824258",  # V1.2
    "0xa51afafe0263b40edaef0df8781ea9aa03e381a3",  # V2.0
    "0x8B844f885672f333Bc0042cB669255f93a4C1E6b",  # V2.1.1
)

CEX_VENUES: tuple[str, ...] = ("binance", "coinbase", "kraken", "okx", "bybit")

# Native xDAI bridge — excluded (different mechanism).
XDAI_BRIDGE_ETH = "0x4aa42145Aa6Ebf72e164C9bBC74fbD3788045016"
XDAI_BRIDGE_GNOSIS = "0x7301CFA0e1756B71869E93d4e4Dca5c7d0eb0AA6"

STREAM_IDS: tuple[str, ...] = (
    "treat_eth",
    "treat_gnosis",
    "ctrl_eth",
    "ctrl_arbitrum",
)

# Confirmatory test vector order (one BH over all 248). Do not reorder.
PAIR_IDS: tuple[str, ...] = ("treatment", "control")
METRIC_IDS: tuple[str, ...] = ("hawkes", "cte")
DIRECTION_IDS: tuple[str, ...] = ("ab", "ba")  # treatment: ETH→Gnosis / Gnosis→ETH


def n_minute_bins() -> int:
    return calendar_days_inclusive() * 24 * 60


def _norm(addr: str) -> str:
    return addr.lower()


def calendar_days_inclusive() -> int:
    return (WINDOW_END_UTC.date() - WINDOW_START_UTC.date()).days + 1


def assert_frozen_addresses(manifest_addresses: dict[str, object]) -> None:
    """Raise if a capture manifest drifted from this lock file."""
    got_eth = _norm(str(manifest_addresses["omnibridge_eth"]))
    got_gno = _norm(str(manifest_addresses["omnibridge_gnosis"]))
    if got_eth != _norm(OMNIBRIDGE_ETH) or got_gno != _norm(OMNIBRIDGE_GNOSIS):
        raise AssertionError("OmniBridge addresses drifted from pre-reg lock")
    ur_eth = {_norm(a) for a in manifest_addresses["uniswap_ur_eth"]}  # type: ignore[union-attr]
    ur_arb = {_norm(a) for a in manifest_addresses["uniswap_ur_arbitrum"]}  # type: ignore[union-attr]
    if ur_eth != {_norm(a) for a in UNISWAP_UR_ETH}:
        raise AssertionError("ETH Uniswap UR set drifted from pre-reg lock")
    if ur_arb != {_norm(a) for a in UNISWAP_UR_ARBITRUM}:
        raise AssertionError("Arbitrum Uniswap UR set drifted from pre-reg lock")
    topics = {_norm(str(t)) for t in manifest_addresses["topic0"]}  # type: ignore[union-attr]
    locked = {_norm(TOPIC_TOKENS_BRIDGING_INITIATED), _norm(TOPIC_TOKENS_BRIDGED)}
    if topics != locked:
        raise AssertionError("OmniBridge topic0 drifted from pre-reg lock")
