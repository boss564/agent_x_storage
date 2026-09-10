# H₁ — News-Primär-Trigger: Methodik-Präreg (M0 / M1 / M2)

**Status:** PREREG (vor erstem Lauf)  
**Datum:** 2026-09-01  
**Parent:** [`STRATEGY_THESIS.md`](STRATEGY_THESIS.md) · [`NEWS_AGENT.md`](NEWS_AGENT.md)  
**Blocker:** Kein Hetzner-Deploy neuer Trading-Logik vor Gate-Close (`NEWS_24H_SCHEDULER_GATE.md`)

---

## 0. Datenlage (ehrlich)

| Datenquelle | Verfügbarkeit | Zeitraum |
|-------------|---------------|----------|
| 15m OHLCV (BTC/ETH) | ✅ lokal via `ccxt` + Cache | ~365 Tage |
| `data/news_scores.jsonl` (Live) | ⚠️ nur ab Epoch (~2026-09-01) | **< 1 Tag** |
| Historische News + Sentiment | ❌ nicht im Repo | — |

**Konsequenz:** Ein **Performance-Backtest** „News → Trade“ über 12 Monate ist **jetzt unmöglich**.  
Wir testen zuerst die **Methodik** und eine **Oracle-Decke**, nicht die reale News-Alpha-Hypothese.

---

## 1. Paradigmenwechsel nach A / B2 / H2

Preis-Action allein ist falsifiziert. H₁ invertiert die Rollen:

```text
Alt (Stage B — verworfen):  Dip (Preis) → News-Filter → Trade
Neu (H₁):                   News-Event (exogen) → Entry-Fenster → Preis als Ausführung
```

**M0/M1** nutzen Stage-A-Dips nur als **Trade-Pool mit bekannter Brutto-Verteilung** (E[gross] ≈ 0), nicht als Primär-Trigger.

---

## 2. Drei Stufen

| Stufe | Name | Daten | Frage |
|-------|------|-------|-------|
| **M0** | Null-Injection | Synthetisches Sentiment (RNG) | Halluziniert ein Filter Alpha aus Rauschen? |
| **M1** | Oracle-Decke | Lookahead auf `gross_pnl` (Cheating) | Gibt es überhaupt genug >+30 bps Trades, die ein perfekter Filter retten könnte? |
| **M2** | Live-Replay | `news_scores.jsonl` akkumuliert | Liefert **echtes** Sentiment Brutto-Alpha? (≥ 3–6 Monate Daten) |

**Reihenfolge:** M0 → M1 → (Gate PASS + Fenster W) → M2.  
Option 2 (externe News-Archive) nur wenn M1 zeigt, dass die **Decke** hoch genug ist.

---

## 3. M0 — Null-Injection (Methodik-Test)

### 3.1 Setup

- **Trade-Pool:** Alle Stage-A Long-Dip-Trades pro Symbol, kanonische Parameter  
  `k_entry=2.0`, `k_tp=1.5`, `k_sl=1.0` (oder Grid-Best mit `trades ≥ 20` — im Skript dokumentiert).
- **Synthetic label:** Pro Trade `sentiment ∈ {+1, −1}` mit P=0,5, unabhängig von `gross_pnl`.
- **Filter:** Trade nur wenn `sentiment == +1` (Long-Konvention).
- **Execution:** Unverändert — pessimistic intrabar, non-overlap, 19 bps (aus Parent-Skript).

### 3.2 Monte-Carlo

- **N = 500** Seeds (vorab fest).
- Pro Seed: synthetische Labels → gefilterte Metriken `E[PnL_gross]`, `E[PnL_net]`, `n_trades`.

### 3.3 Erwartung unter Null

```text
E[E[PnL]_filtered] = E[E[PnL]_unfiltered]     (≈ 0 gross, ≈ −19 bps net)
Var durch Halbierung der Stichprobe steigt, aber Mean bleibt zentriert.
```

### 3.4 Erfolgskriterien M0

| Outcome | Kriterium | Bedeutung |
|---------|-----------|-----------|
| **PASS** | ≥ 95% der Seeds: \|Δ E[PnL_net]\| vs. unfiltered < 5 bps | Methodik erzeugt kein Schein-Alpha |
| **FAIL** | > 5% Seeds mit \|Δ\| ≥ 5 bps bei gleichem Pool | Implementations-Bug oder Selection-Bias |

