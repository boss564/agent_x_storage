# Messperiode — Start-Sequenz (Pre-Flight → KeepAlive)

Charter: `diagnostic_only=true`, `live_execution=false`, `order_send=false`.  
Basis-Commit Messperiode: nach Ops-Implementierung den **aktuellen sauberen HEAD** in `preflight_check --expect-commit` und in der Run-Stichprobe festhalten (Plan-Anker war `bfcc856d` + nachfolgende Ops-Commits).

## Vorbedingungen

1. **Freeze vorhanden:** `ops/allowlist.freeze.json` (Gamma, BTC/ETH, `source=gamma`).
   - Neu erzeugen nur vor Perioden-Start:
     ```bash
     python3 order_execution_engine/scripts/resolve_allowlist_gamma.py
     ```
   - Während der Periode **nicht** neu resolven. Settled/Rotate → belegt verwerfen, Tag-7-Review.
2. **Policy eingefroren:** `ops/run_policy.json` mit `max_news_age_s=3900`, `max_book_age_ms=2000`, `reject_stale`, `re_cross`, `fallback_limit`.
3. **Frische DB:** `data/shadow_live/` (kein Test-Temp). Bei Neustart der Periode Verzeichnis leeren/archivieren.
4. **News-Agent:** schreibt in dasselbe `data/news_scores.jsonl` (Pfad `THX_OS_ULTRA/...`, nicht nur `THX_OS_ULTRA - Data/...`). Stündlich belassen.
5. **Uhr:** NTP/automatische Zeit am Host.

## Start

```bash
cd /Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage
mkdir -p data/shadow_live ~/Library/Logs/agentx-shadow

# 1) Pre-Flight (vor KeepAlive)
PYTHONPATH=. python3 order_execution_engine/ops/preflight_check.py \
  --expect-commit "$(git rev-parse --short HEAD)"

# 2) Plist installieren (einmalig)
cp order_execution_engine/ops/com.agentx.shadow-runner.plist \
  ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.agentx.shadow-runner.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.agentx.shadow-runner.plist

# 3) Stichprobe nach Warmup (~1 min, dann nach erstem Stunden-Batch)
PYTHONPATH=. python3 order_execution_engine/ops/preflight_check.py --after-start \
  --expect-commit "$(git rev-parse --short HEAD)"
```

Logs: `~/Library/Logs/agentx-shadow/shadow-runner.log` (+ `.err.log`).  
Rotation: macOS unified logging / manuelles `newsyslog` — Pfade dokumentiert; bei Wachstum rotieren oder archivieren.

## Tag-1-Gates (kein Config-Touch)

| Gate | Erwartung |
|---|---|
| `no_book` | niedrig nach Warmup |
| `news_too_old` | nicht ~100 % nach erstem Batch |
| `unresolved` | darf hoch sein (Allowlist-Schnitt) |
| `STALE_SNAPSHOT` | ≈ 0 |
| `telemetry_fill_metrics` | Nebenzeilen bei Fills |
| Dedup | 0 Doppel-`item_id` im Stunden-Batch |

Bei Rot: fixen, **neuen Run** (`run_id`), Periode zählt ab grünem Run.  
Config (θ, Stufen, Allowlist, Grenzen) während der Periode nicht ändern.

## Tag 7 / Tag 21

- Tag 7: Stopp-Kriterien (Signale ≥ 200? Fills ≥ 50 / partiell ≥ 10?).  
- Tag 21 hart: Ende; Unterdeckung = Befund „Selektion zu restriktiv“.  
- Auswertung Fragen 1–4 erst bei ausreichender Deckung.
