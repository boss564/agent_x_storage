"""P1 tests: AstroCore Neo4j reader (mock driver, zero cluster/DB)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.astrocore_hook.neo4j_reader import (
    LIQUIDATION_AGGREGATE_QUERY,
    LIQUIDATION_QUERY,
    assert_read_only_cypher,
    compute_since_ts,
    fetch_liquidation_events,
    fetch_liquidation_timestamps,
    normalize_liquidation_record,
    preflight_liquidation_aggregate,
    resolve_neo4j_read_auth,
)
from agents_b2g.astrocore_hook.verdict import cap_verdict_for_provenance


class _Row:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def keys(self):
        return self._data.keys()


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def single(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, liquidation_rows, aggregate_row):
        self.liquidation_rows = liquidation_rows
        self.aggregate_row = aggregate_row
        self.last_query = None
        self.last_params = None
        self.execute_read_called = False

    def run(self, query, **params):
        self.last_query = query
        self.last_params = params
        if "count(l)" in query:
            return _Result([_Row(self.aggregate_row)])
        return _Result([_Row(r) for r in self.liquidation_rows])

    def execute_read(self, fn, *args, **kwargs):
        self.execute_read_called = True
        return fn(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Driver:
    def __init__(self, liquidation_rows, aggregate_row):
        self.liquidation_rows = liquidation_rows
        self.aggregate_row = aggregate_row
        self.access_mode = None

    def session(self, default_access_mode=None):
        self.access_mode = default_access_mode
        sess = _Session(self.liquidation_rows, self.aggregate_row)
        self.last_session = sess
        return sess


def test_compute_since_ts_default_seven_days():
    since = compute_since_ts(now=1_000_000.0, lookback_days=7)
    assert since == 1_000_000.0 - 7 * 86400


def test_compute_since_ts_rejects_extended_without_opt_in():
    try:
        compute_since_ts(now=1_000_000.0, lookback_days=120)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "120" in str(exc)


def test_fetch_liquidation_timestamps_read_only_bounded():
    rows = [
        {"ts": 100.0, "phase": 0.1, "symbol": "ETH", "amount_usd": 1.0, "is_clustered": False},
        {"ts": 200.0, "phase": 0.2, "symbol": "BTC", "amount_usd": 2.0, "is_clustered": True},
    ]
    driver = _Driver(rows, {"n": 2, "ts_min": 100.0, "ts_max": 200.0})
    ts = fetch_liquidation_timestamps(driver, since_ts=50.0, limit=100)
    assert ts == [100.0, 200.0]
    assert driver.access_mode in ("READ", "r") or "READ" in str(driver.access_mode)
    assert driver.last_session.execute_read_called is True


def test_preflight_aggregate_bounded():
    driver = _Driver([], {"n": 0, "ts_min": None, "ts_max": None})
    agg = preflight_liquidation_aggregate(driver, since_ts=1.0)
    assert agg == {"n": 0, "ts_min": None, "ts_max": None}


def test_fetch_requires_since_ts():
    driver = _Driver([], {"n": 0, "ts_min": None, "ts_max": None})
    try:
        fetch_liquidation_events(driver, since_ts=None)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_cap_verdict_synthetic_blocks_positive():
    assert cap_verdict_for_provenance("CLUSTER_DETECTED", "synthetic") == "SYNTHETIC_ONLY"
    assert cap_verdict_for_provenance("COUPLED", "synthetic") == "SYNTHETIC_ONLY"
    assert cap_verdict_for_provenance("UNIFORM", "synthetic") == "UNIFORM"


def test_cap_verdict_live_unchanged():
    assert cap_verdict_for_provenance("CLUSTER_DETECTED", "neo4j") == "CLUSTER_DETECTED"


def test_assert_read_only_blocks_set_after_newline():
    cypher = "MATCH (n:Liquidation)\nSET n.tampered = true"
    try:
        assert_read_only_cypher(cypher)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "SET" in str(exc)


def test_assert_read_only_blocks_set_at_query_start():
    try:
        assert_read_only_cypher("SET n.x = 1")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "SET" in str(exc)


def test_assert_read_only_allows_offset_and_match_return():
    assert_read_only_cypher("MATCH (n) RETURN n SKIP 1 OFFSET 0")
    assert_read_only_cypher(LIQUIDATION_QUERY)
    assert_read_only_cypher(LIQUIDATION_AGGREGATE_QUERY)


def test_queries_use_dual_schema_coalesce():
    assert "coalesce(l.timestamp, l.ts)" in LIQUIDATION_QUERY
    assert "coalesce(l.timestamp, l.ts)" in LIQUIDATION_AGGREGATE_QUERY
    assert "l.usd_value AS usd_value" in LIQUIDATION_QUERY
    assert "l.funding_phase AS funding_phase" in LIQUIDATION_QUERY


def test_normalize_cherry_listener_schema():
    row = normalize_liquidation_record(
        {
            "timestamp": None,
            "ts": 100.0,
            "funding_phase": None,
            "phase": 0.41,
            "amount_usd": None,
            "usd_value": 1500.5,
            "symbol": "ETHUSDT",
            "is_clustered": None,
        }
    )
    assert row == {
        "ts": 100.0,
        "timestamp": 100.0,
        "phase": 0.41,
        "amount_usd": 1500.5,
        "symbol": "ETHUSDT",
        "is_clustered": False,
    }


def test_normalize_raas_seed_schema():
    row = normalize_liquidation_record(
        {
            "timestamp": 200.0,
            "ts": None,
            "funding_phase": 0.95,
            "phase": None,
            "amount_usd": 42.0,
            "usd_value": None,
            "symbol": "BTCUSDT",
            "is_clustered": True,
        }
    )
    assert row["ts"] == 200.0
    assert row["phase"] == 0.95
    assert row["amount_usd"] == 42.0
    assert row["is_clustered"] is True


def test_normalize_prefers_canonical_names():
    row = normalize_liquidation_record(
        {
            "timestamp": 10.0,
            "ts": 99.0,
            "funding_phase": 0.1,
            "phase": 0.9,
            "amount_usd": 1.0,
            "usd_value": 9.0,
            "symbol": "ETH",
            "is_clustered": False,
        }
    )
    assert row["ts"] == 10.0
    assert row["phase"] == 0.1
    assert row["amount_usd"] == 1.0


def test_normalize_keeps_zero_timestamp():
    row = normalize_liquidation_record({"timestamp": 0.0, "ts": 99.0, "phase": 0.0})
    assert row["ts"] == 0.0
    assert row["phase"] == 0.0


def test_normalize_drops_record_without_timestamp():
    assert normalize_liquidation_record({"phase": 0.1, "symbol": "ETH"}) is None


def test_fetch_liquidation_cherry_schema_rows():
    rows = [
        {
            "timestamp": None,
            "ts": 100.0,
            "funding_phase": None,
            "phase": 0.1,
            "amount_usd": None,
            "usd_value": 1.0,
            "symbol": "ETH",
            "is_clustered": None,
        },
        {
            "timestamp": None,
            "ts": 200.0,
            "funding_phase": None,
            "phase": 0.2,
            "amount_usd": None,
            "usd_value": 2.0,
            "symbol": "BTC",
            "is_clustered": None,
        },
    ]
    driver = _Driver(rows, {"n": 2, "ts_min": 100.0, "ts_max": 200.0})
    events = fetch_liquidation_events(driver, since_ts=50.0, limit=100)
    assert [e["ts"] for e in events] == [100.0, 200.0]
    assert events[0]["phase"] == 0.1
    assert events[0]["amount_usd"] == 1.0
    assert events[0]["is_clustered"] is False
    ts = fetch_liquidation_timestamps(driver, since_ts=50.0, limit=100)
    assert ts == [100.0, 200.0]


def test_resolve_prefers_read_user_env(monkeypatch=None):
    os.environ["NEO4J_USER_READ"] = "astrocore_reader"
    os.environ["NEO4J_URI_READ"] = "bolt://read:7687"
    try:
        auth = resolve_neo4j_read_auth()
        assert auth["user"] == "astrocore_reader"
        assert auth["uri"] == "bolt://read:7687"
        assert auth["dedicated_reader"] is True
        assert auth["warnings"] == []
    finally:
        os.environ.pop("NEO4J_USER_READ", None)
        os.environ.pop("NEO4J_URI_READ", None)


def test_resolve_warns_without_dedicated_reader():
    os.environ.pop("NEO4J_USER_READ", None)
    auth = resolve_neo4j_read_auth()
    assert auth["dedicated_reader"] is False
    assert any("NEO4J_USER_READ" in w for w in auth["warnings"])


def test_strict_requires_dedicated_reader():
    os.environ.pop("NEO4J_USER_READ", None)
    try:
        resolve_neo4j_read_auth(strict=True)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "NEO4J_USER_READ" in str(exc)


def test_strict_ok_with_dedicated_reader():
    os.environ["NEO4J_USER_READ"] = "astrocore_reader"
    try:
        auth = resolve_neo4j_read_auth(strict=True)
        assert auth["dedicated_reader"] is True
    finally:
        os.environ.pop("NEO4J_USER_READ", None)


if __name__ == "__main__":
    test_compute_since_ts_default_seven_days()
    test_compute_since_ts_rejects_extended_without_opt_in()
    test_fetch_liquidation_timestamps_read_only_bounded()
    test_preflight_aggregate_bounded()
    test_fetch_requires_since_ts()
    test_cap_verdict_synthetic_blocks_positive()
    test_cap_verdict_live_unchanged()
    test_assert_read_only_blocks_set_after_newline()
    test_assert_read_only_blocks_set_at_query_start()
    test_assert_read_only_allows_offset_and_match_return()
    test_queries_use_dual_schema_coalesce()
    test_normalize_cherry_listener_schema()
    test_normalize_raas_seed_schema()
    test_normalize_prefers_canonical_names()
    test_normalize_keeps_zero_timestamp()
    test_normalize_drops_record_without_timestamp()
    test_fetch_liquidation_cherry_schema_rows()
    test_resolve_prefers_read_user_env()
    test_resolve_warns_without_dedicated_reader()
    test_strict_requires_dedicated_reader()
    test_strict_ok_with_dedicated_reader()
    print("OK: test_astrocore_neo4j_reader 21/21")
