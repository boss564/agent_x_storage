# Regime Documentation — Präregistrierung (Raten & Bruchpunkte)

**Status:** FROZEN (2026-09-02)  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` — Marktstruktur & Regime, **keine** Wertabschöpfung  
**Parent:** [`STRATEGY_THESIS.md`](STRATEGY_THESIS.md) §2.7 · [`M2A_FUNDING_SQUEEZE_PREREG.md`](M2A_FUNDING_SQUEEZE_PREREG.md)

---

## 0. Zweck

Strategie-Tests fragen: *Renditeverteilung, MDE, Kosten.*  
Regime-Befunde fragen: ***Raten und Bruchpunkte.***

Diese Klasse hat **denselben methodischen Rang** wie Scenario-1/2/3-Falsifikationen — aber schlankere Statistik und **Vorregistrierung der Zeitfenster**, nicht der Handels-Schwellen.

---

## 1. Episoden-Definition (wiederverwendet)

| Element | Regel |
|---------|--------|
| Episode | Zusammenhängende Funding-Slots mit `\|fr\| ≥ θ` (8h-Cadence) |
| θ (deskriptiv) | Pro Befund **vor Lauf** benannt — z. B. 0,10 % für „extremes Funding" |
| Assets | BTCUSDT + ETHUSDT Perp (additiv, keine Doppelzählung) |
| Provenienz | Binance `fapi/v1/fundingRate` · WORM/JSON-Artefakt |

---

## 2. Bruchpunkt — fixed-boundary (exogen), nicht geschätzt

### 2.1 Regel (vor dem ersten Befund eingefroren)

Der Schnitt zwischen Pre- und Post-Fenster muss **exogen** sein: festgelegt **vor** dem Ratenvergleich und **ohne** Maximierung über Kandidatendaten im selben Datensatz.

| Modus | Gültigkeit des Poisson-p | Zitierpflicht |
|-------|--------------------------|---------------|
| **Fixed-boundary** (exogener Schnitt) | p ist ein **einzelner** vorgeplanter Test | Boundary-Quelle nennen |
| **Estimated-breakpoint** (Suche über Kandidaten) | p **nicht** ohne Korrektur (Mehrfachtest / Suchverfahren) | Separate Präreg + Korrektur **vor** Lauf |

**Warum das zählt:** Wer den Bruchpunkt über Kandidatendaten maximiert, findet zuverlässig überall Brüche — das p beschreibt dann ein **Suchverfahren**, nicht einen einzelnen Kontrast. Diese Regel jetzt festhalten ist billiger als sie später an drei Befunden nachzuziehen.

### 2.2 Begründung für Befund 1 — `OOS_SPLIT_TS`

`OOS_SPLIT_TS = 2023-11-13T19:12:00Z` stammt aus der **Strategiearbeit** (M2a/M2 §4: chronologischer **60/40-Kalenderschnitt**), **nicht** aus einer Bruchpunktsuche auf Funding-Episoden.

```text
OOS_SPLIT_TS = PERP_START + 60% × (PREREG_END − PERP_START)
```

Damit ist Befund 1 ein **fixed-boundary**-Test; das Poisson-p ist methodisch gültig als Hilfskriterium im Verdict-Baum (§4), weil die Grenze **von außen** kam.

**Referenz:** [`M2A_FUNDING_SQUEEZE_PREREG.md`](M2A_FUNDING_SQUEEZE_PREREG.md) §4 · [`scripts/m2a_config.py`](../scripts/m2a_config.py)

### 2.3 Zeitfenster (Vorreg, nicht Schwellen)

| Fenster | Grenzen (eingefroren) |
|---------|------------------------|
| **Pre** | `PERP_START` … `OOS_SPLIT_TS` |
| **Post** | `OOS_SPLIT_TS` … `PREREG_FREEZE` |

```text
PERP_START    = 2019-09-01T00:00:00Z
OOS_SPLIT_TS  = 2023-11-13T19:12:00Z   # exogen, s. §2.2
PREREG_FREEZE = 2026-09-02T00:00:00Z
```

Weitere Regime-Befunde: **neue** Split-Daten nur per Amendment. Geschätzte Bruchpunkte nur unter §2.1 rechte Spalte (eigene Präreg).

---

## 3. Statistik — Ratenvergleich + Poisson (Hilfskriterium)

### 3.1 Kopfzahl (zitieren): Rate-Ratio

**Primäre deskriptive Größe** — verteilungsunabhängig:

```text
rate_pre  = n_pre / T_pre
rate_post = n_post / T_post
expected_post = rate_pre × T_post
rate_ratio = rate_post / rate_pre
```

**Zitierregel:** In Abstracts, Thesis und Dashboards die **Rate-Ratio** (und ggf. *expected vs observed*) führen — **nicht** das p mit vielen Nullstellen.

### 3.2 Hilfskriterium: Poisson-p (Annahmen beachten)

**H₀:** Konstante Episodenrate λ über beide Fenster.

Unter H₀ (gleiche Rate) mit λ̂ = n_pre / T_pre: bedingter exakter Test —  
`count_post | (n_pre + n_post) ~ Binomial(total, T_post / (T_pre + T_post))`.

| Richtung | Hilfs-p | Rate-Ratio-Schwelle |
|----------|---------|---------------------|
| Abnahme (Kühlung) | p_lower = P(X ≤ n_post \| H₀) | **< 0,25** (= 1/4×) |
| Zunahme (Häufung) | p_upper = P(X ≥ n_post \| H₀) | **> 4,0** (= 4×) |

API: `rate_ratio_test(count_pre, exposure_pre, count_post, exposure_post)` →  
`decision` ∈ {`decrease`, `increase`, `no_change`}, plus `ratio`, `p_lower`, `p_upper`.  
Präreg-Verdict-Wrapper: `poisson_rate_test(pre_window, post_window)` → `REGIME_SHIFT_CONFIRMED` / `FLUCTUATION`.

**Schwellen-Begründung (0,25 / 4,0):** Eingefroren **2026-09-02** mit Klasseneinführung — **nicht** an Befund 1 (rate_ratio 0,015) kalibriert. Regel: **Faktor 4** Ratenänderung gilt als struktureller Bruch (reziprokes Paar 1/4 ↔ 4). Bei 0,015 entscheidet jede Schwelle < ~0,5 nichts; die Zahl trägt erst beim **zweiten** Kandidaten, wenn das Verhältnis näher an der Grenze liegt.

**Annahme:** unabhängige Ereignisse bei konstanter Rate. Funding-Episoden **clustern** → **Überdispersion** würde p vergrößern (s. §3.1 Zitierregel).

Implementierung: [`scripts/regime_rate_test.py`](../scripts/regime_rate_test.py)

---

## 4. Urteilsschema (Regime-Verdict-Baum)

| Verdict | Bedingung |
|---------|-----------|
| **REGIME_SHIFT_CONFIRMED** (Abnahme) | n_pre ≥ **30** · T_post ≥ **12** mo · **rate_ratio < 0,25** · p_lower **< 0,01** |
| **REGIME_SHIFT_CONFIRMED** (Zunahme) | n_pre ≥ **30** · T_post ≥ **12** mo · **rate_ratio > 4,0** · p_upper **< 0,01** |
| **FLUCTUATION** | Daten ausreichend, aber keine Richtung erfüllt Schwellen + Hilfs-p |
| **INSUFFICIENT_DATA** | n_pre < 30 oder T_post < 12 Monate |

Fixed-boundary in beiden Fällen (§2). Poisson nur Hilfskriterium.

**Zitierreihenfolge bei CONFIRMED:** (1) rate_ratio + Richtung, (2) n_pre / n_post / expected_post, (3) Verdict, (4) p nur mit Poisson-Hinweis — **nicht** p mit vielen Nullstellen.

**Interpretation:**

- `REGIME_SHIFT_CONFIRMED` ≠ Trading-Edge. Strukturelle Aussage über **Ereignishäufigkeit**.
- `FLUCTUATION` ≠ „kein Regime" — nur „unter dieser Vorreg nicht nachweisbar".
- Kein PASS/Neutral/Fail auf PnL — orthogonale Achse.

---

## 5. Erster Befund — Extremes Funding (θ = 0,10 %)

**Boundary:** fixed-boundary, `OOS_SPLIT_TS` exogen (§2.2).

| | Pre (→ Nov 2023) | Post (Nov 2023 →) |
|--|------------------|-------------------|
| Episoden | **102** | **1** |
| Monate | ~50,4 | ~33,6 |
| Rate | **2,02/mo** | **0,03/mo** |
| Erwartung post (konstante Rate) | — | **~68** |
| **Rate-Ratio post/pre** | — | **0,015** |
| Poisson p (Hilfskriterium) | — | ≪ 0,01 *(Unabhängigkeit angenommen)* |

**Kopfzahl:** **Rate-Ratio 0,015** (68 erwartet, 1 beobachtet).  
**Verdict: REGIME_SHIFT_CONFIRMED** — extremes Funding (≥0,10 %/8h) post-Split nicht als Flaute erklärbar.

Artefakt: [`results/regime_funding_extreme_shift.json`](../results/regime_funding_extreme_shift.json)  
Runner: [`scripts/run_regime_funding_shift.py`](../scripts/run_regime_funding_shift.py)

---

## 6. Abgrenzung zu Strategie-Stages

| | Strategie (A/B2/H2/M2a/M2b) | Regime-Dokumentation |
|--|------------------------------|----------------------|
| Frage | Ist E[PnL_net] > Kosten? | Hat sich die **Ereignisrate** geändert? |
| Statistik | Rendite, MDE, Episoden-PnL | Poisson, Raten, Bruchpunkt |
| Vorreg | θ, Grid, Kosten | **Zeitfenster**, θ_deskriptiv |
| Charter | Falsifikation erlaubt | **Primärprodukt** |

---

## 7. Changelog

| Datum | Eintrag |
|-------|---------|
| 2026-09-02 | Klasse eingeführt; erster Befund Funding ≥0,10 % REGIME_SHIFT_CONFIRMED |
| 2026-09-02 | Exakter bedingter Poisson-Test (Binomial); `rate_ratio_test` API |
