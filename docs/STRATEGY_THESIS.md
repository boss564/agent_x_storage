# Agent-X — Strategy Thesis & Alpha Architecture

**Status:** ACTIVE (iterative hypothesis testing)  
**Last Updated:** 2026-09-01  
**Method:** Backtest-driven falsification (Stage A / B2 / H2) · prove-it-first  
**Parent:** [`NEWS_AGENT.md`](NEWS_AGENT.md) · [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) · [`SHADOW_EVALUATOR_PREREG.md`](SHADOW_EVALUATOR_PREREG.md)

---

## 0. Zweck

Dieses Dokument ist ein **Quant-Lab-Log** — kein Grabstein, kein Pitch-Deck. Jede Hypothese wird formuliert, getestet, und bei Falsifikation **eingefroren** (Commit-Referenz), damit keine tote Infrastruktur weiterläuft.

**Kern-Invariante:**

```text
E[R_price_only_gross] ≈ 0  →  E[PnL_net] ≈ −Kosten
```

Wenn unkonditionierte Preis-Trigger kein Brutto-Alpha liefern, ist ein Sentiment-Filter **kein Sanatorium** für ein totes Signal — er darf nur Katalysatoren auf **exogenen** Ereignissen verstärken.

---

## 1. Nullmodell (H₀) — geeichte Basislinie

| Feld | Wert |
|------|------|
| **Status** | Aktiv — 24h-Gate §8.5 auf Hetzner (`NEWS_SCHEDULER_EPOCH_TS` ab `2026-09-01T12:00:01.615076Z`, Commit `c8755c2e`) |
| **Funktion** | Negativkontrolle: Scheduler, WORM-Marker, Liveness, Kosten-Eichung (Fenster W) |
| **Invariante** | `E[PnL_net] ≤ 0` ohne validiertes Primärsignal — prove-it-first |
| **Gate-Close** | `2026-09-02T12:00:01.615076Z` |

H₀ beantwortet nicht „haben wir Edge?“, sondern „läuft die Mess-Infrastruktur zuverlässig?“. Alpha-Claims kommen erst nach H₀-PASS.

---

## 2. Empirische Falsifikation — unkonditionierte 15m-Preis-Trigger

**Setup (gemeinsam):** BTC/USDT + ETH/USDT · 365 Tage · 15m OHLCV · 36 Grid-Kombinationen  
`k_entry ∈ {1.5, 2.0, 2.5, 3.0}` · `k_tp ∈ {1.0, 1.5, 2.0}` · `k_sl ∈ {0.5, 1.0, 1.5}`  
σ₂₄ₕ-Rolling = 96 Kerzen · `shift(1)` · Non-Overlap · Pessimistic Intrabar · 19 bps Round-Trip

### 2.1 Stage A — Long Mean-Reversion (Dip-Kauf)

| | |
|--|--|
| **Hypothese** | Nach Dip `return_15m < −k_entry × σ_15m` revertiert Preis um `k_tp × σ` innerhalb 60 min |
| **Skript** | [`scripts/backtest_h1_price.py`](../scripts/backtest_h1_price.py) |
| **Commits** | `938ec8ce` (non-overlap + Scenario-Klassifizierung) |
| **E[PnL_gross] best** | +0,005% (BTC) · −0,008% (ETH) |
| **E[PnL_net] best** | −0,185% (BTC) · −0,198% (ETH) |
| **Szenario** | **3 — Falsifiziert** |
| **Artefakt** | [`results/results_stage_a.csv`](../results/results_stage_a.csv) |

### 2.2 Stage B2 — Short Momentum (Dip-Fortsetzung)

| | |
|--|--|
| **Hypothese** | Nach gleichem Dip fällt Preis weiter um `k_tp × σ` (SHORT) |
| **Skript** | [`scripts/backtest_h1_price_momentum.py`](../scripts/backtest_h1_price_momentum.py) |
| **Commit** | `366957a0` |
| **E[PnL_gross] best** | −0,012% (BTC) · +0,010% (ETH) |
| **E[PnL_net] best** | −0,202% (BTC) · −0,180% (ETH) |
| **Szenario** | **3 — Falsifiziert** |
| **Artefakt** | [`results/results_stage_b2_momentum.csv`](../results/results_stage_b2_momentum.csv) |

