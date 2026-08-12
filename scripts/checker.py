#!/usr/bin/env python3
"""Live Log Checker — monitors docker compose logs for invariant violations.

Usage:
  python3 scripts/checker.py                      # tail all container logs
  python3 scripts/checker.py --services c01-c09   # specific services
  python3 scripts/checker.py --alert              # exit 1 on first error

Patterns (ordered by severity):
  FATAL:  BHO violation, Z3 UNSAT, nullifier double-spend, pairing failure
  ERROR:  Connection refused, timeout, NATS disconnect
  WARN:   Retry, circuit breaker trip, TPS drop

Exit code: 1 if any FATAL pattern found, 0 otherwise.
"""

import os
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# ─── Pattern Categories ────────────────────────────────────────────────────

PATTERNS = {
    "FATAL": [
        (r"BHO_INVARIANCE_VIOLATED", "BHO violation detected"),
        (r"delta.*[1-9]\d*\.\d+.*€", "Non-zero BHO delta"),
        (r"Z3.*UNSAT", "Z3 proof rejected"),
        (r"NULLIFIER_ALREADY_SPENT", "Double-spend attempt"),
        (r"PAIRING_CHECK_FAILED", "Groth16 pairing failed"),
        (r"DID_REVOKED", "DID auto-revoked after 3 failures"),
    ],
    "ERROR": [
        (r"ConnectionRefusedError|Connection refused", "NATS connection lost"),
        (r"TimeoutError|nats: timeout", "NATS request timeout"),
        (r"ZK forward error", "ZK forwarding pipeline error"),
        (r"INVALID_ZK_RECONCILIATION", "D02 forensic proof rejected"),
        (r"ESCROW_NOT_FROZEN", "D03 rescue without freeze"),
    ],
    "WARN": [
        (r"LOW_FUEL|needs_refuel", "Agent fuel low"),
        (r"CircuitBreaker.*OPEN", "Circuit breaker tripped"),
        (r"Retry #\d+", "Retry in progress"),
        (r"TPS.*drop", "TPS drop detected"),
    ],
}

# ─── Stats ──────────────────────────────────────────────────────────────────

stats: defaultdict = defaultdict(lambda: {"FATAL": 0, "ERROR": 0, "WARN": 0})
first_seen: dict = {}
alert_mode = "--alert" in sys.argv
started_at = datetime.now(timezone.utc)


def classify(line: str) -> tuple:
    for severity, patterns in PATTERNS.items():
        for pattern, label in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return severity, label
    return "", ""


def print_line(service: str, severity: str, label: str, line: str):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    icons = {"FATAL": "🚨", "ERROR": "❌", "WARN": "⚠️"}
    icon = icons.get(severity, "·")
    truncated = line.strip()[:120]
    print(f"  {icon} {now} [{service}] {severity}: {label} — {truncated}")


def main():
    services = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--services" and i + 1 < len(args):
            services = args[i + 1].split(",")
            i += 2
        else:
            i += 1

    print(f"\n🔍 Live Log Checker — {len(PATTERNS['FATAL'])} fatal, "
          f"{len(PATTERNS['ERROR'])} error, {len(PATTERNS['WARN'])} warn patterns")
    if services:
        print(f"   Services: {services}")
    print(f"   Started:  {started_at.strftime('%H:%M:%S')}")
    print(f"   Mode:     {'ALERT (exit 1 on fatal)' if alert_mode else 'MONITOR'}")
    print()

    proc = subprocess.Popen(
        ["docker", "compose", "logs", "-f", "--no-log-prefix"] + (services if services else []),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )

    def shutdown(sig, frame):
        print(f"\n⏹️  Stopped after {(datetime.now(timezone.utc) - started_at).total_seconds():.0f}s")
        proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    service = "unknown"
    line_count = 0

    for raw in proc.stdout:
        line_count += 1
        line = raw.strip()
        if not line:
            continue

        # Docker compose logs prefix: "service_name  | message"
        if "|" in line and len(line.split("|")[0].strip()) < 50:
            parts = line.split("|", 1)
            service = parts[0].strip()
            line = parts[1].strip() if len(parts) > 1 else line

        severity, label = classify(line)
        if severity:
            stats[service][severity] += 1
            key = f"{severity}:{label}"
            if key not in first_seen:
                first_seen[key] = datetime.now(timezone.utc)
            print_line(service, severity, label, line)

            if alert_mode and severity == "FATAL":
                print(f"\n🚨 FATAL alert — exiting\n")
                sys.exit(1)

        if line_count % 10_000 == 0:
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            print(f"  · {line_count} lines processed ({elapsed:.0f}s)",
                  end="\r" if not alert_mode else "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
