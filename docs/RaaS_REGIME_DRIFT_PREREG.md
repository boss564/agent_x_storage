# RaaS Regime Drift & Feature-Shift Detection — Pre-Reg v0 (Baustein 2)

**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · monitoring only · `live_execution=false`

## 9-Agent-Schwarm (A1–A9)

| ID | Agent | Sub-Schwarm | Funktion |
|----|-------|-------------|----------|
| **A1** | Orchestrator | Meta-Control | Takt, Pipeline A2→A9, Cooling-Off (3 Zyklen) |
| **A2** | Data-Ingestor | Daten | WORM `SIGNAL.mark_price` (Paper-Collect) |
| **A3** | Feature-Engineer | Daten | log/abs/down/rolling_vol + Z-Score vs Baseline |
| **A4** | Fenster-Manager | Statistik | Referenz 25 % · Current 25 % |
| **A5** | KS-Test-Agent | Statistik | Univariater KS pro Feature (m=4, Permutation, α_screen=0.05) |
| **A6** | Wasserstein-Agent | Statistik | W₁ pro Feature (mean/max) |
| **A7** | Drift-Klassifizierer | Statistik | RSI 0–100, `Regime_Flag` 0/1/2, Drift-Typ |
| **A8** | Strategie-Adapter | Entscheidung | **Nur Advisory** — keine Parameterausführung |
| **A9** | Audit- & Alerting | Compliance | Hash-gesichertes JSONL-Audit |

Implementierung: `prototypes/raas_paper_trading/regime_swarm/`

**Charter:** A8 schlägt Anpassungen nur als `advisory_only` vor. Kein Leverage-, kein Live-Order-Send.

## Offene Hypothese

> Können zwei-Stichproben-Tests (KS + 1D-Wasserstein) auf Tick-Features einen
> Regime-Wechsel **früh** signalisieren — bevor Envelope-Breaks die Auswertung dominieren?

**Nicht** behauptet: optimale Schwellen oder Trading-Anpassung. Nur **Drift-Warnung** im Audit-Log.

## Features (v0)

Aus WORM-`SIGNAL.mark_price` (Chronologie):

| Feature | Definition |
|---------|------------|
| `log_return_pct` | 100 × (pₜ − pₜ₋₁) / pₜ₋₁ |
| `abs_return_pct` | \|log_return_pct\| |
| `down_move_pct` | max(0, −log_return_pct) |
| `rolling_vol_pct` | pstdev der letzten 10 log_returns (Schwarm A3) |

Legacy-Modul `regime_drift.assess_price_series` testet nur die ersten drei Merkmale.
Der **9-Agent-Schwarm** (A5/A7) entscheidet über **m = 4** korrelierte KS-Tests.

Kein Live-Loop — offline auf `paper_trades.worm.jsonl` oder nach Collect-Ende.

## Multiplizität — `p_min` über korrelierte Merkmale (v0, dokumentiert)

**Entscheidungsvariable:** A7 nutzt `p_min = min(p₁,…,p_m)` über alle Features der Feature-Matrix (Schwarm: **m = 4**).
Es gibt **keine** Holm-/Bonferroni-Korrektur in v0 — bewusst, um den Drift-Detektor nicht zusätzlich zu dämpfen.
Stattdessen: **Cooling-Off** (3 aufeinanderfolgende Zyklen mit `regime_flag ≥ 2`) als Run-Length-Filter für bestätigte CRITICAL-Alerts.

**Problem:** Das Minimum von m p-Werten ist unter H₀ nicht α-verteilt. Bei unabhängigen Tests gilt:

\[
P(\min_i p_i < \alpha \mid H_0) = 1 - (1-\alpha)^m
\]

Die Merkmale stammen aus derselben Preisreihe (`log_return` → `abs_return`, `down_move`, `rolling_vol`) und sind **positiv korreliert**. Die effektive Rate liegt daher zwischen dem Einzeltest und der Unabhängigkeits-Obergrenze — nicht exakt ablesbar ohne Kalibrierlauf.

