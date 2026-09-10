# Hetzner — Logrotate & JSONL archives

**Status:** Template only — install **after** gate-close unless ops explicitly approves.

## Phased install (recommended)

| Phase | When | File | What |
|-------|------|------|------|
| **A** | Post gate-close + v1.3 deploy | `logrotate.agent-x-logs-only.conf` | `logs/*.log` only — safe immediately |
| **B** | Watchdog Exit 0 durchgehend + Tag-7 `--lag-report` (Coverage plausibel) | `logrotate.agent-x.conf` (full) | **Einbahnstraße** — Rollback nur noch Pfad B |

**Why phased:** Before the first `news_scores.jsonl` rotation, rollback = `git checkout` + audit restore. After rotation, a legacy reader (v1.2) sees an empty active file and replays the full RSS corpus — worse than no rollback unless archives are merged back. See [`docs/V13_DEPLOY_RUNBOOK.md`](../../docs/V13_DEPLOY_RUNBOOK.md) §5.

## Logrotate

```bash
# Phase A (logs only)
sudo cp deploy/hetzner/logrotate.agent-x-logs-only.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x
sudo logrotate -d /etc/logrotate.d/agent-x

# Phase B (full — after soak)
sudo cp deploy/hetzner/logrotate.agent-x.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x
sudo logrotate -d /etc/logrotate.d/agent-x
find /root/agent_x_storage/data -name 'news_scores.jsonl-*.gz' -exec gzip -t {} \; -print
```

| Path | Policy | Install |
|------|--------|---------|
| `logs/*.log` | 14d, `maxsize 100M`, `0640 root adm` | Phase A (anytime post gate-close) |
| `data/news_scores.jsonl` | 365d, rename+create, `maxsize 200M`, `dateformat -%Y%m%d-%s`, post-rotate watchdog + `gzip -t` | Phase B (after soak) |

`news_scores.jsonl` is WORM state. Readers use `iter_jsonl_store` (`load_seen`, `load_run_markers`, `last_run_marker`). Archive sort: `dateext` lex ascending (`-%Y%m%d-%s`); numeric `.N` fallback.

## Python loader

Streaming reader: `src/ingestion/news_jsonl_loader.py`

```python
from src.ingestion.news_jsonl_loader import iter_jsonl_store, iter_news_records_tail

for row in iter_jsonl_store("data/news_scores.jsonl", max_files=7):
    ...

for row in iter_news_records_tail("data/news_scores.jsonl", sample_size=50):
    ...  # watchdog content sample (markers: last_run_marker)
```

## Disk alert (optional)

```bash
df -h /root/agent_x_storage | awk 'NR==2 {gsub(/%/,"",$5); if ($5+0 >= 80) exit 1}'
```

Wire into existing alerting (RaaS / cron mail) — not part of the news gate.

## Phase 1 — M2 shadow protocol (post gate-close)

**Do not** deploy the generic `deploy.sh` / `copytruncate` / A-B-C-second-bucket drafts — use repo-native paths below.

| Component | Canonical path |
|-----------|----------------|
| Install (Phase A/B logrotate) | `deploy/hetzner/phase1-m2-install.sh` |
| Watchdog | `scripts/watchdog_news_ingestion.py` |
| Live monitor (hourly metrics) | `scripts/m2_live_monitor.py --once` |
| Tag-7 lag GO/NO-GO | `scripts/backtest_h1_news_m2_skeleton.py --lag-report` |
| M2 ingest progress (daily cron) | `scripts/m2_ingest_status.py` → `logs/m2_ingest_status.log` |
| Shadow backtest (≥90d) | `scripts/m2_backtest.py` → `backtest_h1_news_m2_shadow.py` |
| Logrotate | `deploy/hetzner/logrotate.agent-x*.conf` (rename+create, **no** copytruncate) |
| Runbook | `docs/V13_DEPLOY_RUNBOOK.md` |

```bash
cd /root/agent_x_storage
sudo bash deploy/hetzner/phase1-m2-install.sh --phase-a   # post gate-close
# after watchdog soak + Tag-7 lag-report:
sudo bash deploy/hetzner/phase1-m2-install.sh --phase-b

PYTHONPATH=. python3 scripts/m2_live_monitor.py --once
PYTHONPATH=. python3 scripts/m2_backtest.py --jsonl data/news_scores.jsonl  # when thresholds met
```

Optional systemd: `deploy/systemd/m2-live-monitor.{service,timer}` — installed and enabled by `phase1-m2-install.sh`.

**Liveness (instance 7):** each monitor cycle appends `kind=run_marker` to `data/m2_live_monitor.jsonl`. `phase1-m2-install.sh` sets `WATCHDOG_M2_MONITOR=1` in `config/news_watchdog.env` (auto-loaded by the watchdog) **together with** enabling the systemd timer — no separate ops step. `=1` catches a monitor that **never started** (MISSING audit file); `auto` only arms after the file exists. `lag_bucket_counts` on news JSONL is **not** a substitute.
