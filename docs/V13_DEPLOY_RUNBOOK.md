# Release & Deployment Runbook: Agent-X v1.3

```text
Version:         v1.3 (M2 Event-Driven Readiness & Ingestion Latency Audit)
Target Host:     Hetzner Production (65.108.246.89 — isolierte Eich-Instanz)
Gate-Close:      2026-09-02T12:00:01.615076+00:00  (NEWS_SCHEDULER_GATE_CLOSE_TS)
Status:          EXECUTABLE POST-GATE-CLOSE ONLY
Prerequisites:   G1 Gate-Auswertung archiviert · make news-agent-test grün lokal
Parent:          NEWS_24H_SCHEDULER_GATE.md · deploy/hetzner/README.md · H1_M2_EVENT_DRIVEN_SPEC.md
```

> **STRIKTE REGEL:** Keine Befehle aus Abschnitt 2–4 vor Gate-Close auf Hetzner ausführen.  
> Während Fenster W läuft der Scheduler unverändert weiter — kein `git pull`, kein Logrotate auf `news_scores.jsonl`, kein manueller `runner --once` für Epochen-Beweis.

---

## 1. Pre-Deployment (Gate-Close Vorbereitung)

### 1.1 UTC & Gate-Status

```bash
echo "Gate-Close:  2026-09-02T12:00:01.615076+00:00"
echo "Current UTC: $(date -u +'%Y-%m-%dT%H:%M:%S.%6NZ')"
```

**Kriterium:** Current UTC ≥ Gate-Close (Mikrosekunden optional ignorierbar; Grenze = `12:00:01Z`).

### 1.2 G1-Auswertung & Window-W-Snapshot

Vor Code- oder Config-Änderungen: Gate-Protokoll ausführen und Daten einfrieren.

```bash
cd /root/agent_x_storage
mkdir -p ~/gate_close_audit_20260902

# G1 — vollständiges Protokoll: NEWS_24H_SCHEDULER_GATE.md §5 / §8.5
PYTHONPATH=. python3 -c "
from pathlib import Path
from services.news_agent.liveness import (
    NEWS_SCHEDULER_EPOCH_TS,
    NEWS_SCHEDULER_GATE_CLOSE_TS,
    load_run_markers,
    measurement_run_markers,
    parse_marker_ts,
)
path = Path('data/news_scores.jsonl')
close = parse_marker_ts(NEWS_SCHEDULER_GATE_CLOSE_TS)
markers = [
    m for m in measurement_run_markers(load_run_markers(path))
    if (t := parse_marker_ts(str(m.get('ts') or ''))) and t <= close
]
print('epoch', NEWS_SCHEDULER_EPOCH_TS)
print('gate_close', NEWS_SCHEDULER_GATE_CLOSE_TS)
print('n_markers_post_epoch', len(markers))
"

# WORM-Snapshot (unveränderlich archivieren)
cp -a data/news_scores.jsonl ~/gate_close_audit_20260902/
cp -a logs/ ~/gate_close_audit_20260902/logs/ 2>/dev/null || true
wc -l ~/gate_close_audit_20260902/news_scores.jsonl
sha256sum ~/gate_close_audit_20260902/news_scores.jsonl > ~/gate_close_audit_20260902/checksum.sha256
```

**Kriterium:** `n_markers_post_epoch` ≥ `n_min` (G1, siehe Gate-Doc). Ergebniszeile archivieren:  
`NEWS_24H_GATE=PASS|FAIL n=… n_min=…`

---

## 2. Code Deployment (Release v1.3)

Hetzner ist **pull-only** — kein Edit/Merge auf dem Server (Gate §8.5 V3).

### 2.1 Git Sync

```bash
cd /root/agent_x_storage
git status          # muss clean sein (keine lokalen Änderungen)
git fetch origin
git checkout main
git pull origin main
git log -1 --oneline
```

Erwartete Commits u. a.: rotation-safe JSONL readers (`ce20f9ec`), logrotate epoch suffix (`cf002e9b`).

### 2.2 In-Situ Test Suite

Nicht nur `test_rss_parser.py` — vollständige News/v1.3-Suite wie lokal:

```bash
cd /root/agent_x_storage
make news-agent-test
```

**Kriterium:** alle Skripte exit 0 (u. a. `test_rss_parser.py` 13/13, `test_news_agent.py` 16/16, `test_watchdog_news_ingestion.py` 7/7, `test_news_jsonl_loader.py` 12/12).

Einzelcheck RSS/Parser:

```bash
PYTHONPATH=. python3 tests/test_rss_parser.py
PYTHONPATH=. python3 tests/test_h1_m2_lag_report.py
```

---

## 3. Infrastruktur & Log-Konfiguration

### 3.1 Logrotate (Template — **kein** `copytruncate`)

**Wichtig:** `news_scores.jsonl` ist WORM-Zustand, kein Wegwerf-Log. Der stündliche Cron öffnet/schließt die Datei pro Lauf — **rename + create** ist sicher, sobald `iter_jsonl_store`-Reader deployed sind (`load_seen`, `load_run_markers`, `last_run_marker`).

