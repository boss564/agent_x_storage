# Audit-Writer Liveness (erzwungene Invariante)

**Stand:** 2026-08-30

## Invariante

> Jeder Audit-Writer, dessen Normalzustand Schweigen ist, muss pro Beobachtungszeitraum mindestens eine Liveness-Marke schreiben; ihr Fehlen ist ein Fehlerzustand.

Schweigen im Datensatz ist **kein** Nachweis, dass beobachtet wurde. Marker-Absenz = der Writer lief nicht oder starb vor dem Marker.

## Instanzen (nicht jedes Mal neu herleiten)

| Instanz | Writer | Marke | Tot vs. ruhig |
|---------|--------|--------|----------------|
| 1 | Feed-Gap | `source=heartbeat` in `feed_gaps.jsonl` | `writer_liveness_status` |
| 1b | Paper-Ticks | `last_tick_ts` in `feed_gap_state.json` (Fallback: Feld `last_tick_ts` auf Heartbeat-Zeile) | `paper_tick_liveness` in `raas_hourly_rt_check.py` — **nicht** `heartbeat.ts` |
| 2 | Cross-Venue | per-venue `heartbeat` | `writer_liveness_status(..., venue=)` |
| 3 | News-Agent | `source_type=run_marker` in `news_scores.jsonl` | `feeds.*.health` |
| 4 | Price-Gap-Detector | `kind=run_marker` in `data/gap_reports.jsonl` | Marker fehlt = Cron/Skript tot; `coverage_gaps=0` bei vorhandenem Marker = ruhiger Markt |
| 5 | News-Sentiment PhaseSource | `kind=run_marker` in `data/phase_signals/news_sentiment.jsonl` | Marker fehlt = Cron/Adapter tot; `status=empty` bei vorhandenem Marker = kein News-Fenster |
| 6 | Price-Gap PhaseSource | `kind=run_marker` in `data/phase_signals/price_gap.jsonl` | Marker fehlt = Cron/Adapter tot; `status=empty` bei vorhandenem Marker = keine COVERAGE_GAP |

## News: Transport-Klassifikation (kein Sammelalarm)

`bozo OR empty` ist verboten. `bozo` allein ist kein harter Fehler (XML-Quirks).

| status | bozo | entries | structure_ok | health |
|--------|------|---------|--------------|--------|
| ≠200 (z.B. 404) | * | 0 | * | **dead** |
| 200 | 1 | 0 | * | **dead** |
| None + bozo | 1 | 0 | * | **dead** (kein HTTP) |
| 200 | 0 | 0 | false | **degraded** (kein Feed-Container) |
| 200 | 0 | 0 | true | **quiet** |
| 200 | 0 | >0 | true | **ok** |
| 200 | 1 | >0 | * | **degraded** |

`structure_ok` = Container-Präsenz (`channel` / Atom `feed`), nicht Item-Anzahl — Pre-Reg [`NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md). `degraded` bricht die Quiet-Streak in `derive_quiet_streaks`.

Code: `agents_b2g/news/feed_health.py` · `agents_b2g/news/scraper.py` · `services/news_agent/liveness.py` · Instanz 4: `services/gap_detector/detector.py` (`kind=run_marker` in `data/gap_reports.jsonl`) · Instanz 5: `astrocore/sources/news_sentiment_source.py` · Instanz 6: `astrocore/sources/price_gap_source.py` (`kind=run_marker` in `data/phase_signals/price_gap.jsonl`).

Ein toter Feed darf den Lauf nicht abbrechen (sonst fehlt der Marker). Ein harter Absturz **vor** dem Marker ist das gewollte Liveness-Negativ. Dasselbe für den Preis-Cron: fehlende Marke in `gap_reports.jsonl` ist nicht „keine Lücken“.

## Smoke

```bash
PYTHONPATH=. python3 tests/test_news_agent.py
```

`test_transport_health_matrix` friert die Health-Tafel ein (inkl. `structure_ok`). `test_structure_ok_s1_to_s7` / `test_degraded_breaks_quiet_streak` decken Pre-Reg S1–S7 + Auflage 3. `test_run_marker_carries_health_not_counts_only` prüft, dass `fetched: 0` nicht tot und ruhig vermischt. `test_quiet_stale_duration_frozen` friert 72 h ein.

## Verlauf: `quiet` → `stale` (Pre-Reg 2026-08-30)

Pro Lauf bleibt `health=quiet` korrekt. Über die Marker-Historie gilt:

> `QUIET_STALE_AFTER_S = 72 × 3600` (259200). Originalwert = Codekonstante. Nicht nachjustieren, wenn ein Feed auffällig wirkt (Anti-HARKing, analog `MIN_OBSERVABLE_FRACTION=0.80` / `null_gaps_proven`).

n aufeinanderfolgende `quiet` derselben Quelle, Zeitspanne der Serie ≥ 72 h → `streaks[source].stale=true`. Ein einzelner ruhiger Lauf ist nicht stale. `ok`/`dead`/`degraded` unterbrechen die Serie. Keine neue Instrumentierung — Ableitung aus vorhandenen `run_marker`.

**Verdrahtung (2026-08-30):** `run_once` setzt `status=DEGRADED`, wenn `stale` nicht leer ist (auch ohne `dead`). Marker-Alter: `run_marker_freshness` / `NEWS_MARKER_MAX_AGE_H` (Default 2 h) → `WRITER_STALE` im Lauf; `make news-agent-cron-status` FAIL bei STALE.

## sentiment_score

Kontinuierlich (−1..+1). Keine diskrete `bullish`/`bearish`-Schwelle im Multi-Scraper. Wer downstream diskretisiert, muss den Schwellenwert einfrieren (Anti-HARKing), sonst ist es ein nachjustierbarer Hyperparameter.
