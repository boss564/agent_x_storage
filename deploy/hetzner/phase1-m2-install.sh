#!/usr/bin/env bash
# Phase 1 — M2 shadow protocol on Hetzner (post gate-close only).
#
# Does NOT copy standalone scripts into /opt/agent-x — uses git checkout as source of truth.
# See docs/V13_DEPLOY_RUNBOOK.md · deploy/hetzner/README.md
#
# Usage (on server, as root for logrotate):
#   cd /root/agent_x_storage
#   sudo bash deploy/hetzner/phase1-m2-install.sh [--phase-a|--phase-b]
#
set -euo pipefail

AGENT_X_ROOT="${AGENT_X_ROOT:-/root/agent_x_storage}"
PHASE="${1:---phase-a}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

die() { echo -e "${RED}ERROR:${NC} $*" >&2; exit 1; }
ok() { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }

news_python() {
  local py="${AGENT_X_ROOT}/.venv/bin/python"
  if [[ -x "$py" ]]; then
    echo "$py"
  else
    echo "python3"
  fi
}

# Idempotent: deploy-safe-snapshot / git clean wipe .venv (gitignored); the
# systemd unit hardcodes .venv/bin/python → 203/EXEC if missing (seen 2026-09-10).
ensure_venv() {
  local py="${AGENT_X_ROOT}/.venv/bin/python"
  local req="${AGENT_X_ROOT}/requirements.txt"
  if [[ -x "$py" ]]; then
    ok "venv present: $py"
    return 0
  fi
  [[ -f "$req" ]] || die "requirements.txt missing — cannot recreate .venv ($req)"
  warn "venv missing — creating ${AGENT_X_ROOT}/.venv and pip install -r requirements.txt"
  python3 -m venv "${AGENT_X_ROOT}/.venv"
  "${AGENT_X_ROOT}/.venv/bin/pip" install -U pip
  "${AGENT_X_ROOT}/.venv/bin/pip" install -r "$req"
  [[ -x "$py" ]] || die "venv create failed: $py not executable"
  ok "venv ready: $py"
}

enable_watchdog_m2_liveness() {
  local env_file="${AGENT_X_ROOT}/config/news_watchdog.env"
  mkdir -p "${AGENT_X_ROOT}/config"
  if [[ -f "$env_file" ]] && grep -q '^WATCHDOG_M2_MONITOR=' "$env_file"; then
    sed -i 's/^WATCHDOG_M2_MONITOR=.*/WATCHDOG_M2_MONITOR=1/' "$env_file"
  else
    cat >"$env_file" <<EOF
# Managed by deploy/hetzner/phase1-m2-install.sh — instance 7 (do not hand-edit on Hetzner)
WATCHDOG_M2_MONITOR=1
EOF
  fi
  chmod 600 "$env_file"
  ok "Watchdog: WATCHDOG_M2_MONITOR=1 → ${env_file} (auto-loaded by watchdog_news_ingestion.py)"
}

install_m2_ingest_status_cron() {
  local py
  py="$(news_python)"
  local cron_line="5 6 * * * cd ${AGENT_X_ROOT} && PYTHONPATH=. ${py} scripts/m2_ingest_status.py --data ${AGENT_X_ROOT}/data/news_scores.jsonl >> ${AGENT_X_ROOT}/logs/m2_ingest_status.log 2>&1"
  (
    crontab -l 2>/dev/null | grep -v "m2_ingest_status.py" | grep -v "AGENTX_M2_INGEST_STATUS" || true
    echo "# AGENTX_M2_INGEST_STATUS"
    echo "$cron_line"
  ) | crontab -
  ok "Cron: daily 06:05 UTC m2_ingest_status → logs/m2_ingest_status.log (informative, no alarm)"
}

