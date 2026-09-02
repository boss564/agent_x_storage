# Hetzner — Logrotate & JSONL archives

**Status:** Template only — install **after** gate-close unless ops explicitly approves.

## Logrotate

```bash
sudo cp deploy/hetzner/logrotate.agent-x.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x
sudo logrotate -d /etc/logrotate.d/agent-x          # syntax / dry-run
sudo logrotate -f /etc/logrotate.d/agent-x          # manual rotate (careful)
find /root/agent_x_storage/data -name 'news_scores.jsonl-*.gz' -exec gzip -t {} \; -print
```

| Path | Policy | Install |
|------|--------|---------|
| `logs/*.log` | 14 days, `maxsize 100M`, `0640 root adm` | Anytime |
| `data/news_scores.jsonl` | 365 days, **rename + create** (not `copytruncate`), `maxsize 200M`, `dateformat -%Y%m%d-%s` (unique per rotation when `maxsize` fires intraday), post-rotate watchdog + `gzip -t` | **After** loader deploy + preferably gate-close |

`news_scores.jsonl` is WORM state, not a throwaway log. The hourly cron opens the file per run and closes it — regular rotation is safe once readers use `iter_jsonl_store` (`load_seen`, `load_run_markers`, `last_run_marker`). Archive sort: `dateext` suffixes lex ascending (`-%Y%m%d-%s` in template); numeric `.N` fallback if convention changes.

`maxsize 200M` can rotate outside the daily window — avoid enabling the data block during the 24h scheduler gate unless ops accepts mid-window archive moves.

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
