# Stage M2a — Funding Rate Squeeze (Vollhistorie-Präreg)

**Status:** FROZEN + **Amendment A1** (2026-09-02, vor erstem PnL)  
**Parent:** [`STRATEGY_THESIS.md`](STRATEGY_THESIS.md) §2.4 · [`H1_M2_EVENT_DRIVEN_SPEC.md`](H1_M2_EVENT_DRIVEN_SPEC.md) §5  
**Skripte:** [`scripts/backtest_m2a_funding_squeeze.py`](../scripts/backtest_m2a_funding_squeeze.py) · [`scripts/m2a_config.py`](../scripts/m2a_config.py) · [`scripts/m2a_funding_feasibility.py`](../scripts/m2a_funding_feasibility.py)

---

## 0. Ausgangslage

| Lauf | Fenster | Urteil |
|------|---------|--------|
| Pilot (365d) | 2025-09 … 2026-09 | **NOT TESTABLE** — keine Prereg-Events; Skalierung API-verifiziert |
| Feasibility | Funding only 2019-09 … 2026-09 | **103** unabhängige Episoden (≥ 0,10 % / 8h) → OHLCV-Abruf gerechtfertigt |

Dieses Dokument friert die Methodik für den **Vollhistorie-Lauf** ein. Änderungen nur per Amendment mit neuem Freeze-Datum.

---

## 1. Hypothese & Trigger

Extreme Perpetual-Funding-Rates (übermäßiger Hebel) tendieren zu Squeeze/Gegenbewegung.

| Trigger | Aktion |
|---------|--------|
| `funding_rate > +θ` | SHORT |
| `funding_rate < −θ` | LONG |

**Prereg-Grid (deskriptiv, alle θ):** `θ ∈ {0,05 %, 0,10 %, 0,15 %}` · `k_tp` · `k_sl` · 27 Zellen × 2 Assets.

**Primär-Verdict (Amendment A1):** nur **`θ_primary = 0,05 %`** (0,0005). θ ∈ {0,10 %, 0,15 %} = sekundär / historisch (OOS bei 0,10 % praktisch leer).

**Datenfenster:** maximale zusammenhängende Binance-Perp-Historie ab **2019-09-01**.

### Amendment A1 — Primär-θ 0,10 % → 0,05 % (vor PnL)

| | |
|--|--|
| **Zeitpunkt** | 2026-09-02 — **kein OHLCV geladen, kein PnL gerechnet** |
| **Legitimation** | Studiendesign (Teststärke + Marktregime), kein HARKing — 0,05 % stand in der ursprünglichen Schwellentabelle |
| **Regime-Befund** | ≥ 0,10 %/8h: **102 Episoden** Sep 2019–Nov 2023, danach **1** (ETH). Extrem-Funding ist post-2023 weitgehend verschwunden (Arbitrage-Kapitalisierung) |
| **Lebende Frage** | θ=0,05 %: **33 OOS-Episoden** (BTC 16, ETH 17) nach Split 2023-11-13 — beschreibt Zustände, die es noch gibt |
| **θ=0,10 %** | OOS NOT TESTABLE; In-Sample wäre Archäologie (2020/21-Hausse), kein Primär-Verdict |

---

## 1b. MDE-Vorprüfung (vor OHLCV)

Gleiche Formel wie M2 (`min_detectable_effect_bps`):  
`MDE = (z_(1−α) + z_0.80) · σ_ref / √n_episodes` mit `σ_ref = 75 bps`, `α = 0.05`, `n = 33` OOS @ θ=0,05 %.

| n OOS | MDE (bps) | Informative (< 80 bps)? |
|-------|-----------|------------------------|
| 33 kombiniert | **~32** | Ja |
| 16 BTC | ~47 | Ja |
| 17 ETH | ~45 | Ja |

Artefakt: [`results/m2a_mde_prereg.json`](../results/m2a_mde_prereg.json) · Skript: [`scripts/m2a_mde_prereg.py`](../scripts/m2a_mde_prereg.py)

---

## 2. Inference-Einheit: Episoden, nicht Trades

