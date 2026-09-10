# Agent-X — Strategy Thesis & Alpha Architecture

**Status:** ACTIVE (iterative hypothesis testing)  
**Last Updated:** 2026-09-02 (Post-Gate v1.3 verification — deploy pending Hetzner `sudo`)  
**Method:** Backtest-driven falsification (Stage A / B2 / H2 / M2a / M2b) · M2 live replay blocked ≥90d · prove-it-first  
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
| **Gate-Close** | `2026-09-02T12:00:01.615076Z` — **abgelaufen**; v1.3-Deploy auf Hetzner (Phase A) ausstehend |

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

### 2.4 Stage M2a — Funding Rate Squeeze (Perp-Hebel-Überhang)

**Regime-Beobachtung (Funding-only, unabhängig vom Strategie-Urteil):** Extremes Funding (≥ **0,10 % / 8h**) Sep 2019–Nov 2023: **102 Episoden** (BTC 43, ETH 59). OOS-Hälfte (ab 2023-11-13): **1** Episode (ETH). Post-2023 praktisch verschwunden — Basis-Arbitrage räumt Prämie ab, bevor sie 0,10 % erreicht.

| | |
|--|--|
| **Hypothese** | Funding-Extrem → Squeeze/Gegenbewegung |
| **Amendment A1 (vor PnL)** | **Primär-θ = 0,05 %** — lebende Frage, 33 OOS-Episoden; 0,10 % = historisch/OOS-leer |
| **Pilot 365d** | NOT TESTABLE @ 0,10 %; Skalierung ratio **1,0** |
| **MDE OOS (n=33, σ=75 bps)** | **~32 bps** (< 80 bps → informativ) |
| **Präreg** | [`M2A_FUNDING_SQUEEZE_PREREG.md`](M2A_FUNDING_SQUEEZE_PREREG.md) |
| **Vollhistorie-Lauf** | **SCENARIO 3 — Falsifiziert** @ θ=0,05 % OOS (BTC −21,9 bps · ETH −20,4 bps · n_oos 16/17) |

Artefakte: [`m2a_funding_feasibility.json`](../results/m2a_funding_feasibility.json) · [`m2a_mde_prereg.json`](../results/m2a_mde_prereg.json)

### 2.5 Stage M2b — 15m Volume-Explosion Breakout

| | |
|--|--|
| **Hypothese** | Plötzlicher Volumen-Spike (`volume > 5× median(96)`) + gerichtete Bewegung (`\|return\| > 1.5σ`) signalisiert institutionellen Einstieg (Smart Money) |
| **Skript** | [`scripts/backtest_m2_volume_breakout.py`](../scripts/backtest_m2_volume_breakout.py) |
| **Grid** | `k_vol ∈ {3, 5, 7}` · `k_entry ∈ {1.5, 2.0, 2.5}` · `k_tp/k_sl` wie A/B2 → **81 Kombinationen × 2 Assets = 162 Zellen** |
| **Kosten** | 19 bps BTC · 25 bps ETH (Round-Trip) |
| **E[PnL_net] Default** | −0,233% (BTC, n=545) · −0,278% (ETH, n=729) |
| **E[PnL_net] best cell** | −21,4 bps (BTC) · −23,3 bps (ETH) — alle Zellen negativ |
| **Sharpe/trade (Default BTC)** | −0,80 (korrigiert; keine Kerzen-Frequenz-Annualisierung) |
| **Szenario** | **3 — Falsifiziert** |
| **Commit** | `292765c7` |
| **Artefakt** | [`results/stage_m2b_results.csv`](../results/stage_m2b_results.csv) |

**Interpretation:** Volumen-Spikes auf 15m wirken als Retail-FOMO-/Mean-Reversion-Falle, nicht als Smart-Money-Einstieg. Brutto-Edge ≈ 0; Netto ≈ −Kosten.

### 2.6 Orthogonale Schlussfolgerung (Preis-/Struktur-Baselines abgeschlossen)

