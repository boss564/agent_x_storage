#!/usr/bin/env python3
"""
Agent X Calibration Runner — reads signal-event logs, runs compound analysis,
and generates a calibration report with recommendations.

Usage:
    python scripts/calibrate_agent_x.py                     # Read from logs/
    python scripts/calibrate_agent_x.py --generate-samples  # Create sample log data
    python scripts/calibrate_agent_x.py --log-dir ./logs    # Custom log directory
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_x.metrics.compound_analyzer import AgentXCompoundAnalyzer


# ============================================================
# Configuration loader
# ============================================================


def load_config() -> dict[str, Any]:
    """Load calibration config from YAML, with sensible defaults."""
    config_path = PROJECT_ROOT / "config" / "calibration_config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f)
        except ImportError:
            pass  # Fall through to defaults

    return {
        "calibration": {
            "alpha": 0.15,
            "static_caution_threshold": 2.0,
            "volatility_penalty": 0.5,
            "min_samples": 20,
        },
        "logging": {"level": "INFO"},
        "output": {"report_dir": "./reports/", "report_prefix": "calibration_report_"},
        "alert_threshold_percent": 30.0,
    }


# ============================================================
# Log reader
# ============================================================


def read_log_events(log_dir: Path) -> list[dict[str, Any]]:
    """
    Read signal events from JSONL log files.

    Expected format:
      {"block_id": "BLK-001", "signal_value": 2.10, "timestamp": "..."}

    Also supports flat format:
      {"block_id": "BLK-001", "value": 2.10}

    Falls back to extracting numeric values from plain-text logs.
    """
    events: list[dict[str, Any]] = []
    jsonl_files = list(log_dir.glob("*.jsonl")) + list(log_dir.glob("*.log"))

    for log_file in sorted(jsonl_files):
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    value = record.get("signal_value", record.get("value"))
                    if value is not None:
                        # Preserve ALL fields from the record — ground truth labels
                        # like 'expected_state' pass through to the analyzer.
                        ev = dict(record)
                        ev["block_id"] = record.get("block_id", f"BLK-{len(events):04d}")
                        ev["signal_value"] = float(value)
                        events.append(ev)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

    return events


# ============================================================
# Sample data generator
# ============================================================


def generate_sample_logs(log_dir: Path, count: int = 60) -> None:
    """
    Generate synthetic signal-event log files for testing.

    Creates a realistic mix: mostly normal values with a few genuine outliers.
    """
    import random
    random.seed(42)

    log_dir.mkdir(exist_ok=True)
    sample_path = log_dir / "agent_x_sample.jsonl"

    events = []
    for i in range(count):
        # 80% normal, 10% borderline, 10% genuine outlier
        roll = random.random()
        if roll < 0.80:
            value = random.gauss(0.5, 0.8)  # Normal: mean 0.5, std 0.8
        elif roll < 0.90:
            value = random.gauss(2.0, 1.5)  # Borderline: near threshold
        else:
            value = random.gauss(3.5, 1.0)  # Genuine outlier

        events.append({
            "block_id": f"BLK-{i:04d}",
            "signal_value": round(value, 4),
            "ts": datetime(2026, 8, 1, hour=i % 24, minute=i % 60).isoformat(),
        })

    with open(sample_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    print(f"  Generated {len(events)} sample events → {sample_path}")


# ============================================================
# Report generator
# ============================================================


def generate_report(report_data: dict, config: dict, report_dir: Path) -> Path:
    """Write calibration report to JSON file."""
    report_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = config["output"]["report_prefix"]
    path = report_dir / f"{prefix}{ts}.json"
    path.write_text(json.dumps(report_data, indent=2, default=str))
    return path


# ============================================================
# Main
# ============================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Agent X Calibration Runner")
    parser.add_argument("--log-dir", type=str, default=str(PROJECT_ROOT / "logs"),
                        help="Directory containing signal-event log files")
    parser.add_argument("--generate-samples", action="store_true",
                        help="Generate synthetic sample log data for testing")
    parser.add_argument("--count", type=int, default=60,
                        help="Number of sample events to generate")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)

    print("=" * 60)
    print("  Agent X Compound-Risk Calibration Runner")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Generate samples if requested
    if args.generate_samples:
        generate_sample_logs(log_dir, args.count)

    # Load config
    config = load_config()
    cal = config["calibration"]
    print(f"\n  Configuration:")
    print(f"    α={cal['alpha']}, static_threshold={cal['static_caution_threshold']}, "
          f"min_samples={cal['min_samples']}")
    print(f"    Alert threshold: {config['alert_threshold_percent']}% static/adaptive disagreement")

    # Read events
    events = read_log_events(log_dir)
    print(f"\n  Events read: {len(events)}")

    if len(events) < cal["min_samples"]:
        print(f"  ⚠ Insufficient data: need ≥{cal['min_samples']}, got {len(events)}")
        if not args.generate_samples:
            print(f"  Run with --generate-samples to create test data.")
        return

    # Analyze
    analyzer = AgentXCompoundAnalyzer(
        alpha=cal["alpha"],
        static_caution_threshold=cal["static_caution_threshold"],
        volatility_penalty=cal.get("volatility_penalty", 0.5),
        min_samples=cal["min_samples"],
        high_is_healthy=cal.get("high_is_healthy", True),  # CHI: high=healthy, low=alarm
    )

    # Check for ground truth
    has_ground_truth = any("expected_state" in ev for ev in events)
    gt_report = None

    if has_ground_truth:
        gt_report = analyzer.analyze_with_ground_truth(events)
        if "error" in gt_report:
            print(f"\n  Ground truth: {gt_report['error']}")
        else:
            print(f"\n  Ground truth: {gt_report['labeled_events']} labeled events "
                  f"({gt_report['unlabeled_excluded']} unlabeled excluded), "
                  f"direction={gt_report['signal_direction']}")
            print(f"  Labels: {gt_report['positive_labels']} positive "
                  f"(caution/stressed/critical), {gt_report['negative_labels']} negative (healthy)")

    report = analyzer.analyze_sequence(events)

    # Additional metrics
    evaluations = report.get("evaluations", [])
    z_scores = [e["z_score"] for e in evaluations if isinstance(e, dict)]
    if z_scores:
        report["additional_metrics"] = {
            "z_score_mean": round(sum(z_scores) / len(z_scores), 4),
            "z_score_std": round(
                (sum((z - sum(z_scores) / len(z_scores)) ** 2 for z in z_scores) / len(z_scores)) ** 0.5,
                4,
            ) if z_scores else 0.0,
            "z_score_min": round(min(z_scores), 4),
            "z_score_max": round(max(z_scores), 4),
        }

    # Console output
    print(f"\n{'=' * 60}")
    print(f"  Results")
    print(f"{'=' * 60}")
    print(f"  Blocks analyzed:      {report['total_blocks_analyzed']}")
    print(f"  Static/adaptive disagreement: {report['disagreement_count']} "
          f"({report['disagreement_rate_percent']}%)")
    print(f"  Static CAUTION count:          {report['static_caution_count']}")
    if "additional_metrics" in report:
        m = report["additional_metrics"]
        print(f"  Z-score distribution: μ={m['z_score_mean']}, σ={m['z_score_std']}, "
              f"range=[{m['z_score_min']}, {m['z_score_max']}]")
    print(f"  Recommendation:       {report['recommendation']}")

    # Show threshold candidates
    candidates = report.get("threshold_candidates", [])
    if candidates:
        print(f"\n  Threshold analysis (static=CAUTION → removed at higher threshold):")
        print(f"  {'Threshold':>10s}  {'Removed':>8s}  {'Remaining':>10s}  {'Δ%':>6s}")
        first_hit = None
        for c in candidates:
            is_first_hit = (first_hit is None and c.get("removed_pct", 0) >= 50)
            if is_first_hit:
                first_hit = c
            marker = " ← recommended" if is_first_hit else ""
            print(f"  {c['threshold']:>10.1f}  {c['caution_removed']:>8d}  "
                  f"{c['caution_remaining']:>10d}  {c['removed_pct']:>5.1f}%{marker}")
        if first_hit:
            print(f"\n  Recommendation: threshold → {first_hit['threshold']} "
                  f"(lowest threshold removing ≥50%: "
                  f"{first_hit['caution_removed']}/{report['static_caution_count']} CAUTIONs). "
                  f"Higher thresholds would remove more but risk missing genuine outliers.")

    # Ground-truth-based performance
    if gt_report and "error" not in gt_report:
        print(f"\n{'=' * 60}")
        print(f"  Ground-Truth Accuracy (expected_state as label)")
        print(f"{'=' * 60}")
        curr = gt_report["current_threshold_performance"]
        best = gt_report["best_threshold"]
        print(f"  Current threshold {cal['static_caution_threshold']}: "
              f"precision={curr['precision']:.3f}, recall={curr['recall']:.3f}, "
              f"F1={curr['f1']:.3f}, FPR={curr['fpr']:.3f}")
        print(f"  Optimal threshold {best}: "
              f"precision={gt_report['best_precision']:.3f}, "
              f"recall={gt_report['best_recall']:.3f}, "
              f"F1={gt_report['best_f1']:.3f}")
        print(f"  {gt_report['recommendation']}")

        # Show top-5 thresholds by F1
        top5 = sorted(gt_report["all_candidates"], key=lambda c: c["f1"], reverse=True)[:5]
        print(f"\n  Top 5 thresholds by F1:")
        print(f"  {'Thr':>6s}  {'Prec':>6s}  {'Recall':>6s}  {'F1':>6s}  {'FPR':>6s}  {'TP':>5s} {'FP':>5s} {'FN':>5s}")
        for c in top5:
            marker = " ← best" if c["threshold"] == best else ""
            print(f"  {c['threshold']:>6.1f}  {c['precision']:>6.3f}  {c['recall']:>6.3f}  "
                  f"{c['f1']:>6.3f}  {c['fpr']:>6.3f}  {c['tp']:>5d} {c['fp']:>5d} {c['fn']:>5d}{marker}")

    # Save report
    report_dir = PROJECT_ROOT / config["output"]["report_dir"].lstrip("./")
    if gt_report:
        report["ground_truth_analysis"] = gt_report
    report_path = generate_report(report, config, report_dir)
    print(f"\n  Report saved: {report_path}")

    # Alert check
    if report["disagreement_rate_percent"] > config["alert_threshold_percent"]:
        print(f"\n  ⚠ ALERT: Disagreement rate ({report['disagreement_rate_percent']}%) "
              f"exceeds threshold ({config['alert_threshold_percent']}%). "
              f"Review threshold calibration.")
    else:
        print(f"\n  ✓ Disagreement rate within acceptable range.")

    print(f"\n  Done.\n")


if __name__ == "__main__":
    main()