| Schwelle | Einzeltest (m=1, perfekte Korrelation) | Obergrenze unabhängig (m=4) |
|----------|----------------------------------------|-----------------------------|
| Screen `KS_SCREEN_ALPHA = 0.05` | 5,0 % | 1 − 0,95⁴ ≈ **18,5 %** |
| Kritisch `CRITICAL_ALPHA = 0.01` | 1,0 % | 1 − 0,99⁴ ≈ **3,9 %** |

**Planungshaltung v0 (vor Live-Monitor, unter H₀):**

| Größe | Formel / Annahme | Größenordnung |
|-------|------------------|---------------|
| Screen-Treffer (`p_min < 0.05`, mind. ein Feature) | zwischen 5 % und 18,5 %; **Planwert ~10 %** pro Zyklus (Korrelation) | bei 24 Zyklen/Tag ≈ **2–3** Screen-Ereignisse/Tag |
| `regime_flag = 1` (WARNING) | Zweig wenn nicht stabil und nicht kritisch (inkl. W₁-Gate) | Audit-Eintrag, kein bestätigter Stopp |
| `regime_flag = 2` (CRITICAL-Roh) | `p_min < 0.01` **und** `W₁_mean > 0.01` | effektiv **r₂ ≈ 3–8 %** pro Zyklus (unter H₀, abhängig von W₁-Null) |
| **Bestätigt** (`regime_flag_confirmed`, 3× flag≥2) | ≈ **r₂³** (i.i.d.-Näherung) | bei **r₂ = 10 %** → **0,1 %** ≈ **1 / 1.000 Zyklen** (~6 Wochen bei stündlichem Takt) |

Diese Zahlen sind **vorab festgehalten** (Pre-Reg), nicht nachträglich aus Läufen rekonstruiert. Nach 30-Tage-Collect: beobachtete Alarmrate vs. Tabelle berichten; Abweichung >2× löst Pre-Reg-Amendment aus, keine stille Schwellenanpassung.

**Hinweis:** Permutation-KS pro Feature nutzt denselben `seed=42`; die Tests sind damit nicht stochastisch unabhängig — die Unabhängigkeits-Obergrenze bleibt eine **konservative** Worst-Case-Schranke.

## Fenster

- **Referenz:** erste 25 % der Feature-Samples
- **Test:** letzte 25 %
- **Minimum:** 30 Samples pro Fenster (sonst `insufficient_features`)

## Tests

| Test | Entscheidung |
|------|----------------|
| KS (permutation, n=500, seed=42) | `drift_ks` wenn p < α |
| Wasserstein-1D | `drift_wasserstein` wenn D > 99%-Quantil der Null (within-run shuffle) |
| **Regime drift** | OR über Features |

**α = 0.01** (einseitig: beobachtetes KS ≥ permutiert) · Schwarm-A7 nutzt zusätzlich `p_min` über m Merkmale (siehe Multiplizität).

`definition_hash()` friert Parameter ein (`prototypes/raas_paper_trading/regime_drift.py`).

## Ausgabe

- Report: `exports/reports/regime_drift_latest.json`
- Audit: `logs/worm/regime_drift_audit.jsonl` → `DRIFT_WARN` bei Shift

```bash
make raas-regime-drift-monitor   # 9-Agent-Schwarm A1–A9
make raas-regime-drift-smoke     # Unit + synthetischer Shift
```

Audit-Schema (A9) entspricht dem Entwurf: `drift_summary`, `adaptive_action`, `alert_level`, `hash_checksum`.

## Abgrenzung

- Kein Kelly-Sizing (Baustein 3)
- Kein Cross-Venue (Baustein 4)
- `pair_manifest_hash` / `config_hash` bleiben für Fill-Provenance — Drift-Monitor segmentiert nicht über Manifest-Grenzen hinweg (pro WORM-Datei)

## 30-Tage-Eval

Nach Collect-Fenstern: Monitor pro Symbol · Drift-Warnungen mit `definition_hash` zitieren ·
Envelope-Hit-Rate nur innerhalb stabiler Regime-Fenster interpretieren (oder strata nach Drift-Flag).

Parent: `docs/RaaS_PAPER_DEPTH_INGEST_v0.md` · `docs/PAPER_TRADING_SETUP_v0.md`
