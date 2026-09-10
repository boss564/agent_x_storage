"""P3 tests: RaaS audit JSONL ingest (read-only, no cluster)."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_b2g.astrocore_hook.raas_ingest import (
    extract_timestamps_from_record,
    parse_gap_logs,
)
from agents_b2g.astrocore_hook import AstrocoreHookClient
from agents_b2g.astrocore_hook.verdict import cap_verdict_for_provenance


def _iso(days_ago: float = 0.0) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return ts.isoformat().replace("+00:00", "Z")


def test_extract_timestamps_from_record():
    record = {
        "ts": _iso(0.1),
        "gap_start_ts": _iso(0.2),
        "gap_end_ts": None,
        "entry_tick_ts": _iso(0.3),
    }
    values = extract_timestamps_from_record(record)
    assert len(values) == 3
    assert all(isinstance(v, float) for v in values)


def test_parse_gap_logs_worm_provenance():
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp)
        line = {
            "source": "tick_spacing",
            "symbol": "ETHUSDT",
            "ts": _iso(0.1),
            "gap_start_ts": _iso(0.2),
            "gap_end_ts": _iso(0.15),
        }
        (audit / "feed_gaps.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")

        timestamps, meta = parse_gap_logs(audit, lookback_days=7)
        assert meta["provenance"] == "worm"
        assert meta["source_files"] == ["feed_gaps.jsonl"]
        assert len(timestamps) >= 2
        assert timestamps.dtype == np.float64


def test_parse_gap_logs_empty_falls_back_to_gap_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp)
        old = {"source": "socket", "ts": _iso(30)}
        (audit / "feed_gaps.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")

        timestamps, meta = parse_gap_logs(audit, lookback_days=7)
        assert meta["provenance"] == "gap_synthetic"
        assert len(timestamps) == 1000
        assert meta["warnings"]


def test_cap_verdict_worm_blocks_positive():
    assert cap_verdict_for_provenance("CLUSTER_DETECTED", "worm") == "SYNTHETIC_ONLY"
    assert cap_verdict_for_provenance("CLUSTER_DETECTED", "gap_synthetic") == "SYNTHETIC_ONLY"


def test_hook_client_worm_source():
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp)
        (audit / "feed_gaps.jsonl").write_text(
            json.dumps({"source": "heartbeat", "ts": _iso(0.05)}) + "\n",
            encoding="utf-8",
        )
        client = AstrocoreHookClient(
            data_source="worm",
            audit_dir=str(audit),
            strict=False,
        )
        env = client.analyze_liquidations()
        assert env["data_provenance"] == "worm"
        assert env["verdict"] != "CLUSTER_DETECTED"
        assert env["stats"]["source_files"] == ["feed_gaps.jsonl"]


if __name__ == "__main__":
    test_extract_timestamps_from_record()
    test_parse_gap_logs_worm_provenance()
    test_parse_gap_logs_empty_falls_back_to_gap_synthetic()
    test_cap_verdict_worm_blocks_positive()
    test_hook_client_worm_source()
    print("OK: test_astrocore_raas_ingest 5/5")
