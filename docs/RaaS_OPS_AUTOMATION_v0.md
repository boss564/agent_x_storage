# RaaS — Ops Automation v0 (Cron + Notifications)

**Status:** MAP v0 (2026-08-27) · additiv · **keine offene Hypothese** (Betrieb)  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · kein Order-Send  
**Nicht:** Secrets im Repo · Live-Trade-Alerts · BLOCK aus WARNUNG allein

---

## 1. Zweck

| Paket | Was | Was nicht |
|-------|-----|-----------|
| **A** Täglicher Paper-Report | Cron/systemd → Markdown aus WORM-Audit | Kein Live-Export, kein Sample-Fill |
| **B** Gate-Notify | Telegram/Discord bei **neuen** Risiko-`BLOCKED`-Ereignissen (Simulation/Paper/Screens) | Kein Investment-Alert, kein Token im Git |

---

## 2. Einrichtung A — Daily Paper Report

```bash
# von Hand / Cron (REPO anpassen)
cd /ABS/PFAD/agent_x_storage
export PYTHONPATH=.
make raas-daily-paper-report
# ≡ scripts/raas_daily_paper_report.sh
```

**crontab (Beispiel 23:00 lokale Zeit):**

```cron
0 23 * * * /ABS/PFAD/agent_x_storage/scripts/raas_daily_paper_report.sh >> /ABS/PFAD/agent_x_storage/logs/cron_exporter.log 2>&1
```

**systemd:** `deploy/systemd/raas-paper-exporter.service` + `.timer`  
(Unit `WorkingDirectory=` auf Repo-Root setzen.)

Voraussetzung: Audit existiert (`make raas-paper-trading-smoke` mindestens einmal).

---

## 3. Einrichtung B — Notification Bridge

```bash
cp config/raas_ops.env.example config/raas_ops.env   # gitignored pattern: use .env
# Tokens nur in Environment / raas_ops.env (nicht committen)
export $(grep -v '^#' config/raas_ops.env | xargs)   # oder systemd EnvironmentFile=

# Dry-run (default): zeigt Payload, sendet nicht
PYTHONPATH=. python3 scripts/raas_notify_gate_blocks.py

# Senden
PYTHONPATH=. python3 scripts/raas_notify_gate_blocks.py --send
```

Quellen (append-only JSONL unter `logs/worm/`, gitignored):

| Datei | Nutzung |
|-------|---------|
| `gate_blocks.jsonl` | bevorzugter Feed (explizite Blocks) |
| `paper_trading_audit.jsonl` | Zeilen mit `decision=BLOCKED` / Risk-Reasons |
| `flash_crash_retrospective.jsonl` | Screen-WORM (nur wenn BLOCK-Felder) |
| `barrier_cal_surface.jsonl` | Kalibrier-WORM (kein Prod-Block) |

Dedup: `logs/worm/notify_gate_state.json` (Offset/`seen` hashes).

**Dedup-Verhalten (bewusst):**

| Situation | Verhalten |
|-----------|-----------|
| State-Datei **fehlt** | `seen=∅` → alle aktuell passenden Blocks gelten als **neu** (erneute Meldung möglich) |
| State **nicht lesbar** / kaputt | wie fehlt (`seen=∅`) |
| State nach `--send` **nicht schreibbar** | Exit **3** + Fehlermeldung; nächster Lauf kann dieselben Blocks erneut melden |
| `--send` ohne konfigurierten Kanal | Exit **2** + klare Meldung „kein Kanal … nichts gesendet“ (kein stilles No-op) |

Nachricht enthält immer: `live_execution=false` · `not_investment_advice=true` ·  
**kein** BLOCK allein wegen Warn-Band (Amendment).

---

## 4. Charter

```text
live_execution = false
order_send = forbidden
secrets = env only
warn ≠ trip notify
```

---

## 5. Verweise

| Artefakt | Rolle |
|----------|-------|
| `scripts/raas_daily_paper_report.sh` | Cron-Wrapper |
| `scripts/raas_notify_gate_blocks.py` | Notify Bridge |
| `config/raas_ops.env.example` | Template |
| `deploy/systemd/raas-paper-exporter.*` | Timer |
| `docs/RaaS_WARN_BAND_AMENDMENT_v0.md` | Warn ≠ BLOCK |