```text
Long nach 2σ-Dip:              E[R_gross] ≈ 0   — Stage A
Short nach 2σ-Dip:             E[R_gross] ≈ 0   — Stage B2
Vol-Kompression→Breakout:      E[R_gross] ≈ 0   — Stage H2
Funding-Squeeze (θ=0,05 % OOS): E[R_gross] ≈ 0   — Stage M2a (s.u.)
Volumen-Explosion:             E[R_gross] ≈ 0   — Stage M2b
Netto (alle Stages):           ≈ −Kosten        (Reibungsstrafe bei ausreichend n)
```

**M2a — präzise Lesart (erster vollständig sauberer Negativbefund):** OOS @ θ=0,05 %: BTC **−21,9 bps** netto, ETH **−20,4 bps** netto (Episode-Inferenz, periodenabhängige Kosten, MDE vorab bestanden). In der OOS-Hälfte (ab 2022) dominiert **19 bps** Reibung → **Brutto ≈ −3 bps** (BTC) bzw. **≈ −1 bps** (ETH). Der Funding-Wert trägt **keine Richtungsinformation**; der Verlust ist Reibung, nicht falsche Vorhersage — dieselbe Struktur wie Fenster W (H₀: `E[PnL_net] ≈ −Kosten` bei `E[R_gross] ≈ 0`).

**Fünf Baselines, fünfmal Scenario 3:** Kein Pech — das ist die erwartbare Antwort einfacher Preis-/Volumen-/Finanzierungsregeln auf liquide Majors im 15m-Takt. Unabhängig und methodisch sauber bestätigt; das wiegt schwerer als die meisten positiven Backtests.

### 2.7 Regime-Befunde (Primärprodukt, charter-konform)

**Statistische Frage:** Raten & Bruchpunkte — nicht Renditeverteilungen. Vorreg: **Zeitfenster** (exogener Schnitt, nicht Bruchpunktsuche). Urteilsschema: [`REGIME_DOCUMENTATION_PREREG.md`](REGIME_DOCUMENTATION_PREREG.md).

**Befund 1 — Extremes Funding (θ = 0,10 % / 8h, BTC+ETH, fixed-boundary):**

| | Pre (→ 2023-11-13) | Post (→ 2026-09-02) |
|--|---------------------|----------------------|
| Episoden | **102** (~50 mo) | **1** (~34 mo) |
| Rate | **2,02 / Monat** | **0,03 / Monat** |
| Erwartung post (konstante Rate) | — | **~68** |
| **Rate-Ratio post/pre** | — | **0,015** |

**Kopfzahl: Rate-Ratio 0,015** (68 erwartet, 1 beobachtet). Poisson-p nur Hilfskriterium (Clustering würde p vergrößern; Größenordnung des Kontrasts bleibt). Schnitt **exogen** aus M2a-60/40-Kalender — kein geschätzter Bruchpunkt.

**Verdict: `REGIME_SHIFT_CONFIRMED`** — struktureller Regime-Wechsel, gleicher methodischer Rang wie die fünf Strategie-Falsifikationen.

Artefakt: [`results/regime_funding_extreme_shift.json`](../results/regime_funding_extreme_shift.json)

**Charter:** `DEFENSIVE_CAUSAL_GROUNDING` — Messapparat (Episoden, Clusterung, WORM, Raten-Test) für Regime-Erkennung und Risikoschranken.

---

## 3. Strategische Einordnung — H₁ News & Mess-Infrastruktur

| Rolle | Inhalt |
|-------|--------|
| **Preis** | Ausführungsmedium, **nicht** Primär-Trigger |
| **Primärsignal (H₁)** | Exogen — News, Regime, strukturelle Katalysatoren |
| **News-Agent / M2** | **Letzter übriger** struktureller Testpfad — **nicht** automatisch aussichtsreichster |
| **Shadow Evaluator** | Strang B.1 — passiv, nach G1-PASS |

```text
E[R_priceOnly] ≤ 0  — empirisch bestätigt (A/B2/H2/M2a/M2b)
```

