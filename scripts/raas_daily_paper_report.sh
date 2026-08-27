#!/usr/bin/env bash
# Daily paper-trading markdown report (cron / systemd entrypoint).
# Charter: live_execution=false · no order send · no sample fills.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}"

mkdir -p logs
LOG="logs/cron_exporter.log"
{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) raas_daily_paper_report ===="
  python3 services/exporter/agent_x_raas_exporter.py \
    --mode paper_trading \
    --format markdown
  echo "ok"
} >>"$LOG" 2>&1
