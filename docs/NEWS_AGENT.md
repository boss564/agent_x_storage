# News-Agent (Stufe 2) — isoliert

RSS → Keyword-Sentiment → JSONL. **Kein** Cluster-Patch, **kein** Order-Send, kein DeepSeek/Discord.

## Herkunft

Isoliert aus `imports/legacy_daytrading/news_bot/scraper.py` (RSS CoinDesk/Cointelegraph, MD5-Dedup). **Nicht** übernommen: DeepSeek-API, Discord-Webhook, 24/7-Loop als Default, Preis-Tracking.

## Nutzung

```bash
make news-agent-test          # Fixture-RSS, kein Netz
make cross-chain-validate     # config/cross_chain_map.json
make news-agent-once         # Legacy-PoC → logs/audit/news_scores.jsonl
make news-agent-multi-once   # Multi-Scraper → data/news_scores.jsonl
make news-agent-cron-enable # genau eine Zeile, Marker # AGENTX_NEWS_AGENT
make news-agent-cron-status   # launchd/cron + marker_liveness (NEWS_MARKER_MAX_AGE_H)
make news-watchdog            # read-only health; WARN 90m / CRIT 150m (hourly cron); lag/pubdate metrics-only
make news-watchdog-json       # JSON für Monitoring (GO/NO-GO: Tag-7 --lag-report)
make news-agent-cron-disable
make news-agent-gap-report     # Entity-Lücken → exports/reports/gap_analysis.json
make news-agent-gap-cron-enable  # optional täglich 00:00, Marker # AGENTX_NEWS_GAP
make gap-detector-once          # Preis-Anomalie (ccxt Binance, kein API-Key)
make satellites-cron-enable  # News :00 + Price-Gap :05, Cluster unberührt
make gap-detector-cron-status
make news-sentiment-phase-cron-enable  # PhaseSource :06 → JSONL-Append
make news-sentiment-phase-cron-status  # muss count=1 unique=1
make price-gap-phase-cron-enable         # PhaseSource :07 → price_gap.jsonl
make price-gap-phase-cron-status
```

Stdout des Cron-Laufs: `logs/audit/news_cron.log`. Scores (Cron): `data/news_scores.jsonl`.

Optional: `NEWS_AGENT_JSONL=/pfad/news_scores.jsonl`. `--loop` nur bewusst (`scripts/run_news_agent.py --loop`).

## Schema (`news_agent_multi/v1.3`)

`timestamp` = Ingest (`t_ingest`), `published_at` = Feed-Veröffentlichung (RSS `pubDate` / Atom `published`), `detection_lag` = Sekunden Ingest−Published (JSONL, berechnet).  
`sentiment` −1/0/1, `label`, `confidence`, `symbols` (Ticker), `assets` (Ticker + `MACRO` / `GENERAL`), `entities` (`chains` / `bridges` / `protocols` / `persons`), `cross_chain_impact` (`bridges`, `affected_chains`, `impact_score`), `item_id`, Hash-Kette (`prev_hash`/`hash`). Jede Zeile: `diagnostic_only`, `live_execution=false`, `order_send=false`.

`assets` kommt aus `TOKEN_KEYWORDS`. `entities` aus `CHAIN_KEYWORDS` / `BRIDGE_KEYWORDS` / `PROTOCOL_KEYWORDS` / `PERSON_KEYWORDS` in `agents_b2g/news/config.py`. `cross_chain_impact` aus `config/cross_chain_map.json` via `services/news_agent/impact.py`: passende Bridges (Name oder Chain-Schnitt), `affected_chains` aus `correlation_matrix` (plus Korridor-Ziele), `impact_score` = max `impact_factor` der Treffer. Nicht jede Bridge-Peer-Chain — sonst würden Polygon/Optimism das Solana-Beispiel überdecken. Kurze Tokens nur wortgebunden (`\beth\b`, nicht WHETHER; `matic` nicht automatic). `GENERAL` nur wenn kein Ticker und kein MACRO. `relevant_only` nimmt Ticker + MACRO, nicht GENERAL allein.

Scorer: `keyword_v1` (Lexikon). LLM bleibt optional und unverdrahtet.

## Korrekturen (Datenqualität)

- Ticker nur wortgebunden (`\beth\b` / `ethereum`): WHETHER / Together / Ethics / Netherlands sind **nicht** ETH.
- Neutral ist `NEUTRAL`, keine Richtungswette. Legacy-Alerts nur bei `sentiment ±1` und `confidence > 0.7`.
- Feed-Ausfall: `run_once` setzt `FEED_SILENT` / `DEGRADED` plus `feed_errors` — nicht still 0 Einträge.
- Legacy: `seen_hashes` persistiert; erster Lauf seedet ohne Discord; Preis **vor** CSV+Alert; `.strip('```json')` entfernt.

## Host-Cron (nicht Cluster)

