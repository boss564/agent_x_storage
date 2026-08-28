#!/usr/bin/env bash
# Start long-running paper collect (live depth at fill; no order send).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}"
export PYTHONUNBUFFERED=1

PID_FILE="logs/paper_collect.pid"
LOG="logs/paper_collect.log"
RUN_ID="${1:-collect-$(date -u +%Y%m%dT%H%M%SZ)}"
DURATION_S="${RAAS_COLLECT_DURATION_S:-86400}"
DEPTH_MODE="${RAAS_COLLECT_DEPTH_MODE:-live}"

mkdir -p logs

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "already running pid=$old_pid run_id unknown (see manifest)"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) start run_id=$RUN_ID depth=$DEPTH_MODE duration_s=$DURATION_S ===="
} >>"$LOG"

nohup python3 -u scripts/raas_paper_collect.py \
  --depth-mode "$DEPTH_MODE" \
  --duration-s "$DURATION_S" \
  --run-id "$RUN_ID" \
  >>"$LOG" 2>&1 &

echo $! >"$PID_FILE"
echo "started pid=$(cat "$PID_FILE") run_id=$RUN_ID log=$LOG"