### 2.3 Stage H2 — Volatility Breakout (letzter reiner Preis-Action-Test)

| | |
|--|--|
| **Hypothese** | Nach Vol-Kompression (`σ₁₅ₘ[t−1] < k_low × median(σ, 96)`) folgt Vol-Expansion (`σ₁₅ₘ[t] > k_high × median`) → richtungsgebundener Trade |
| **Skript** | [`scripts/backtest_h2_vol_breakout.py`](../scripts/backtest_h2_vol_breakout.py) |
| **Grid** | `k_low ∈ {0.5, 0.7, 0.9}` · `k_high ∈ {1.5, 2.0, 2.5}` · `k_tp/k_sl` wie A/B2 → **81 Kombinationen × Long/Short × 2 Assets = 324 Zellen** |
| **σ-Definition** | `σ₁₅ₘ` = `std(returns, 15)` · `shift(1)` · Baseline = `median(σ, 96)` |
| **E[PnL_gross] best** | +0,34% (BTC Long, n=2) · +1,04% (ETH Long, n=4) — **nicht signifikant** |
| **E[PnL_net] best** | +0,15% (BTC Long, n=2) · +0,85% (ETH Long, n=4) — **nicht signifikant** |
| **Hochfrequenz-Zelle** | k_low=0.9, k_high=1.5: 36–47 Trades/Jahr → E[PnL_net] ≈ **−0,21% bis −0,27%** |
| **Grid-Median** | E[PnL_net] = **−0,11%** · nur 9,9% Zellen netto positiv |
| **Szenario** | **3 — Falsifiziert** (min. 10 Trades für S1 erforderlich; Best-Cells n≤4) |
| **Artefakt** | [`results/results_stage_h2_vol_breakout.csv`](../results/results_stage_h2_vol_breakout.csv) |

### 2.4 Orthogonale Schlussfolgerung (Preis-Action abgeschlossen)

```text
Long nach 2σ-Dip:         E[R_gross] ≈ 0   (keine Reversion)       — Stage A
Short nach 2σ-Dip:        E[R_gross] ≈ 0   (keine Fortsetzung)     — Stage B2
Vol-Kompression→Breakout: E[R_gross] ≈ 0   (keine Expansion-Edge)  — Stage H2
Netto (alle Stages):      ≈ −19 bps         (Kostenstrafe bei ausreichend n)
```

**Erkenntnis:** Reine Preis-Action auf 15m (Dip-Reversion, Momentum, Vol-Breakout) liefert kein robustes Brutto-Alpha. Der Pivot zu **exogenen Primärsignalen** (News/Regime) ist keine strategische Präferenz mehr, sondern **empirisch erzwungen**.

---

## 3. Strategische Neuausrichtung — Event-Driven Primär-Signale (H₁)

| Rolle | Inhalt |
|-------|--------|
| **Preis** | Ausführungsmedium, **nicht** Primär-Trigger |
| **Primärsignal** | Muss **exogen** sein — strukturelle News, On-Chain-Net-Flows, Cross-Graph-Entitäten (Neo4j), Regime-Wechsel mit kausaler Story |
| **News-Agent** | Liefert diagnostische Events + Liveness — Kandidat für H₁, **nach** G1-PASS und Fenster W |
| **Shadow Evaluator** | Strang B.1 — erst nach sauberem Scheduler-Gate |

```text
E[R_priceOnly] ≤ 0  ⟹  Fokus → 100% auf exogene Katalysatoren
```

### 3.1 Datenproblem & Stufenplan