install_m2_systemd_timer() {
  local unit_dir="/etc/systemd/system"
  if [[ ! -d "$unit_dir" ]]; then
    warn "No systemd — skip m2-live-monitor.timer (run scripts/m2_live_monitor.py --once manually)"
    return 0
  fi
  if [[ ! -f deploy/systemd/m2-live-monitor.service ]]; then
    warn "deploy/systemd/m2-live-monitor.service missing — skip timer"
    return 0
  fi
  for f in service timer; do
    cp "deploy/systemd/m2-live-monitor.${f}" "${unit_dir}/m2-live-monitor.${f}"
    sed -i "s|@AGENT_X_ROOT@|${AGENT_X_ROOT}|g" "${unit_dir}/m2-live-monitor.${f}"
  done
  systemctl daemon-reload
  systemctl enable --now m2-live-monitor.timer
  ok "systemd: m2-live-monitor.timer enabled (hourly)"
  systemctl status m2-live-monitor.timer --no-pager || true
}

[[ -d "$AGENT_X_ROOT" ]] || die "Repo not found: $AGENT_X_ROOT"
cd "$AGENT_X_ROOT"

echo -e "${GREEN}=== Agent-X Phase 1 — M2 Shadow (repo-native) ===${NC}"
echo "Root: $AGENT_X_ROOT"

mkdir -p data logs results
ok "data/ logs/ results/"

ensure_venv

chmod +x scripts/watchdog_news_ingestion.py \
  scripts/backtest_h1_news_m2_shadow.py \
  scripts/m2_backtest.py \
  scripts/m2_live_monitor.py \
  scripts/m2_ingest_status.py 2>/dev/null || true
ok "Scripts executable (in-repo)"

case "$PHASE" in
  --phase-a)
    warn "Installing logrotate Phase A (logs only)"
    cp deploy/hetzner/logrotate.agent-x-logs-only.conf /etc/logrotate.d/agent-x
    sed -i "s|@AGENT_X_ROOT@|${AGENT_X_ROOT}|g" /etc/logrotate.d/agent-x
    ;;
  --phase-b)
    warn "Installing logrotate Phase B (logs + news_scores) — Einbahnstraße"
    warn "Requires iter_jsonl_store readers + watchdog soak (V13 §3.2)"
    cp deploy/hetzner/logrotate.agent-x.conf /etc/logrotate.d/agent-x
    sed -i "s|@AGENT_X_ROOT@|${AGENT_X_ROOT}|g" /etc/logrotate.d/agent-x
    ;;
  *)
    die "Usage: $0 [--phase-a|--phase-b]"
    ;;
esac

chmod 644 /etc/logrotate.d/agent-x
logrotate -d /etc/logrotate.d/agent-x >/dev/null
ok "logrotate dry-run OK (/etc/logrotate.d/agent-x)"

enable_watchdog_m2_liveness
install_m2_systemd_timer
install_m2_ingest_status_cron

PY="$(news_python)"
echo ""
echo "M2 live monitor (first cycle + run_marker):"
PYTHONPATH=. "$PY" scripts/m2_live_monitor.py --once --json data/news_scores.jsonl \
  > results/m2_live_monitor_smoke.json 2>/dev/null \
  || warn "m2_live_monitor: first cycle non-zero (marker still written unless import failed)"

echo ""
echo "Smoke tests (read-only):"
PYTHONPATH=. "$PY" scripts/watchdog_news_ingestion.py data/news_scores.jsonl || true
ok "Watchdog smoke (loads config/news_watchdog.env; M2 liveness enforced when =1)"

echo ""
echo -e "${GREEN}=== Phase 1 install complete ===${NC}"
echo "Watchdog:      PYTHONPATH=. python3 scripts/watchdog_news_ingestion.py data/news_scores.jsonl"
echo "  → loads config/news_watchdog.env (WATCHDOG_M2_MONITOR=1 set by this install)"
echo "Live monitor:  systemd m2-live-monitor.timer + scripts/m2_live_monitor.py --once"
echo "  → writes data/m2_live_monitor.jsonl (kind=run_marker, instance 7)"
echo "Tag-7 lag:     PYTHONPATH=. python3 scripts/backtest_h1_news_m2_skeleton.py --lag-report"
echo "Ingest status: cron 06:05 UTC → logs/m2_ingest_status.log (scripts/m2_ingest_status.py)"
echo "Shadow (≥90d): PYTHONPATH=. python3 scripts/m2_backtest.py --jsonl data/news_scores.jsonl"
echo ""
echo "Do NOT use copytruncate on news_scores.jsonl — use deploy/hetzner/logrotate.agent-x.conf only."
