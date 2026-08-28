#!/usr/bin/env bash
# Passive depth ingest — Binance public REST only (Phase B).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}"

mkdir -p logs
LOG="logs/cron_depth_ingest.log"
{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) raas_depth_ingest ===="
  python3 scripts/raas_depth_ingest.py
  echo "ok"
} >>"$LOG" 2>&1