| Stufe | Name | Daten | Status |
|-------|------|-------|--------|
| **M0** | Null-Injection | Synthetisches Sentiment auf Stage-A-Trade-Pool | ✅ PASS (500 Seeds, 100% within ±5 bps) |
| **M1** | Oracle-Decke | Lookahead `gross_pnl ≥ +30 bps` | ✅ Decke existiert (n=341, E[net]=+27 bps) — **kein** News-Beweis |
| **M2** | Live-Replay | `news_scores.jsonl` akkumuliert | **Spezifikation fertig** — Live blockiert bis ≥90d Daten |

**Wichtig:** Stage B („Sentiment filtert Dips“) ist **verworfen** — Base-Signal falsifiziert.  
M0/M1 fragen nicht „funktioniert News?“, sondern: *Lohnt sich Datensammlung überhaupt?* und *Ist die Methodik sauber?*

→ Vollständige Präreg: [`docs/H1_NEWS_METHODOLOGY_PREREG.md`](H1_NEWS_METHODOLOGY_PREREG.md)  
→ M2-Spezifikation: [`docs/H1_M2_EVENT_DRIVEN_SPEC.md`](H1_M2_EVENT_DRIVEN_SPEC.md)  
→ Skripte: M0/M1 [`backtest_h1_news_null_injection.py`](../scripts/backtest_h1_news_null_injection.py) · M2-Skeleton [`backtest_h1_news_m2_skeleton.py`](../scripts/backtest_h1_news_m2_skeleton.py)

**M1-Nuance:** Oracle-Decke zeigt Varianz im Pool (~19% mit gross ≥ +30 bps), nicht dass News sie findet.  
**M2-Vorbehalt (§2.2.1):** `t₀` = Ingest (stündlicher Cron) — misst nicht die unmittelbare News-Reaktion; `published_at` + `detection_lag` vor Live-Replay Pflicht.

---

## 4. Offene Fragen (priorisiert)

### 4.1 Zeitrahmen-Skalierung (LOW)

- Gleiche Dip-Logik auf 1h/4h? Fee-Last relativ zu σ sinkt — aber A+B2 auf 15m deuten auf Brutto ≈ 0 unabhängig von Richtung.
- **Erwartung:** Ähnliches Fair-Game — kein Ersatz für orthogonale Tests.

### 4.2 H₁ News — Daten & Methodik (HIGH, M0/M1 sofort)

- **Blocker M2:** Keine 12-Monats-News-Historie — Live-JSONL erst ab Epoch.
- **M0:** Zufälliges Sentiment auf Dip-Trade-Pool → Filter darf kein Schein-Alpha erzeugen.
- **M1:** Oracle-Decke (`gross ≥ +30 bps`) → selbst perfekter Filter rettet Dip-Pool?
- **Regel:** Wenn M1 tot → H₁ = **News-first** (Event → Entry), nicht Dip-Filter.
- **Präreg:** [`H1_NEWS_METHODOLOGY_PREREG.md`](H1_NEWS_METHODOLOGY_PREREG.md)

### 4.3 Hypothesis H2: Volatility Breakout — **FALSIFIZIERT** (2026-09-01)

Orthogonal zur Dip-Physik — andere Marktineffizienz (Kompression → Expansion):

| Feld | Spezifikation |
|------|----------------|
| **Kompression** | `σ₁₅ₘ[t−1] < k_low × median(σ, 96)` |
| **Breakout** | `σ₁₅ₘ[t] > k_high × median(σ, 96)` |
| **Exit** | TP/SL = `k × σ₁₅ₘ` · Time-Exit 60 min · pessimistic intrabar |
| **Ergebnis** | Szenario 3 — Grid-Median netto −0,11%; Best-Cells n≤4; Hochfrequenz-Zellen netto ≈ −19 bps |

Verbleibende Kandidaten (nicht mehr Preis-Action):

| Kandidat | Status |
|----------|--------|
| Volatility Breakout | ❌ Falsifiziert (H2) |
| Regime Change | → H₁ News/Regime-Trigger |
| Volume Surge | LOW — erst nach H₁ |
| Compression → Expansion (Range) | LOW — orthogonal, aber Preis-Action-Klasse gesperrt |

### 4.4 Cross-Asset / Cross-Venue (LOW)