M0 beweist **kein** News-Edge — nur dass der Filter-Pfad sauber ist.

---

## 4. M1 — Oracle-Decke (Cheating Upper Bound)

### 4.1 Setup

- Gleicher Trade-Pool wie M0.
- **Oracle label:** `sentiment = +1` iff `gross_pnl ≥ +0.003` (+30 bps), sonst `−1`.
- Zusätzlich Variante **Top-k%** nach `gross_pnl` (k ∈ {10, 20, 30}).

### 4.2 Fragen

1. Wie viel % der Dip-Trades haben `gross_pnl ≥ +30 bps`?
2. Was ist `E[PnL_gross]` und `E[PnL_net]` auf dieser perfekt gefilterten Teilmenge?
3. Reicht die Teilmenge (`n ≥ 30`/Jahr) für statistische Aussagekraft?

### 4.3 Entscheidungsregel M1

| M1-Ergebnis | Konsequenz |
|-------------|------------|
| Oracle `E[PnL_net] ≥ +10 bps` **und** `n_filtered ≥ 30` | Option 2 (echte News sammeln) **lohnt sich** |
| Oracle `E[PnL_gross] < +10 bps` oder `n_filtered < 10` | Dip-Pool hat **keine** rettbare Tail — News auf Dips sinnlos; H₁ = **frisches exogenes Event**, nicht Dip-Filter |
| Oracle gross positiv, net negativ | Kosten dominieren — Entry/Exit oder Timeframe ändern, nicht Sentiment |

**Kern:** Wenn selbst der **perfekte** Filter auf dem Dip-Pool kein Netto-Alpha liefert, ist „News filtert Dips“ tot. H₁ muss dann **News-first** (Event → Entry), nicht Filter-on-falsified-base.

---

## 5. M2 — Live-Replay (später)

**Vollständige Spezifikation:** [`H1_M2_EVENT_DRIVEN_SPEC.md`](H1_M2_EVENT_DRIVEN_SPEC.md)  
**Skeleton (Typen + Alignment, kein Live-Run):** [`scripts/backtest_h1_news_m2_skeleton.py`](../scripts/backtest_h1_news_m2_skeleton.py)

### Voraussetzungen

- G1-PASS (`NEWS_24H_SCHEDULER_GATE.md`)
- Gate-Close `2026-09-02T12:00:01Z` vergangen
- `news_scores.jsonl` ≥ 90 Tage, ≥ 200 gated Events, ≥ 80 BTC/ETH
- Preis-Gap-Cron aktiv

### M2-Kern (Kurzfassung)

```text
News-Event (item_id, t₀=ingest, sentiment_score, target_assets)
  → Gate: |score| ≥ 0.30, Asset ∈ {BTC, ETH}, **`schema == news_agent_multi/v1.3`**
  → Window: [t₀ + 1min, t₀ + 15min]
  → Direction: sign(sentiment_score)
  → TP/SL/Time-Exit wie A/B2/H2 · 19 bps
  → Metriken: Precision-Recall auf +30bps-Tail ZUERST, dann E[PnL]
```

Kein Live-Replay vor Daten-Schwelle. Synthetic-Injection (§6.2) lokal erlaubt.

---

## 6. Skript & Artefakte

| Artefakt | Pfad |
|----------|------|
| M0/M1 Runner | [`scripts/backtest_h1_news_null_injection.py`](../scripts/backtest_h1_news_null_injection.py) |
| Trade-Pool Export | `results/h1_trade_pool_stage_a.csv` |
| M0 MC Summary | `results/h1_m0_null_injection_summary.csv` |
| M1 Oracle Summary | `results/h1_m1_oracle_ceiling.csv` |

---

## 7. Was wir **nicht** tun

1. Synthetische Labels an **Outcomes koppeln** (außer M1-Oracle — explizit als Cheating markiert).
2. M0-Ergebnis als News-Performance verkaufen.
3. H₁-Deploy auf Hetzner vor Gate-Close.
4. Stage-B „Sentiment filtert Dips“ wiederbeleben — Base-Signal ist falsifiziert.

---

## 8. Changelog

| Datum | Eintrag |
|-------|---------|
| 2026-09-01 | M0 PASS (500 seeds, 100% within ±5 bps); M1 Oracle n=341, E[net]=+27 bps |
