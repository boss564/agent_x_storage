"""Read-only Neo4j reader for AstroCore Class-C liquidation events (D2).

All queries require ``since_ts`` and ``LIMIT`` — unbounded scans are forbidden.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

# Fail-closed: word boundaries so SET at line start / query start is blocked,
# while OFFSET / SETTINGS do not match.
_WRITE_TOKENS = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE)\b")


def assert_read_only_cypher(cypher: str) -> None:
    """Reject write Cypher in the read-only hook (fail-closed)."""
    match = _WRITE_TOKENS.search(cypher.upper())
    if match:
        raise RuntimeError(f"Write query blocked in read-only hook: {match.group(1)}")

DEFAULT_LOOKBACK_DAYS = int(os.environ.get("ASTROCORE_NEO4J_LOOKBACK_DAYS", "7"))
DEFAULT_LIMIT = int(os.environ.get("ASTROCORE_NEO4J_LIMIT", "10000"))
MAX_LOOKBACK_DAYS = 90

# Dual-schema: CherryStudio listener (ts/phase/usd_value) and
# RaaS/AstroCore seed (timestamp/funding_phase/amount_usd).
LIQUIDATION_QUERY = """
MATCH (l:LiquidationEvent)
WHERE coalesce(l.timestamp, l.ts) >= $since_ts
RETURN l.timestamp AS timestamp,
       l.ts AS ts,
       l.funding_phase AS funding_phase,
       l.phase AS phase,
       l.amount_usd AS amount_usd,
       l.usd_value AS usd_value,
       l.symbol AS symbol,
       l.is_clustered AS is_clustered
ORDER BY coalesce(l.timestamp, l.ts) ASC
LIMIT $limit
"""

LIQUIDATION_AGGREGATE_QUERY = """
MATCH (l:LiquidationEvent)
WHERE coalesce(l.timestamp, l.ts) >= $since_ts
RETURN count(l) AS n,
       min(coalesce(l.timestamp, l.ts)) AS ts_min,
       max(coalesce(l.timestamp, l.ts)) AS ts_max
"""


def _coalesce(*values: Any) -> Any:
    """Return the first value that is not None (0.0 and False are valid)."""
    for value in values:
        if value is not None:
            return value
    return None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def normalize_liquidation_record(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Map CherryStudio and RaaS property names onto one hook schema.

    Canonical keys: ``ts``, ``phase``, ``amount_usd``, ``symbol``, ``is_clustered``.
    ``timestamp`` is an alias of ``ts`` for callers that prefer the seed names.
    Records without a usable timestamp are dropped (None).
    """
    ts = _coalesce(record.get("timestamp"), record.get("ts"))
    if ts is None:
        return None
    phase = _coalesce(record.get("funding_phase"), record.get("phase"))
    amount = _coalesce(record.get("amount_usd"), record.get("usd_value"))
    clustered = record.get("is_clustered")
    ts_f = float(ts)
    return {
        "ts": ts_f,
        "timestamp": ts_f,
        "phase": _optional_float(phase),
        "amount_usd": _optional_float(amount),
        "symbol": record.get("symbol"),
        "is_clustered": False if clustered is None else bool(clustered),
    }


@dataclass(frozen=True)
class Neo4jReaderConfig:
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    limit: int = DEFAULT_LIMIT
    allow_extended_lookback: bool = False

    def __post_init__(self) -> None:
        if self.lookback_days < 1:
            raise ValueError("lookback_days must be >= 1")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.lookback_days > MAX_LOOKBACK_DAYS and not self.allow_extended_lookback:
            raise ValueError(
                f"lookback_days={self.lookback_days} exceeds {MAX_LOOKBACK_DAYS}; "
                "set allow_extended_lookback=True to opt in"
            )


def compute_since_ts(
    *,
    now: Optional[float] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    allow_extended_lookback: bool = False,
) -> float:
    """Unix timestamp for ``now - lookback_days`` (D2)."""
    Neo4jReaderConfig(
        lookback_days=lookback_days,
        allow_extended_lookback=allow_extended_lookback,
    )
    anchor = time.time() if now is None else float(now)
    return anchor - lookback_days * 86400.0


