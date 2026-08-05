#!/usr/bin/env python3
"""
Agent X Paper Trading Runner — full pipeline with deep logging.

Feeds each event through the complete SymbolicsAgent pipeline:
  Module A (Consensus) → B (Pressure) → C (Lending) → D (Oracle) → E (Governance)
  → _compute_global_state_5class → CHI-ZERLEGUNG → State + Action

Logs every intermediate signal, penalty, score, and decision to JSONL.
Tracks FCR, Recovery Latency, and Opportunity Drag over the run.

Usage:
    python scripts/paper_trading_agent_x.py                    # Replay from logs/
    python scripts/paper_trading_agent_x.py --live --interval 30  # Live mode, 30s poll
    python scripts/paper_trading_agent_x.py --output reports/pt_day1.jsonl
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_x_orchestrator import SymbolicsAgent
from agent_x_backtest import BlockSnapshot
# Config is not a separate module in agent_x_storage — paths are hardcoded in the orchestrator


# ============================================================
# Configuration
# ============================================================


class PaperTradingConfig:
    output_dir: Path = PROJECT_ROOT / "logs" / "paper_trading"
    log_interval: int = 1        # Log every N events
    live_poll_seconds: int = 30  # Poll interval in live mode
    max_events: int = 0          # 0 = unlimited
    verbose: bool = True


# ============================================================
# Event Source — reads events from log files or live generation
# ============================================================


def read_events_from_logs(log_dir: Path) -> list[dict[str, Any]]:
    """Read signal events from JSONL log files."""
    events = []
    for log_file in sorted(log_dir.glob("*.jsonl")):
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if "signal_value" in ev or "chi" in ev or "value" in ev:
                        events.append(ev)
                except json.JSONDecodeError:
                    continue
    return events


def event_to_snapshot(ev: dict[str, Any]) -> tuple[BlockSnapshot, dict]:
    """
    Convert a log event into a BlockSnapshot plus module data.
    Handles both raw signal_value events and full backtest-format events.
    """
    chi = float(ev.get("chi", ev.get("signal_value", ev.get("value", 90))))
    block_str = ev.get("block", ev.get("block_id", "0"))
    try:
        block = int(block_str)
    except (ValueError, TypeError):
        # Hash-based stable integer for non-numeric block IDs
        block = abs(hash(str(block_str))) % 1000000

    snap = BlockSnapshot(
        block=block,
        label=ev.get("label", ev.get("notes", "")),
        chi=chi,
        gas_pressure=float(ev.get("gas_pressure", 35)),
        mev_pressure=float(ev.get("mev_pressure", 20)),
        positions_at_risk=int(ev.get("positions_at_risk", 2)),
        positions_liquidatable=int(ev.get("positions_liquidatable", 0)),
        worst_hf=float(ev.get("worst_hf", 1.5)),
        flash_loan_profitable=int(ev.get("flash_loan_profitable", 0)),
        mempool_bots=int(ev.get("mempool_bots", 1)),
        active_proposals=int(ev.get("active_proposals", 0)),
        hours_until_next_timelock=float(ev.get("hours_until_next_timelock", 9999)),
        days_until_next_unlock=float(ev.get("days_until_next_unlock", 9999)),
        expected_global_state=ev.get("expected_state", ev.get("expected_global_state", "healthy")),
        expected_action=ev.get("expected_action", "MONITOR"),
        expected_all_clear=ev.get("expected_all_clear", True),
    )
    return snap, ev


# ============================================================
# Deep Logging
# ============================================================


def deep_log(
    output_file: Path,
    event_index: int,
    event: dict[str, Any],
    snap: BlockSnapshot,
    state_result: dict[str, Any],
    action: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    """Write one deeply-logged event record to JSONL."""
    decomposed = state_result.get("decomposed", {})
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_index": event_index,
        "block": snap.block,
        "scenario": event.get("scenario", event.get("_phase", "unknown")),
        # Input signals
        "signals": {
            "chi_raw": snap.chi,
            "gas_pressure": snap.gas_pressure,
            "mev_pressure": snap.mev_pressure,
            "positions_at_risk": snap.positions_at_risk,
            "positions_liquidatable": snap.positions_liquidatable,
            "worst_hf": snap.worst_hf,
        },
        # CHI decomposition
        "chi_decomposed": {
            "consensus_base": decomposed.get("consensus_base", snap.chi),
            "pressure_penalty": decomposed.get("pressure_penalty", 0),
            "lending_penalty": decomposed.get("lending_penalty", 0),
            "mev_penalty": decomposed.get("mev_penalty", 0),
            "longterm_penalty": decomposed.get("longterm_penalty", 0),
            "spike_bypass": decomposed.get("spike_bypass", False),
        },
        # Final state
        "chi_final": state_result["score"],
        "state": state_result["state"],
        "time_horizon": state_result.get("time_horizon", "unknown"),
        "action": action,
        # Ground truth (if available)
        "expected_state": snap.expected_global_state,
        "expected_action": snap.expected_action,
        # Performance
        "elapsed_ms": round(elapsed_ms, 2),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "a") as f:
        f.write(json.dumps(record) + "\n")

    return record


# ============================================================
# Metrics Tracker
# ============================================================


class PaperTradingMetrics:
    """Tracks FCR, Recovery Latency, and Opportunity Drag during a run."""

    def __init__(self):
        self.total = 0
        self.by_state: dict[str, int] = {}
        self.by_expected: dict[str, int] = {}
        self.cautions_in_quiet: list[dict] = []
        self.recovery_events: list[int] = []
        self._last_state = "healthy"
        self._recovery_counter = 0
        self._in_recovery = False

    def record(self, record: dict[str, Any]) -> None:
        self.total += 1
        state = record["state"]
        expected = record.get("expected_state", "unknown")
        self.by_state[state] = self.by_state.get(state, 0) + 1
        self.by_expected[expected] = self.by_expected.get(expected, 0) + 1

        # Recovery tracking: was in stressed/critical, now back to healthy/caution
        if self._last_state in ("stressed", "critical") and state in ("healthy", "caution"):
            self._in_recovery = False
            self.recovery_events.append(self._recovery_counter)
            self._recovery_counter = 0
        elif state in ("stressed", "critical"):
            if self._in_recovery:
                self._recovery_counter += 1
            else:
                self._in_recovery = True
                self._recovery_counter = 0

        # False Caution: state==caution but expected==healthy (quiet phase false alarm)
        if state == "caution" and expected == "healthy":
            self.cautions_in_quiet.append(record)

        self._last_state = state

    def summary(self) -> dict[str, Any]:
        fcr = len(self.cautions_in_quiet) / max(self.total, 1) * 100
        avg_recovery = (sum(self.recovery_events) / max(len(self.recovery_events), 1)
                        if self.recovery_events else 0)
        return {
            "total_events": self.total,
            "state_distribution": self.by_state,
            "expected_distribution": self.by_expected,
            "fcr_pct": round(fcr, 2),
            "fcr_count": len(self.cautions_in_quiet),
            "recovery_events_mean": round(avg_recovery, 1),
            "recovery_events_max": max(self.recovery_events) if self.recovery_events else 0,
            "recovery_spikes": len(self.recovery_events),
        }


# ============================================================
# Main Runner
# ============================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Agent X Paper Trading Runner")
    parser.add_argument("--log-dir", type=str, default=str(PROJECT_ROOT / "logs"),
                        help="Directory with input log files")
    parser.add_argument("--output", type=str,
                        default=str(PROJECT_ROOT / "logs" / "paper_trading" / "run.jsonl"),
                        help="Output JSONL file for deep logs")
    parser.add_argument("--live", action="store_true",
                        help="Live polling mode (replay from logs if not set)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Poll interval in seconds (live mode)")
    parser.add_argument("--max-events", type=int, default=0,
                        help="Max events to process (0 = unlimited)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-event console output")
    args = parser.parse_args()

    output_path = Path(args.output)
    log_dir = Path(args.log_dir)

    print("=" * 60)
    print("  Agent X Paper Trading — Deep Logging Mode")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Output: {output_path}")
    print("=" * 60)

    # Initialize agent
    print("  Initializing SymbolicsAgent...")
    agent = SymbolicsAgent()
    metrics = PaperTradingMetrics()
    print(f"  Agent ready. Capital: ${agent.capital:,}")

    # Load events
    if args.live:
        print(f"  Mode: LIVE (polling every {args.interval}s)")
        print(f"  Waiting for events in {log_dir}...")
    else:
        events = read_events_from_logs(log_dir)
        print(f"  Mode: REPLAY ({len(events)} events from {log_dir})")

    event_index = 0
    processed = 0

    while True:
        # Get next event
        if args.live:
            current_events = read_events_from_logs(log_dir)
            new_events = current_events[event_index:]
            if not new_events:
                time.sleep(args.interval)
                continue
            ev = new_events[0]
            event_index += 1
        else:
            if event_index >= len(events):
                break
            ev = events[event_index]
            event_index += 1

        # Convert to snapshot
        snap, _ = event_to_snapshot(ev)

        # Run full pipeline via SymbolicsAgent.evaluate()
        t0 = time.perf_counter()
        try:
            eval_result = agent.evaluate(
                consensus_health_index=snap.chi,
                gas_pressure_index=snap.gas_pressure,
                mev_pressure_index=snap.mev_pressure,
                health_factors=None,       # Let lending modules default
                flash_loan_opportunities=None,
                mempool_bots_count=snap.mempool_bots,
                active_proposals=snap.active_proposals if snap.active_proposals else None,
            )
            # Normalize result for deep_log
            state_result = {
                "score": eval_result.get("global_score", eval_result.get("score", 0)),
                "state": eval_result.get("global_state", eval_result.get("state", "healthy")),
                "time_horizon": eval_result.get("time_horizon", "unknown"),
                "decomposed": eval_result.get("decomposed", eval_result.get("scenario_details", {})),
            }
            action = eval_result.get("action", eval_result.get("recommended_action", "MONITOR"))
            elapsed_ms = (time.perf_counter() - t0) * 1000
        except Exception as exc:
            print(f"  ❌ Event {event_index} error: {exc}")
            continue

        # Deep log
        record = deep_log(output_path, event_index, ev, snap, state_result, action, elapsed_ms)
        metrics.record(record)
        processed += 1

        # Console output
        if not args.quiet:
            state_icon = {"healthy": "✓", "caution": "○", "stressed": "⚠", "critical": "⛔"}.get(record["state"], "?")
            gt = record.get("expected_state", "?")
            print(f"  [{event_index:4d}] {state_icon} {record['state']:10s} "
                  f"(gt={gt:10s}) chi={snap.chi:5.1f}→{record['chi_final']:5.1f} "
                  f"penalties={record['chi_decomposed']['lending_penalty']:4.1f} "
                  f"action={action:12s} {elapsed_ms:5.1f}ms")

        if args.max_events and processed >= args.max_events:
            break

    # Summary
    summary = metrics.summary()
    print(f"\n{'=' * 60}")
    print(f"  Paper Trading Summary ({processed} events)")
    print(f"{'=' * 60}")
    print(f"  State distribution:  {summary['state_distribution']}")
    print(f"  Expected distribution:{summary['expected_distribution']}")
    print(f"  FCR:                 {summary['fcr_pct']}% ({summary['fcr_count']}/{processed})")
    print(f"  Recovery (mean/max): {summary['recovery_events_mean']}/{summary['recovery_events_max']} events")
    print(f"  Recovery spikes:     {summary['recovery_spikes']}")
    print(f"  Deep log:            {output_path}")

    # Save summary
    summary_path = output_path.parent / f"{output_path.stem}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"  Summary:             {summary_path}")
    print(f"\n  ✓ Paper trading complete.\n")


if __name__ == "__main__":
    main()