**Nicht verwenden:** Inline-Heredoc mit `copytruncate` oder `dateformat -%Y%m%d` allein — bei `maxsize 200M` entstehen sonst Same-Day-Kollisionen (`-YYYYMMDD.N.gz`).

```bash
cd /root/agent_x_storage
sudo cp deploy/hetzner/logrotate.agent-x.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x
sudo chmod 0644 /etc/logrotate.d/agent-x
sudo logrotate -d /etc/logrotate.d/agent-x    # Dry-Run
```

| Pfad | Policy |
|------|--------|
| `logs/*.log` | 14d, `maxsize 100M`, `0640 root adm` |
| `data/news_scores.jsonl` | 365d, **rename+create**, `maxsize 200M`, `dateformat -%Y%m%d-%s`, post-rotate Watchdog + `gzip -t` |

Details: [`deploy/hetzner/README.md`](../deploy/hetzner/README.md)

---

## 4. Aktivierung & Verifikation

### 4.1 Scheduler (Host-Cron — kein Docker-Restart)

Produktion auf Hetzner: **Linux-Cron `:00`**, nicht `docker compose restart news_agent`.

```bash
# Crontab prüfen (genau eine Zeile # AGENTX_NEWS_AGENT)
make news-agent-cron-status

# Optional: einmaliger Smoke (zählt NICHT für Gate-Epoche)
make news-agent-multi-once
```

Nächster autonomer `:00`-Lauf lädt v1.3-Code automatisch — kein Service-Restart nötig.

### 4.2 Watchdog

```bash
make news-watchdog
# oder JSON für Monitoring:
make news-watchdog-json
```

**Erwartung:** Exit `0`, Status `OK`.  
Exit `1` = WARN (Datenalter), Exit `2` = CRITICAL (Marker/Data stale).  
`detection_lag` / `published_at` sind **Metriken only** — kein Exit-WARN (Tag-7 `--lag-report`).

### 4.3 Live-Schema (v1.3)

Nach dem ersten post-deploy `:00`-Lauf:

```bash
tail -n 10 data/news_scores.jsonl | grep -v run_marker | tail -n 5 | \
  python3 -c "
import json, sys
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    r=json.loads(line)
    print({k:r.get(k) for k in ('schema','timestamp','published_at','detection_lag','detection_lag_sec','source_name','sentiment_score')})
"
```

**Kriterium:**

- `schema`: `news_agent_multi/v1.3`
- `published_at`: ISO-UTC oder `null` — **kein** `now()`-Fallback bei fehlendem Datum
- `detection_lag` / `detection_lag_sec`: Ganzzahl Sekunden oder `null`

### 4.4 Tag-7 Lag-Report (Pflicht vor M2-Live)

7 Tage nach Deploy:

```bash
PYTHONPATH=. python3 scripts/backtest_h1_news_m2_skeleton.py \
  --lag-report --jsonl data/news_scores.jsonl
```

Frozen GO/NO-GO: Median `detection_lag` ≤ 15 min → GO; sonst Polling-Epoche (Spec §11) vor M2-Replay.

---

## 5. Rollback (Contingency)

Kein Tag `v1.2-freeze` im Repo — Rollback per **SHA vor v1.3-Deploy**:

```bash
cd /root/agent_x_storage
# Cron stoppen (nur News-Zeile)
make news-agent-cron-disable

PRE_V13_SHA="<sha-vor-deploy>"   # z.B. aus gate_close_audit git log
git checkout "$PRE_V13_SHA"

cp ~/gate_close_audit_20260902/news_scores.jsonl data/news_scores.jsonl
make news-agent-cron-enable
make news-agent-multi-once   # Smoke only

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ROLLBACK to $PRE_V13_SHA" >> logs/deploy_incidents.log
```

Logrotate data-Block bei Rollback auf v1.2-Reader: `news_scores.jsonl`-Rotation **deaktivieren** oder Reader-Commit erneut deployen.

---

## 6. Post-Deploy Eintrag (STRATEGY_THESIS / Changelog)

Nach erfolgreichem Durchlauf in [`STRATEGY_THESIS.md`](STRATEGY_THESIS.md) §6 und Changelog:

```markdown
- [x] **2026-09-02T12:00:01Z:** Gate-Close erreicht (G1 PASS archiviert).
- [x] **Release v1.3 deployed:** `published_at` + `detection_lag` (schema v1.3).
- [x] **Logrotate:** `/etc/logrotate.d/agent-x` (rename+create, `-%Y%m%d-%s`).
- [x] **JSONL store readers:** `iter_jsonl_store` (Dedup + Marker + Hash-Kette).
- [ ] **Tag-7 `--lag-report`:** GO/NO-GO (§5.1.1 H1_M2_EVENT_DRIVEN_SPEC).
- [ ] **M2 Live-Replay:** erst ≥90d JSONL + ≥200 gated Events.
```

---

## Siehe auch

- [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) — G1–G4, Hetzner §8.5
- [`H1_M2_EVENT_DRIVEN_SPEC.md`](H1_M2_EVENT_DRIVEN_SPEC.md) — Schema v1.3, Lag-Gate
- [`NEWS_AGENT.md`](NEWS_AGENT.md) — Cron-Marker, Watchdog-Schwellen
