#!/bin/bash
# LaunchAgent entry for com.agentx.news-agent.
#
# launchd cannot write to /Volumes/THX_OS_ULTRA* (EPERM / sealed).
# Runtime JSONL lives under ~/Library/Application Support/agentx/.
# Code + venv are read from the repo on THX (readable).
set -euo pipefail

REPO="/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage"
APP_SUPPORT="${HOME}/Library/Application Support/agentx"
JSONL="${APP_SUPPORT}/news_scores.jsonl"
LOG_DIR="${HOME}/Library/Logs/agentx-shadow"
LOG="${LOG_DIR}/news-agent.log"

mkdir -p "$APP_SUPPORT" "$LOG_DIR"

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) news-agent launchd start ==="
  cd "$REPO"
  export PYTHONPATH="$REPO"
  export PYTHONUNBUFFERED=1
  export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
  export NEWS_AGENT_MULTI_JSONL="$JSONL"
  PY="$REPO/.venv/bin/python3.14"
  if [[ ! -x "$PY" ]]; then PY="$REPO/.venv/bin/python"; fi
  echo "jsonl=$JSONL py=$PY"
  "$PY" -m services.news_agent.runner --once
  rc=$?
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) exit=$rc ==="
  exit "$rc"
} >>"$LOG" 2>&1