- Altcoins: höhere Spreads → Fee-Problem verschärft.
- Perps/Funding: inkrementeller Test, nicht Priorität.

---

## 5. Methodische Prinzipien (eingefroren)

1. **Falsifikation vor Bestätigung** — Hypothesen ablehnen, nicht retten.
2. **Orthogonale Tests** — Long scheitert → Short testen, bevor Timeframe skaliert wird.
3. **Cost-First** — 19 bps (2×7,5 bps Fee + 2 bps Slippage) **vor** Bewertung.
4. **Look-Ahead-Schutz** — σ nur aus Vergangenheit (`shift(1)`).
5. **Pessimistic Execution** — TP+SL gleiche Kerze → SL (konservativ).
6. **Non-Overlap** — Position schließen, dann nächster Entry (`idx = exit_idx + 1`).
7. **Plateau-Robustheit** — ≥60% Nachbarzellen positiv für Scenario 1.
8. **Mess-Hierarchie Infrastruktur** — erst installieren/beobachten (Gap-Cron, ccxt), dann Failover bauen (siehe Gate-Discipline).

---

## 6. Nächste Schritte

### Sofort

- [x] `STRATEGY_THESIS.md` anlegen (dieses Dokument)
- [x] Stage A + B2 falsifiziert dokumentieren (`938ec8ce`, `366957a0`)
- [x] Stage H2 Vol-Breakout getestet — **Szenario 3** (reine Preis-Action abgeschlossen)
- [x] M2-Reißbrett (`H1_M2_EVENT_DRIVEN_SPEC.md`) + Skeleton
- [x] M2 Synthetic-Injection Audit lokal — PASS
- [x] `published_at` + `detection_lag` Scraper-Fix lokal (schema v1.3) — **Deploy nach Gate-Close** → [`V13_DEPLOY_RUNBOOK.md`](V13_DEPLOY_RUNBOOK.md)
- [ ] **Post-Gate v1.3:** G1-Snapshot archiviert · `make news-agent-test` auf Hetzner · Logrotate-Template · Watchdog OK
- [ ] Tag-7 `--lag-report` (§5.1.1/§5.1.3) — Verdict + `lag_coverage`/`coverage_by_source` vor Median
- [ ] Post-Gate: Polling-Epoche (5 min) prüfen **bevor** M2-Parameter — Spec §11
- [ ] Optional: 1h-Sanity nur wenn H₁-Brutto auch ≈ 0

### Mittelfristig (nach G1-PASS)

- [ ] Gap-Cron + `ccxt` in `requirements.txt` committen, dann Fehlertaxonomie messen
- [ ] Shadow Evaluator co-located — nur mit `SHADOW_EVAL_G1_PASS`
- [ ] Stage B1 (Sentiment-Filter) **nur** auf validiertem Base-Signal

### Langfristig

- [ ] 3–5 orthogonale Tests ohne Brutto-Alpha → Fundamentalansatz neu bewerten

---

## 7. Changelog

| Datum | Eintrag |
|-------|---------|
| 2026-09-01 | H₁ M0/M1 Methodik-Test — M0 PASS; M1 Oracle-Decke dokumentiert |
| 2026-09-01 | Stage A 15m Long-Dip falsifiziert (`938ec8ce`) |
| 2026-09-01 | Stage B2 15m Short-Momentum falsifiziert (`366957a0`) |
| 2026-09-01 | Dokument angelegt — H₀ Gate LIVE auf Hetzner (`c8755c2e`) |
| 2026-09-02 | v1.3 Deploy-Runbook (`V13_DEPLOY_RUNBOOK.md`) — post Gate-Close only |

---

## Siehe auch

- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, n≥50
- [`docs/NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — Feed-Qualität vs. Scheduler-Gate
- [`results/results_stage_a.csv`](../results/results_stage_a.csv)
- [`results/results_stage_b2_momentum.csv`](../results/results_stage_b2_momentum.csv)
- [`results/results_stage_h2_vol_breakout.csv`](../results/results_stage_h2_vol_breakout.csv)
