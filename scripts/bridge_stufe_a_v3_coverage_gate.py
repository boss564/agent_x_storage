"""V3 coverage gate over candidate event streams (pre-CTE hard gate).

Reads JSONL candidate captures and evaluates:
- day coverage threshold per candidate
- minimum total event count (N_events >= 100)
- zero-event handling -> V3_UNTESTBAR
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

WINDOW_START = datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 8, 17, 23, 59, 59, tzinfo=timezone.utc)
WINDOW_DAYS = (WINDOW_END.date() - WINDOW_START.date()).days + 1


@dataclass(frozen=True)
class CandidateRule:
    candidate_id: str
    min_day_coverage: float


RULES: tuple[CandidateRule, ...] = (
    CandidateRule("chainlink", 0.80),
    CandidateRule("intent_relayers", 0.60),
    CandidateRule("liquidations", 0.40),
    CandidateRule("stablecoin_mint_burn", 0.60),
    CandidateRule("mev_cluster", 0.70),
)


def parse_ts(obj: dict) -> int | None:
    v = obj.get("timestamp", obj.get("blockTime"))
    if v is None:
        return None
    return int(float(v))


def day_index(ts: int) -> int | None:
    start = int(WINDOW_START.timestamp())
    end = int(WINDOW_END.timestamp())
    if ts < start or ts > end:
        return None
    return (ts - start) // 86400


def eval_file(path: Path, min_day_coverage: float) -> dict:
    if not path.exists():
        return {
            "status": "V3_UNTESTBAR",
            "reason": "missing_file",
            "n_events": 0,
            "coverage_days": 0,
            "coverage_ratio": 0.0,
            "min_day_coverage": min_day_coverage,
        }

    day_hits = set()
    n_events = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ts = parse_ts(obj)
            if ts is None:
                continue
            idx = day_index(ts)
            if idx is None:
                continue
            n_events += 1
            day_hits.add(idx)

    coverage_days = len(day_hits)
    coverage_ratio = coverage_days / WINDOW_DAYS

    if n_events == 0:
        status = "V3_UNTESTBAR"
        reason = "zero_events"
    elif n_events < 100:
        status = "V3_UNTESTBAR"
        reason = "n_events_below_100"
    elif coverage_ratio < min_day_coverage:
        status = "V3_UNTESTBAR"
        reason = "coverage_below_threshold"
    else:
        status = "TESTBAR"
        reason = "ok"

    return {
        "status": status,
        "reason": reason,
        "n_events": n_events,
        "coverage_days": coverage_days,
        "coverage_ratio": round(coverage_ratio, 6),
        "min_day_coverage": min_day_coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Stufe A V3 coverage gate")
    parser.add_argument("--input-dir", default=".")
    parser.add_argument("--output", default="bridge_stufe_a_v3_coverage_gate.json")
    args = parser.parse_args()

    root = Path(args.input_dir)
    out: dict[str, dict] = {}
    testable = 0
    for rule in RULES:
        path = root / f"bridge_stufe_a_v3_{rule.candidate_id}.jsonl"
        result = eval_file(path, rule.min_day_coverage)
        out[rule.candidate_id] = {
            "file": str(path),
            **result,
        }
        if result["status"] == "TESTBAR":
            testable += 1

    report = {
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "window_days": WINDOW_DAYS,
        "rules": [{"candidate_id": r.candidate_id, "min_day_coverage": r.min_day_coverage} for r in RULES],
        "results": out,
        "testable_candidates": testable,
        "untestable_candidates": len(RULES) - testable,
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    for cid, res in out.items():
        print(f"{cid}: {res['status']} ({res['reason']}) n={res['n_events']} coverage={res['coverage_ratio']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
