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
        block = abs(hash(str(block_str))) % 1000000

    # Derive mempool_bots from mev_pressure if not explicitly specified.
    # Without bot data, assume 0 bots — no baseline MEV penalty.
    mev_p = float(ev.get("mev_pressure", 0))
    bots_raw = ev.get("mempool_bots")
    if bots_raw is not None:
        bots = int(bots_raw)
    else:
        bots = 6 if mev_p > 80 else 3 if mev_p > 60 else 1 if mev_p > 30 else 0

    snap = BlockSnapshot(
        block=block,
        label=ev.get("label", ev.get("notes", "")),
        chi=chi,
        # Klasse A — Konsensus
        participation_rate=float(ev.get("participation_rate", 0.97)),
        finality_status=ev.get("finality_status", "on_time"),
        reorg_depth=int(ev.get("reorg_depth", 0)),
        exit_queue=int(ev.get("exit_queue", 50)),
        trusted_validators=ev.get("trusted_validators", ["validator_101"]),
        # Klasse B — Druckventile
        gas_pressure=float(ev.get("gas_pressure", 35)),
        mev_pressure=float(ev.get("mev_pressure", 20)),
        block_pressure=float(ev.get("block_pressure", 50)),
        basefee_gwei=float(ev.get("basefee_gwei", 21)),
        pf_p95_gwei=float(ev.get("pf_p95_gwei", 3.5)),
        mev_spike=ev.get("mev_spike", False),
        # Klasse C — Lending
        positions_at_risk=int(ev.get("positions_at_risk", 2)),
        positions_liquidatable=int(ev.get("positions_liquidatable", 0)),
        worst_hf=float(ev.get("worst_hf", 1.5)),
        # Klasse D — DeFi
        flash_loan_profitable=int(ev.get("flash_loan_profitable", 0)),
        mempool_bots=bots,
        cross_pool_ops=int(ev.get("cross_pool_ops", 0)),
        potential_profit_usd=float(ev.get("potential_profit_usd", 500)),
        # Klasse E — Langzeit
        hours_until_next_timelock=float(ev.get("hours_until_next_timelock", 9999)),
        days_until_next_unlock=float(ev.get("days_until_next_unlock", 9999)),
        active_proposals=ev.get("active_proposals", []) or [],
        pending_timelocks=ev.get("pending_timelocks", []) or [],
        upcoming_unlocks=ev.get("upcoming_unlocks", []) or [],
        # Ground truth
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
# Position Builders (mirror agent_x_backtest._evaluate_snapshot)
# ============================================================


def _build_positions(snap: BlockSnapshot) -> list[dict[str, Any]]:
    """Build position list from snapshot lending fields."""
    total = max(snap.positions_liquidatable, snap.positions_at_risk)
    positions = []
    for i in range(total):
        if i < snap.positions_liquidatable:
            hf = snap.worst_hf
        elif i < snap.positions_at_risk:
            hf = min(snap.worst_hf + 0.15, 1.50) if snap.worst_hf != float("inf") else 1.15
        else:
            hf = 1.5
        positions.append({
            "user_address": f"0xVictim{i}",
            "health_factor": round(hf, 3),
            "total_debt_usd": 10000 + i * 5000,
        })
    return positions


def _build_flash_loans(count: int, profit_usd: float) -> list[dict[str, Any]] | None:
    """Build flash loan opportunity list."""
    if count <= 0:
        return None
    return [{
        "tx_hash": f"0xfl{i}",
        "protocol": "AaveV3",
        "net_profit_usd": profit_usd / max(1, count),
        "profitable": True,
    } for i in range(count)]


def _build_cross_pool(count: int, profit_usd: float) -> list[dict[str, Any]] | None:
    """Build cross-pool opportunity list."""
    if count <= 0:
        return None
    return [{
        "id": f"cp{i}",
        "net_profit_usd": profit_usd / max(1, count or 1),
        "executable": True,
    } for i in range(count)]


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

        # Reset hysteresis when scenario changes (prevents cross-contamination).
        current_scenario = ev.get("scenario", ev.get("_phase", ""))
        if "last_scenario" not in dir(main):
            main.last_scenario = None  # type: ignore[attr-defined]
        if current_scenario and current_scenario != main.last_scenario:  # type: ignore[attr-defined]
            if hasattr(agent, "_prev_global_score"):
                del agent._prev_global_score
        main.last_scenario = current_scenario  # type: ignore[attr-defined]

        # Run full pipeline via SymbolicsAgent.evaluate()
        t0 = time.perf_counter()
        try:
            eval_result = agent.evaluate(
                # Klasse A — Konsensus
                consensus_health_index=snap.chi,
                exit_queue_length=snap.exit_queue,
                participation_rate=snap.participation_rate,
                finality_status=snap.finality_status,
                reorg_depth=snap.reorg_depth,
                trusted_validators=snap.trusted_validators if snap.trusted_validators else None,
                # Klasse B — Druckventile
                gas_pressure_index=snap.gas_pressure,
                mev_pressure_index=snap.mev_pressure,
                block_pressure_index=snap.block_pressure,
                basefee_current_gwei=snap.basefee_gwei,
                priority_fee_p95_gwei=snap.pf_p95_gwei,
                mev_spike_detected=snap.mev_spike,
                # Klasse C — Lending
                health_factors=(
                    _build_positions(snap) if snap.positions_at_risk or snap.positions_liquidatable
                    else None
                ),
                # Klasse D — DeFi
                flash_loan_opportunities=(
                    _build_flash_loans(snap.flash_loan_profitable, snap.potential_profit_usd)
                ),
                mempool_bots_count=snap.mempool_bots,
                cross_pool_opportunities=(
                    _build_cross_pool(snap.cross_pool_ops, snap.potential_profit_usd)
                ),
                # Klasse E — Langzeit
                pending_timelocks=snap.pending_timelocks if snap.pending_timelocks else None,
                upcoming_unlocks=snap.upcoming_unlocks if snap.upcoming_unlocks else None,
                active_proposals=snap.active_proposals if snap.active_proposals else None,
            )
            # Normalize result for deep_log — read from unified_decision, not top-level
            ud = eval_result.get("unified_decision", {})
            state_result = {
                "score": ud.get("global_state_score", 0),
                "state": ud.get("global_state", "healthy"),
                "time_horizon": ud.get("time_horizon", "unknown"),
                "decomposed": eval_result.get("class_signals", {}),
            }
            action_raw = ud.get("recommended_actions", [])
            if action_raw and isinstance(action_raw[0], dict):
                action = action_raw[0].get("action", "MONITOR")
            else:
                action = action_raw[0] if action_raw else "MONITOR"
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
