# Agent-X — Strategy Thesis & Alpha Architecture

**Status:** ACTIVE (iterative hypothesis testing)  
**Last Updated:** 2026-09-01  
**Method:** Backtest-driven falsification (Stage A / B2) · prove-it-first  
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

### 2.3 Orthogonale Schlussfolgerung

```text
Long nach 2σ-Dip:   E[R_gross] ≈ 0   (keine Reversion)
Short nach 2σ-Dip:  E[R_gross] ≈ 0   (keine Fortsetzung)
Netto:              ≈ −19 bps        (reine Kostenstrafe)
```

**Erkenntnis:** Der 15m-Markt nach Volatilitäts-Injektionen verhält sich wie ein **effizientes Fair Game**. Weder Trend noch Reversion übersteigen 19 bps Reibung. Sentiment darf **nicht** nachträglich als Filter auf dieses Preis-Signal gesetzt werden (Overfitting auf Rauschen).

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

---

## 4. Offene Fragen (priorisiert)

### 4.1 Zeitrahmen-Skalierung (LOW)

- Gleiche Dip-Logik auf 1h/4h? Fee-Last relativ zu σ sinkt — aber A+B2 auf 15m deuten auf Brutto ≈ 0 unabhängig von Richtung.
- **Erwartung:** Ähnliches Fair-Game — kein Ersatz für orthogonale Tests.

### 4.2 Conditional Signals — News/Regime (MEDIUM, blockiert)

- Kann Sentiment die „richtigen“ Dips selektieren?
- **Blocker:** Basis-Brutto ≈ 0 → Filter müsste >+30 bps Moves isolieren ohne Gewinner zu überfiltrieren.
- **Regel:** Erst valides Base-Signal, dann Filter — nicht umgekehrt.

### 4.3 Alternative Entry-Logik (HIGH)

Orthogonal zur Dip-Physik — andere Marktineffizienz:

| Kandidat | Trigger-Idee |
|----------|----------------|
| Volatility Breakout | σ_spike > k × σ_rolling |
| Regime Change | Klassifikator stable → volatile |
| Volume Surge | Volume > k × Volume_rolling |
| Compression → Expansion | Range-Narrowing dann Break |

**Empfehlung:** Pfad 2 vor 1h-Skalierung und vor Sentiment-Filter.

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
- [ ] H₁-Architektur skizzieren: erster **exogener** News-Trigger (Reißbrett, kein Hetzner-Deploy vor Gate-Close)

### Kurzfristig

- [ ] **Pfad 2:** Neue Hypothese definieren + Backtest-Skript (z. B. Vol-Breakout) — gleiches Framework
- [ ] Optional: 1h-Sanity nur wenn Pfad 2 auch Brutto ≈ 0 → dann Mean-Reversion-Klasse endgültig zu

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
| 2026-09-01 | Stage A 15m Long-Dip falsifiziert (`938ec8ce`) |
| 2026-09-01 | Stage B2 15m Short-Momentum falsifiziert (`366957a0`) |
| 2026-09-01 | Dokument angelegt — H₀ Gate LIVE auf Hetzner (`c8755c2e`) |

---

## Siehe auch

- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, n≥50
- [`docs/NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — Feed-Qualität vs. Scheduler-Gate
- [`results/results_stage_a.csv`](../results/results_stage_a.csv)
- [`results/results_stage_b2_momentum.csv`](../results/results_stage_b2_momentum.csv)
