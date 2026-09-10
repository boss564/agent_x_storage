# Audit-Writer Liveness (erzwungene Invariante)

**Stand:** 2026-08-31

## Invariante

> Jeder Audit-Writer, dessen Normalzustand Schweigen ist, muss pro Beobachtungszeitraum mindestens eine Liveness-Marke schreiben; ihr Fehlen ist ein Fehlerzustand.

Schweigen im Datensatz ist **kein** Nachweis, dass beobachtet wurde. Marker-Absenz = der Writer lief nicht oder starb vor dem Marker.

### Geltungsbereich: zeitgesteuert vs. Inline-Gate

Die Invariante gilt für **zeitgesteuert aufgerufene** Writer (Cron, LaunchAgent, stündlicher RT-Takt). Sie gilt **nicht** mechanisch für Inline-Gates, die nur laufen, wenn Payload durchgeht.

| Sorte | Beispiel | Wird aufgerufen | Schweigen heißt |
|-------|----------|-----------------|-----------------|
| **Zeitgesteuert** | Scraper, Gap-Detektor, News-Phase | nach Plan, unabhängig vom Inhalt | lief und fand nichts — **oder** lief nicht |
| **Inline-Gate** | D-Suite (`d_suite_enforcer`), Ethical Boundary (Wave 39) | nur wenn Payload durchgeht | nichts kam durch |

Bei Inline-Gates gibt es keinen Aufruf, der hätte scheitern können. Ein `run_marker` würde dort Beobachtung **vortäuschen** — er bezeugte nur, dass ein Zeitgeber lief, nicht dass das Gate funktioniert.

> **Abgrenzung:** Lebendigkeit eines Inline-Gates ist eine Eigenschaft des **Aufrufers** (Pipeline, Gatekeeper, RT-Job), nicht des Writers. Instanz 7/8 als Liveness-Marker für D-Suite oder Ethical Boundary sind **nicht** vorgesehen.

### Post-Gate: Kopplungsprüfung Ethical Boundary ↔ Wave-38-Gatekeeper

Wenn der Wave-39-Hook vor jedem Gatekeeper laufen soll und still übersprungen wird, ist das ein realer blinder Fleck — sichtbar nicht durch Herzschlag, sondern durch **Paarung** (analog BUY↔SELL im Paper-WORM: 147 verwaiste Einstiege, die keine Zeitmessung gefunden hätte).

**Befund:** `n_gatekeeper_verdicts` gegen `n_certificates` (`certificate_id` im `EthicalBoundaryEnvelope` bei CERTIFIED). Jedes Gatekeeper-Urteil muss ein zugehöriges `certificate_id` tragen; fehlt eines, wurde der Hook umgangen.

Backlog-Eintrag (nach News-24h-Gate, nur wenn Traffic zum Messen da ist): Kopplungsprüfung Hook ↔ Gatekeeper — **kein** Liveness-`run_marker`.

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
| 7 | M2 live monitor | `kind=run_marker` in `data/m2_live_monitor.jsonl` (`writer=m2_live_monitor`) | Marker fehlt/STALE = systemd-Timer tot; `lag_samples=0` bei vorhandenem Marker = ruhiges Fenster. Hetzner: `phase1-m2-install.sh` setzt `WATCHDOG_M2_MONITOR=1` (nicht nur `auto`) — fehlende Audit-Datei = CRITICAL, auch wenn der Timer nie lief |

Code: `agents_b2g/news/feed_health.py` · `agents_b2g/news/scraper.py` · `services/news_agent/liveness.py` · Instanz 4: `services/gap_detector/detector.py` · Instanz 5: `astrocore/sources/news_sentiment_source.py` · Instanz 6: `astrocore/sources/price_gap_source.py` · Instanz 7: `services/m2_live_monitor/liveness.py` · `scripts/m2_live_monitor.py`.

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
