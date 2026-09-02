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