**Ehrliche M2-Prior-Einschätzung:** Derselbe Grund, der die fünf Baselines erledigt hat — liquide Instrumente, viele Teilnehmer, Signal eingepreist — gilt für Nachrichten analog: Wenn eine Meldung 15 min nach Veröffentlichung noch vorhersagbar bewegte, wäre es arbitriert. Tag-7-Lag-Erwartung ist **vorregistriert NO-GO** (`T_max = 15 min`, stündlicher Cron). M2 bleibt **real und billig nach Polling-Epoche** (Latenzfrage, Infrastruktur-Beweis) — aber Ausschluss der fünf anderen hebt den Prior **nicht**.

**Charter:** Fünf Alpha-Suchen gescheitert; Wertabschöpfung war nie die Projektrichtung (`DEFENSIVE_CAUSAL_GROUNDING`, `live_execution=false`). Die entstandene Infrastruktur ist der eigentliche Gewinn — H₀/Fenster W, Gates, Replay-Specs, Regime-Dokumentation.

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
| Funding Squeeze (M2a) | ❌ Falsifiziert @ θ=0,05 % OOS — Brutto ≈ 0, Reibung |
| Regime Change | → H₁ News/Regime-Trigger |
| Volume Surge | ❌ Falsifiziert (M2b) |
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
- [x] Stage M2b Volume-Breakout — **Szenario 3** (`292765c7`)
- [x] Stage M2a Funding-Squeeze 1. Versuch — **NOT TESTABLE** (Datenvalidierung + Machbarkeit 103 Episoden)
- [x] Stage M2a Vollhistorie — Scenario 3 @ θ=0,05 % OOS (2026-09-02)
- [x] M2-Reißbrett (`H1_M2_EVENT_DRIVEN_SPEC.md`) + Skeleton
- [x] M2 Synthetic-Injection Audit lokal — PASS
- [x] `published_at` + `detection_lag` Scraper-Fix (schema v1.3) — Code in `main`; **Live-JSONL noch v1.2 bis Hetzner-Deploy**
- [x] Gate-Close abgelaufen (`2026-09-02T12:00:01Z`) — Post-Gate-Fenster offen
- [ ] **Post-Gate v1.3 (Hetzner):** `sudo bash deploy/hetzner/phase1-m2-install.sh --phase-a` · G1-Snapshot · Cron `# AGENTX_M2_INGEST_STATUS` · Watchdog-Soak · Tag-7 `--lag-report` · dann Phase B
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
| 2026-09-02 | M2a Vollhistorie: Scenario 3 @ θ=0,05 % OOS; Brutto≈0-Lesart; Regime-Befund 102→1 @0,10 % |
| 2026-09-02 | Regime: Rate-Ratio 0,015 fixed-boundary; Zitierregel + estimated-breakpoint-Regel in Präreg |
| 2026-09-02 | M2a Amendment A1: Primär-θ → 0,05 % (vor PnL); Regime 102→1 Episoden @0,10 % |
| 2026-09-02 | Stage M2b Volume-Breakout falsifiziert (`292765c7`) |
| 2026-09-02 | Stage M2a Funding-Squeeze: NOT TESTABLE (365d); Skalierung verifiziert; Feasibility 103 Episoden ≥ 0,10 % |
| 2026-09-02 | Post-Gate verify: `git pull` OK · RSS tests 13/13 · local watchdog CRITICAL (stale v1.2 JSONL) · Hetzner deploy pending `sudo` |

---

## Siehe auch

- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, n≥50
- [`docs/NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — Feed-Qualität vs. Scheduler-Gate
- [`results/results_stage_a.csv`](../results/results_stage_a.csv)
- [`results/results_stage_b2_momentum.csv`](../results/results_stage_b2_momentum.csv)
- [`results/stage_m2b_results.csv`](../results/stage_m2b_results.csv)
- [`results/m2a_data_validation.json`](../results/m2a_data_validation.json)
- [`results/m2a_funding_feasibility.json`](../results/m2a_funding_feasibility.json)
- [`docs/REGIME_DOCUMENTATION_PREREG.md`](REGIME_DOCUMENTATION_PREREG.md)
- [`results/regime_funding_extreme_shift.json`](../results/regime_funding_extreme_shift.json)