**Problem:** Mehrere 15m-Trades innerhalb eines Squeeze-Laufs sind stark korreliert. Signifikanz auf Trade-Ebene bläht n auf (analog überlappende Positionen in [`PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) → `PAPER_MAX_OPEN_POSITIONS = 1`).

**Freeze (vor Lauf):**

| Regel | Wert |
|-------|------|
| **Max. Trades pro Episode** | **1** — erster gültiger Entry-Bar pro Funding-Episode |
| **Episode-Definition** | Zusammenhängende 8h-Funding-Slots mit `\|fr\| ≥ θ` (ein Squeeze-Lauf = 1 Episode) |
| **Primäre Statistik** | **Episoden-Mittelwerte** `mean(net_pnl_episode)` |
| **Standardfehler** | **Geclustert:** `SE = std(episode_means) / sqrt(n_episodes)` |
| **Bericht** | Trade-Count nur deskriptiv; **Verdict auf Episode-n** |

Referenzimplementierung: `assign_funding_episodes()` + `metrics_from_episodes()` in [`scripts/backtest_metrics.py`](../scripts/backtest_metrics.py).

---

## 3. Kosten — periodenabhängig

`FRICTION_BPS = 19` gilt für **heutige** Gebühren/Spreads. 2019–2021: breitere Perp-Spreads, höhere effektive Round-Trip-Kosten. Extrem-Funding häuft in dieser Phase → 19 bps wäre **optimistisch** dort.

**Primär-Lauf (eingefroren):**

| Zeitraum | Round-Trip | Dezimal |
|----------|------------|---------|
| 2019-09-01 … 2021-12-31 | **35 bps** | `0.0035` |
| ab 2022-01-01 | **19 bps** | `0.0019` |

**Sensitivität (Pflicht-Report, nicht Primär-Verdict):**

| Szenario | Round-Trip |
|----------|------------|
| Uniform low | 19 bps gesamte Historie |
| Uniform high | 35 bps gesamte Historie |

**Interpretation:** Effekt, der bei 19 bps knapp positiv ist und bei 35 bps verschwindet → **kein Befund**. Ergebnisse in der Early-Phase sind bei Uniform-19 bps **Obergrenzen** (optimistisch).

Konstanten: [`scripts/m2a_config.py`](../scripts/m2a_config.py) → `friction_for_timestamp()`.

---

## 4. Out-of-Sample-Split (chronologisch 60/40)

Analog M2 §5 — **Schnittdatum vor erstem Lauf festgelegt**, kein Shuffle.

| Set | Zeitraum | Verwendung |
|-----|----------|------------|
| **Train / In-Sample** | 2019-09-01 … **Split** | Deskriptiv / Robustheits-Scan (Grid fest, kein Nachoptimieren) |
| **OOS Test** | **Split** … 2026-09-02 | **Einmalige** finale Bewertung |

**Eingefrorener Split (60 % Kalenderzeit):**

```text
PERP_START   = 2019-09-01T00:00:00Z
PREREG_END   = 2026-09-02T00:00:00Z
OOS_SPLIT_TS = 2023-11-13T19:12:00Z   # PERP_START + 60% × (PREREG_END − PERP_START)
```

**Pflicht vor Lauf:** Episodenzählung je Hälfte — [`results/m2a_funding_feasibility.json`](../results/m2a_funding_feasibility.json) Feld `episodes_by_threshold_and_split`.

**Befund (Funding-only, Freeze 2026-09-02):** Bei θ=0,10 % liegen **43/43 BTC-** und **59/60 ETH-Episoden** in Train; OOS 40 % hat **0 BTC / 1 ETH** Episode. Voller OHLCV-Lauf liefert für die **Primär-Schwelle 0,10 % kein gültiges OOS** — nur In-Sample oder niedrigere θ (0,05 %) sind OOS-besetzt.

| Mindestbesetzung | Wert |
|------------------|------|
| Episoden gesamt (Feasibility) | ≥ 30 (adequate) |
| Episoden **OOS 40 %** | ≥ **15** pro Asset (sonst OOS NOT TESTABLE) |
| Episoden pro Grid-Zelle OOS | ≥ **10** für Szenario-Klassifikation |

---

## 5. Szenario-Klassifikation (OOS, Episode-basiert, θ_primary = 0,05 %)

Auf **OOS 40 %**, periodenabhängige Kosten, **Episode-Mittelwerte**, **nur θ = 0,0005**:

| Szenario | Kriterium |
|----------|-----------|
| **1 PASS** | `E[PnL_net_episode] ≥ +10 bps` · `n_episodes_oos ≥ 15` · `sharpe_episode ≥ 0.5` |
| **2 Neutral** | `E[PnL_net_episode]` zwischen −5 und +10 bps |
| **3 Falsified** | `E[PnL_net_episode] < −5 bps` |
| **NOT TESTABLE** | `n_episodes_oos < 15` bei **θ_primary** |

θ ∈ {0,10 %, 0,15 %}: nur Tabelle, kein Primär-Verdict (OOS-Sparse).

---

## 8. Ergebnis Vollhistorie-Lauf (2026-09-02)

**Amendment A1 eingehalten** — θ_primary = 0,05 %, vor Lauf eingefroren.

| Asset | OOS Episoden @0,05 % | Beste OOS E[PnL_episode] | Verdict |
|-------|----------------------|--------------------------|---------|
| BTC | 16 | **−21,9 bps** | Scenario 3 |
| ETH | 17 | **−20,4 bps** | Scenario 3 |

Perioden-Reibung (35/19 bps), 1 Trade/Episode, Split 2023-11-13.  
Artefakt: [`results/stage_m2a_results.csv`](../results/stage_m2a_results.csv) (Grid `full-history`).

**Primärpfad:** M2 (News) — einziger verbleibender exogener Katalysator.

Sensitivitätsläufe (Uniform 19/35 bps) werden mitgeführt, ändern den Primär-Verdict nicht.

---

## 6. Daten & Validierung

1. Funding: volle Historie (`m2a_funding_feasibility.py` / Cache ab 2019).
2. OHLCV: 15m-Klines, zusammenhängend, gleiches Fenster.
3. Skalierung: Cache vs. API (Ratio ≈ 1,0) — bereits im Pilot verifiziert; Stichprobe bei Voll-Download wiederholen.
4. Kein Fenster- oder Episoden-Cherry-Picking.

---

## 7. Changelog

| Datum | Eintrag |
|-------|---------|
| 2026-09-02 | **Amendment A1:** Primär-θ → 0,05 % (vor PnL); MDE ~32 bps @ n=33 OOS |
| 2026-09-02 | Präreg eingefroren: Episoden-Inference, periodenabhängige Kosten, OOS-Split 2023-11-13T19:12:00Z |
| 2026-09-02 | Pilot 365d: NOT TESTABLE; Feasibility 103 Episoden |