**macOS:** `make news-agent-cron-enable` installiert **LaunchAgent** `com.agentx.news-agent` (stündlich :00, `.venv/bin/python` absolut) — kein User-Cron für News (Sleep/:00-Verpasser). **Linux (Hetzner):** Cron mit `cd`, `PYTHONPATH=.`, absolutem `venv/bin/python`, `--once` — siehe [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) §8.5. **Cluster:** eigener CronJob — §8.4.

**Scheduler-Epoche:** `NEWS_SCHEDULER_EPOCH_TS = 2026-09-01T12:00:01.615076+00:00` — erster **autonomer** Hetzner-Cron-`:00` (syslog `12:00:01` + `run_marker` WORM). **`GATE_CLOSE`** = `2026-09-02T12:00:01.615076+00:00` (`NEWS_SCHEDULER_GATE_CLOSE_TS`, Epoche + 24 h). Quiet-Streaks und Feed-Qualität ignorieren ältere `run_marker` (Vorlauf inkl. Mac-VOID `2026-08-31T09:00Z`, Smoke). Analog `OPTION_B_EXIT_EPOCH_TS` im Paper-WORM.

**24h-Scheduler-Gate (PASS/FAIL):** Fenster **2026-09-01T12:00:01Z → 2026-09-02T12:00:01Z** (Hetzner, **LIVE**) — Kriterien in [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) (**G1-A1:** `n ≥ floor(hours_up×0.85)`; **G2:** max. 3 h Lücke in Betriebszeit; **G3:** `marker_liveness` ACTIVE; **G4:** `downtime_h` / A2). Linux-Cron feuert stündlich `:00`; kein Sleep-Nachholen wie LaunchAgent.

Unabhängig von `regime-swarm-hourly-rt` (`:14` UTC im Pod). Pfade mit Leerzeichen sind gequotet.

`make satellites-cron-enable` setzt **zwei** Host-Zeilen: News `:00` (`# AGENTX_NEWS_AGENT`) und Preis-Gap `:05` (`# AGENTX_PRICE_GAP` → `data/gap_reports.jsonl` + `docs/SWARM_GAP_ANALYSIS.md`). Der Preis-Cron: `cd` ins Repo, absoluter `{repo}/.venv/bin/python` und absoluter Skriptpfad (Cron-CWD ist `$HOME`). Jeder Lauf schreibt `kind=run_marker` (Invariante Instanz 4). `news-agent-cron-disable` entfernt nur die News-Zeile.

News-Sentiment PhaseSource: `make news-sentiment-phase-cron-enable` setzt eine **dritte** Host-Zeile um `:06` (`# AGENTX_NEWS_PHASE`) — nicht `:05` (das ist der Preis-Gap). Filter ist der Marker, nicht `grep news_sentiment_source`. Append nach `data/phase_signals/news_sentiment.jsonl`; jeder Lauf schreibt `kind=run_marker` (Instanz 5), auch bei leerem Lookback. Cluster-Registration (`ASTROCORE_PHASE_SOURCES`) bleibt aus.

Price-Gap PhaseSource: `make price-gap-phase-cron-enable` setzt `:07` (`# AGENTX_GAP_PHASE` — **kein** Prefix von `# AGENTX_PRICE_GAP`). Liest `data/gap_reports.jsonl`, mappt `COVERAGE_GAP` (Vorzeichen der %‑Bewegung, Skalen 10/16 eingefroren) nach `data/phase_signals/price_gap.jsonl`. `UNTRACKED_ENTITY` wird nicht auf die Watchlist gesprüht. `kind=run_marker` auch ohne Gap (Instanz 6). Schreibpfad: `assert_handoff_output` wirft `order_send_forbidden` bei Rückschreiben auf Detector-JSONL oder Ziel außerhalb `phase_signals/`.

- `written=0` bei Dedup: normal, JSONL bleibt unverändert.
- `FEED_SILENT` / `DEGRADED`: Feed-Ausfall (HTTP/Parse) **oder** `streaks.*.stale` (72 h quiet). Steht im Cron-Log als JSON `status` + `feed_errors` / `stale`.
- `WRITER_STALE`: Prior-`run_marker` älter als `NEWS_MARKER_MAX_AGE_H` (Default **2**). Cold-Start ohne Marker bleibt `ok` im Lauf; `make news-agent-cron-status` warnt bei MISSING, schlägt bei STALE fehl.
- `item_id`: `MD5(source|link)`; ohne Link normalisierter Titel. Titeländerungen derselben URL erzeugen keine zweite ID.

## Gap-Detector (Schritt 3a)

Liest die letzten 100 Artikel aus `data/news_scores.jsonl` (ohne `run_marker`). Meldet Großschreibung/Anführungszeichen-Kandidaten, die nicht in den Keyword-Katalogen stehen, ab **mehr als 3** Treffern (`min_count=4`). Preis-Anomalien sind zurückgestellt (`price_anomaly: null`). `SUI` ist bereits in `TOKEN_KEYWORDS` und `CHAIN_KEYWORDS` — das Beispiel „SUI fehlt“ gilt nicht mehr.

