#!/usr/bin/env python3
"""
Export backtest snapshot data as JSONL signal-event logs for calibration.

Reads the prefabricated scenarios from agent_x_backtest.py and exports
each BlockSnapshot as a signal event with expected_global_state as ground truth.

Usage:
    python scripts/export_backtest_signals.py          # Export to logs/
    python scripts/calibrate_agent_x.py                # Then calibrate against it
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_x_backtest import ALL_SCENARIOS as SCENARIOS, BlockSnapshot


def export_as_jsonl(scenarios: list[dict], output_path: Path) -> int:
    """
    Convert backtest scenarios to JSONL signal events.

    Each BlockSnapshot is serialized via dataclasses.asdict() so every
    field flows through automatically — no hand-maintained field list.
    """
    count = 0
    with open(output_path, "w") as f:
        for scenario in scenarios:
            name = scenario["name"]
            for snap in scenario["blocks"]:
                if not isinstance(snap, BlockSnapshot):
                    continue
                record: dict = asdict(snap)
                record["block_id"] = f"{name[:30]}-block{snap.block}"
                record["scenario"] = name
                record["notes"] = snap.notes
                f.write(json.dumps(record) + "\n")
                count += 1
    return count


def main():
    output_path = PROJECT_ROOT / "logs" / "backtest_signals.jsonl"
    count = export_as_jsonl(SCENARIOS, output_path)
    print(f"Exported {count} signal events (with ground truth) → {output_path}")

    # Show distribution
    states = {}
    for scenario in SCENARIOS:
        for snap in scenario["blocks"]:
            if isinstance(snap, BlockSnapshot):
                s = snap.expected_global_state
                states[s] = states.get(s, 0) + 1
    print(f"Ground truth distribution: {states}")


if __name__ == "__main__":
    main()
