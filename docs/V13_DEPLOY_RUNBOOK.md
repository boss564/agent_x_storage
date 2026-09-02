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
git rev-parse HEAD > ~/gate_close_audit_20260902/pre_v13_deploy_sha
git log -1 --oneline > ~/gate_close_audit_20260902/pre_v13_deploy_log
cp -a data/news_scores.jsonl ~/gate_close_audit_20260902/
cp -a logs/ ~/gate_close_audit_20260902/logs/ 2>/dev/null || true
wc -l ~/gate_close_audit_20260902/news_scores.jsonl
sha256sum ~/gate_close_audit_20260902/news_scores.jsonl > ~/gate_close_audit_20260902/checksum.sha256
cat ~/gate_close_audit_20260902/pre_v13_deploy_sha
```

**Kriterium:** `n_markers_post_epoch` ≥ `n_min` (G1, siehe Gate-Doc). Ergebniszeile archivieren:  
`NEWS_24H_GATE=PASS|FAIL n=… n_min=…`

`pre_v13_deploy_sha` ist das **kanonische Rollback-Ziel** — kein Tag `v1.2-freeze` im Repo; niemand muss eine SHA notieren.

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

### 3.1 Logrotate — Phase A (sofort nach v1.3-Deploy)

**App-Logs** können sofort rotieren — kein Leser rekonstruiert Zustand aus `logs/*.log`.

```bash
cd /root/agent_x_storage
sudo cp deploy/hetzner/logrotate.agent-x-logs-only.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x
sudo chmod 0644 /etc/logrotate.d/agent-x
sudo logrotate -d /etc/logrotate.d/agent-x    # Dry-Run
```

| Pfad | Policy |
|------|--------|
| `logs/*.log` | 14d, `maxsize 100M`, `0640 root adm` |

### 3.2 Logrotate — Phase B (`news_scores.jsonl`, **Einbahnstraße**)

**Phase B ist irreversibel für den Rollback:** Ab der ersten `news_scores`-Rotation ist Rollback nicht mehr `git checkout` (Pfad A), sondern nur noch Pfad B mit Merge (§5).

**Nicht** direkt nach Gate-Close scharfschalten. Öffnungskriterien sind **Beobachtungen**, kein Kalenderdatum:

| Gate | Kriterium |
|------|-----------|
| **Watchdog-Soak** | `make news-watchdog` durchgehend **Exit 0** über die gesamte Soak-Periode (kein WARN `1`, kein CRITICAL `2`). Zweimal WARN an Tag 4 → Phase B verschiebt sich, bis wieder grün — ohne Ops-Entscheid. |
| **Tag-7 Lag-Report** | `--lag-report` (§4.4): `lag_coverage` und `coverage_by_source` **plausibel** (Spec §5.1.3). Median-GO/NO-GO (§5.1.1) steuert die Polling-Epoche, nicht Phase B — aber Coverage muss vor Rotation Sinn ergeben. |

Beide Gates grün → Phase B installieren. Fehlt eines → bei Phase A bleiben (Rollback-Fenster offen).

Optional: täglichen Soak-Beleg loggen (`logs/watchdog_soak.log`):

```bash
# Crontab-Ergänzung nur während Soak (nach Deploy, vor Phase B)
0 12 * * * cd /root/agent_x_storage && PYTHONPATH=. python3 scripts/watchdog_news_ingestion.py >> logs/watchdog_soak.log 2>&1; echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) exit=$?" >> logs/watchdog_soak.log
```

`news_scores.jsonl` ist WORM-Zustand. **rename + create** mit `iter_jsonl_store`-Readern. **Kein** `copytruncate`, **kein** `dateformat -%Y%m%d` allein.

```bash
cd /root/agent_x_storage
sudo cp deploy/hetzner/logrotate.agent-x.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x
sudo logrotate -d /etc/logrotate.d/agent-x
```

| Pfad | Policy |
|------|--------|
| `data/news_scores.jsonl` | 365d, rename+create, `maxsize 200M`, `dateformat -%Y%m%d-%s`, post-rotate Watchdog + `gzip -t` |

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

### 4.4 Tag-7 Lag-Report (Soak-Gate + M2-Vorstufe)

7 Tage nach Deploy — **Pflicht vor Phase-B-Logrotate** und Vorstufe für M2:

```bash
PYTHONPATH=. python3 scripts/backtest_h1_news_m2_skeleton.py \
  --lag-report --jsonl data/news_scores.jsonl
```

Frozen GO/NO-GO (Polling-Epoche): Median `detection_lag` ≤ 15 min → GO (§5.1.1).  
**Phase B:** zusätzlich `lag_coverage` / `coverage_by_source` plausibel (§5.1.3) — unabhängig vom Median-Verdict.

---

## 5. Rollback (Contingency)

**Kein Tag `v1.2-freeze`.** Rollback-SHA steht in `~/gate_close_audit_20260902/pre_v13_deploy_sha` (§1.2).

### 5.1 Rollback-Fenster (Asymmetrie)

```text
Vor der ersten news_scores-Rotation (Phase B aus):
  → git checkout $(cat ~/gate_close_audit_20260902/pre_v13_deploy_sha)
  → optional: audit-JSONL zurückspielen
  → folgenlos für Dedup/Marker (eine Datei, v1.2-Reader)

Nach der ersten news_scores-Rotation:
  → v1.2 liest nur den aktiven Pfad (leer nach rename+create)
  → load_seen findet nichts → jeder Artikel „neu“ → Alert-Lawine + Voll-Reanalyse
  → git checkout allein ist SCHLECHTER als kein Rollback
```

Sauberer Rollback nach Rotation erfordert **gleichzeitig**:

1. Data-Block in `/etc/logrotate.d/agent-x` entfernen (oder logs-only-Template zurück)
2. Archive in die aktive Datei zusammenführen (noch auf v1.3, `iter_jsonl_store`-Reihenfolge)
3. Dann `git checkout` auf `pre_v13_deploy_sha` + JSONL aus Audit falls nötig

### 5.2 Pfad A — vor erster Data-Rotation (bevorzugt)

```bash
cd /root/agent_x_storage
make news-agent-cron-disable

PRE_V13_SHA="$(cat ~/gate_close_audit_20260902/pre_v13_deploy_sha)"
git checkout "$PRE_V13_SHA"

cp ~/gate_close_audit_20260902/news_scores.jsonl data/news_scores.jsonl
sha256sum -c ~/gate_close_audit_20260902/checksum.sha256

make news-agent-cron-enable
make news-agent-multi-once   # Smoke only

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ROLLBACK to $PRE_V13_SHA (pre-rotation)" >> logs/deploy_incidents.log
```

### 5.3 Pfad B — nach Data-Rotation (Notfall)

```bash
cd /root/agent_x_storage
make news-agent-cron-disable

# 1) Rotation stoppen (logs-only Template)
sudo cp deploy/hetzner/logrotate.agent-x-logs-only.conf /etc/logrotate.d/agent-x
sudo sed -i 's|@AGENT_X_ROOT@|/root/agent_x_storage|g' /etc/logrotate.d/agent-x

# 2) Archive → aktive Datei (noch v1.3 — store sort oldest→newest)
PYTHONPATH=. python3 <<'PY'
import json
from pathlib import Path
from src.ingestion.news_jsonl_loader import iter_jsonl_store

active = Path("data/news_scores.jsonl")
merged = active.with_suffix(".merged")
with merged.open("w", encoding="utf-8") as out:
    for row in iter_jsonl_store(active):
        out.write(json.dumps(row, default=str) + "\n")
merged.replace(active)
PY
find data -maxdepth 1 -name 'news_scores.jsonl-*' -delete

# 3) Code-Rollback
PRE_V13_SHA="$(cat ~/gate_close_audit_20260902/pre_v13_deploy_sha)"
git checkout "$PRE_V13_SHA"

make news-agent-cron-enable
make news-agent-multi-once

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ROLLBACK to $PRE_V13_SHA (post-rotation merge)" >> logs/deploy_incidents.log
```

**Prävention:** Phase B erst wenn Watchdog-Soak + Tag-7 `--lag-report` grün — bis dahin bleibt Pfad A (git-only Rollback) offen.

---

## 6. Post-Deploy Eintrag (STRATEGY_THESIS / Changelog)

Nach erfolgreichem Durchlauf in [`STRATEGY_THESIS.md`](STRATEGY_THESIS.md) §6 und Changelog:

```markdown
- [x] **2026-09-02T12:00:01Z:** Gate-Close erreicht (G1 PASS archiviert).
- [x] **Release v1.3 deployed:** `published_at` + `detection_lag` (schema v1.3).
- [x] **Logrotate Phase A:** `logs/*.log` (`logrotate.agent-x-logs-only.conf`).
- [ ] **Logrotate Phase B:** `news_scores.jsonl` — nach Watchdog-Soak (Exit 0) + Tag-7 `--lag-report` (Coverage plausibel).
- [x] **JSONL store readers:** `iter_jsonl_store` (Dedup + Marker + Hash-Kette).
- [ ] **Tag-7 `--lag-report`:** GO/NO-GO (§5.1.1 H1_M2_EVENT_DRIVEN_SPEC).
- [ ] **M2 Live-Replay:** erst ≥90d JSONL + ≥200 gated Events.
```

---

## Siehe auch

- [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) — G1–G4, Hetzner §8.5
- [`H1_M2_EVENT_DRIVEN_SPEC.md`](H1_M2_EVENT_DRIVEN_SPEC.md) — Schema v1.3, Lag-Gate
- [`NEWS_AGENT.md`](NEWS_AGENT.md) — Cron-Marker, Watchdog-Schwellen