```bash
make news-agent-gap-report
# optional nach dem Ingest:
PYTHONPATH=. python3 -m services.news_agent.runner --once --gap-report
```

Täglicher Host-Cron (nicht stündlich): `make news-agent-gap-cron-enable` — Marker `# AGENTX_NEWS_GAP`, unabhängig von `# AGENTX_NEWS_AGENT`. `news-agent-cron-disable` lässt die Gap-Zeile stehen.

## PhaseSource News Sentiment (lokal)

`astrocore/sources/news_sentiment_source.py` liest `data/news_scores.jsonl` (`assets`/`target_assets`, `sentiment`/`sentiment_score`), skippt `run_marker`, aggregiert gewichtet. MACRO wird **nicht** auf alle Watchlist-Ticker gesprüht. Cluster-Registration (`ASTROCORE_PHASE_SOURCES`) wartet auf Fenster W.

```bash
make news-sentiment-phase                 # stdout, kein Append
make news-sentiment-phase-once         # einmal append + run_marker
make news-sentiment-phase-cron-enable   # stündlich :06, Marker # AGENTX_NEWS_PHASE
make news-sentiment-phase-cron-status  # count=1 unique=1
PYTHONPATH=. python3 -m astrocore.sources.news_sentiment_source --asset BTC --lookback-hours 6
```

## PhaseSource Price Gap (lokal)

`astrocore/sources/price_gap_source.py` liest `data/gap_reports.jsonl`, skippt `run_marker`, nimmt nur `COVERAGE_GAP`. `phase_bias = clip(Δ% / scale)` mit eingefrorenen Skalen 10 (1h) und 16 (24h). Fenster-Test ist `split("+")`, nicht Substring (`"1h" in "24h"` wäre wahr). Cluster-Registration wartet auf Fenster W.

```bash
make price-gap-phase
make price-gap-phase-once
make price-gap-phase-cron-enable
make price-gap-phase-cron-status
```

## Multi-Scraper (`services/news_agent/`)

Plugin-Architektur, unabhängig vom Host-Cron (`scripts/run_news_agent.py`):

```
services/news_agent/
  scrapers/base_scraper.py
  scrapers/rss_scraper.py          # CoinDesk / Cointelegraph
  scrapers/announcement_scraper.py  # Binance CMS
  core/processor.py                 # Sentiment, assets, entities, Dedup, impact_level
  impact.py                        # Cross-chain map → cross_chain_impact
  gap_detector.py                  # unbekannte Ticker/Namen in den letzten N Artikeln
  runner.py                        # lädt alle Scraper dynamisch
```

`NewsItem`: `timestamp`, `source_type` (`rss`|`announcement`|`social`|`regulatory`), `source_name`, `title`, `url`, `target_assets`, `entities`, `cross_chain_impact`, `sentiment_score` (−1..+1), `impact_level` (LOW/MEDIUM/HIGH/CRITICAL). Schema `news_agent_multi/v1.2`.

`make cross-chain-validate` prüft `config/cross_chain_map.json`. Override: `CROSS_CHAIN_MAP=/pfad.json`.

```bash
make news-agent-test          # scripts/ + tests/test_news_agent.py
PYTHONPATH=. python3 -m services.news_agent.runner   # → data/news_scores.jsonl
# oder: make news-agent-multi-once
```

`impact_level=CRITICAL` ruft Telegram nur bei `NEWS_AGENT_TELEGRAM_CRITICAL=true` (bestehende `send_telegram`, keine neuen Secrets). Host-Cron: `python3 -m services.news_agent.runner --once` → `data/news_scores.jsonl`. Cluster-Cron unverändert.

**Hetzner Logrotate (post gate-close):** [`docs/V13_DEPLOY_RUNBOOK.md`](V13_DEPLOY_RUNBOOK.md) · Template `deploy/hetzner/logrotate.agent-x.conf` — rename+create (kein `copytruncate`), `dateformat -%Y%m%d-%s`, 365d Archive. **Streaming-Loader:** `src/ingestion/news_jsonl_loader.py` (`iter_jsonl_store`, `iter_news_records_tail`).

Pro Lauf schreibt der Runner einen `run_marker` (Transport-Health je Quelle: `ok` / `quiet` / `degraded` / `dead`). `entries==0` ist nicht automatisch tot. **Struktur:** `structure_ok` = Channel-/Feed-Container-Präsenz (nicht Item-Anzahl); `¬structure_ok` → `degraded` (bricht Quiet-Streak). Pre-Reg: `docs/NEWS_FEED_STRUCTURE_PREREG.md`. Aufeinanderfolgendes `quiet` ≥ **72 h** (Pre-Reg `QUIET_STALE_AFTER_S`, nicht nachträglich drehen) → `streaks.*.stale`. Invariante: `docs/AUDIT_WRITER_LIVENESS.md`. `sentiment_score` bleibt kontinuierlich; keine `bullish`/`bearish`-Schwelle.