def _read_access_mode() -> Any:
    """Server-enforced read session (Neo4j READ_ACCESS); string fallback without driver."""
    try:
        from neo4j import READ_ACCESS  # type: ignore[attr-defined]
        return READ_ACCESS
    except ImportError:
        return "READ"


def resolve_neo4j_read_auth(
    *,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """Prefer dedicated read credentials; admin fallback is warned, not silent.

    Structural guarantee is a Neo4j user with ROLE ``reader`` (see deploy docs).
    Client deny-list is early detection only.

    ``strict=True`` (CI / P4 gate) requires ``NEO4J_USER_READ`` — least-privilege
    login, not only a READ session on an admin account.
    """
    dedicated_user = os.environ.get("NEO4J_USER_READ")
    resolved_uri = (
        uri
        if uri is not None
        else (os.environ.get("NEO4J_URI_READ") or os.environ.get("NEO4J_URI"))
    )
    resolved_user = (
        user
        if user is not None
        else (dedicated_user or os.environ.get("NEO4J_USER", "neo4j"))
    )
    resolved_password = (
        password
        if password is not None
        else (
            os.environ.get("NEO4J_PASS_READ")
            or os.environ.get("NEO4J_PASS")
            or os.environ.get("NEO4J_PASSWORD")
            or ""
        )
    )
    warnings: List[str] = []
    if not dedicated_user:
        warnings.append(
            "NEO4J_USER_READ unset — driver session is READ_ACCESS, "
            "but the login may still hold write privileges. "
            "Create a ROLE reader user before P4 live ingest."
        )
        if strict:
            raise RuntimeError(
                "strict=True erfordert NEO4J_USER_READ (least-privilege Login)"
            )
    return {
        "uri": resolved_uri,
        "user": resolved_user,
        "password": resolved_password,
        "dedicated_reader": bool(dedicated_user),
        "warnings": warnings,
    }


def _read_session(driver: Any) -> Any:
    return driver.session(default_access_mode=_read_access_mode())


def fetch_liquidation_events(
    driver: Any,
    since_ts: float,
    limit: int = DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Return liquidation rows from Neo4j (read-only)."""
    if since_ts is None:
        raise ValueError("since_ts required (D2: no unbounded scan)")
    assert_read_only_cypher(LIQUIDATION_QUERY)

    def _read_tx(tx: Any) -> List[Dict[str, Any]]:
        result = tx.run(LIQUIDATION_QUERY, since_ts=since_ts, limit=limit)
        out: List[Dict[str, Any]] = []
        for row in result:
            normalized = normalize_liquidation_record(dict(row))
            if normalized is not None:
                out.append(normalized)
        return out

    with _read_session(driver) as session:
        return session.execute_read(_read_tx)


def fetch_liquidation_timestamps(
    driver: Any,
    since_ts: float,
    limit: int = DEFAULT_LIMIT,
) -> List[float]:
    rows = fetch_liquidation_events(driver, since_ts=since_ts, limit=limit)
    return [float(row["ts"]) for row in rows]


def preflight_liquidation_aggregate(
    driver: Any,
    since_ts: float,
) -> Dict[str, Any]:
    """Bounded preflight count/min/max for hook ingest (D2)."""
    if since_ts is None:
        raise ValueError("since_ts required (D2: no unbounded scan)")
    assert_read_only_cypher(LIQUIDATION_AGGREGATE_QUERY)

    def _read_tx(tx: Any) -> Dict[str, Any]:
        row = tx.run(LIQUIDATION_AGGREGATE_QUERY, since_ts=since_ts).single()
        if not row:
            return {"n": 0, "ts_min": None, "ts_max": None}
        return {
            "n": int(row["n"]),
            "ts_min": row["ts_min"],
            "ts_max": row["ts_max"],
        }

    with _read_session(driver) as session:
        return session.execute_read(_read_tx)
