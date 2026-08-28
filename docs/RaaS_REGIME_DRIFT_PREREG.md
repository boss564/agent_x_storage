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

### Pre-Reg-Patch-Matrix (vertikale Upgrades v1)

| Agent | Upgrade | Funktion |
|-------|---------|----------|
| **A4** | Autokorrelations-Monitor | Lag-1 ρ auf `r2_cubed` (überlappende 3er-Blöcke), `n_eff`, `is_iid_violation` wenn `n_eff/n < 0.5` |
| **A7** | i.i.d.-Override-Engine | Bei >2× + i.i.d.-Verletzung + `ρ > 0.3`: `DRIFT_IID_UNRELIABLE`, **`regime_flag` bleibt** (1/2), nur `allow_amendment=False` |
| **A8** | Sperrklinke | Advisory nur wenn `allow_amendment=True`; sonst `PARAMETER_UNCHANGED` + Audit-Grund |

Audit-Feld `pre_reg_intervention` (A9) dokumentiert AMENDMENT_BLOCKED gemäß Line 74.

### Adaptive Stats v2 (`raas_regime_swarm_v2`)

| Patch | Agent | Verhalten |
|-------|-------|-----------|
| Adaptives Cooling | **A1** | Unreliable: 2 Zyklen `DRIFT_IID_UNRELIABLE` → `WARN_ONLY`; Real: 5× `HIGH_VOL_*` → `ADAPT` |
| Bonferroni | **A7** | `α_eff = 0.05 / m` (m=4 Features); IID-Artefakt → `DRIFT_IID_UNRELIABLE`, flag=1, Amendment gesperrt |
| Dynamisches Fenster | **A4** | ρ>0.4 → Fenster verdoppeln (max 60), sonst −5 zur Basis 15 |
| Soft-Adapt | **A8** | Unreliable: +3,3 %/Zyklus (`SOFT_ADAPT_STEP=0.10` × 0,33; cap 30 % von Ziel 1,5); Full bei bestätigtem `ADAPT` |
| Stuck-Telemetrie | **A9** | >4 h `DRIFT_IID_UNRELIABLE` → `REVIEW_REQUIRED` |

Inter-Agent-Payload: `swarm_message` im Cycle-Output (classification, window_metadata, orchestrator_decision, strategy_state, compliance).

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

## Multiplizität — `p_min` / Bonferroni über m = 4 korrelierte Merkmale

**Entscheidungsvariable (Schwarm):** A7 wertet alle m = 4 Features aus (`log_return`, `abs_return`, `down_move`, `rolling_vol`).

Das Minimum von m p-Werten ist unter H₀ nicht α-verteilt. Bei unabhängigen Tests gilt:

\[
P(\min_i p_i < \alpha \mid H_0) = 1 - (1-\alpha)^m
\]

Die Merkmale stammen aus derselben Preisreihe und sind **positiv korreliert** — die effektive Rate liegt zwischen Einzeltest und Unabhängigkeits-Obergrenze.

### Zwei Planungsstände (v1 vs v2)

| | **v1** (historisch, bis 2026-08-28) | **v2** (geltend ab 2026-08-28, Commit `c3b26645`) |
|---|--------------------------------------|---------------------------------------------------|
| Schema | `raas_regime_swarm_v1` | `raas_regime_swarm_v2` |
| Screen-Regel | `p_min < 0.05` (unkorrigiert) | **Bonferroni:** ∃ Feature mit `p < α_eff`, `α_eff = 0.05/m = **0.0125**` |
| Einzeltest (m=1) | 5,0 % | 1,25 % (= α_eff) |
| Obergrenze unabhängig (m=4) | 1 − 0,95⁴ ≈ **18,5 %** | 1 − (1 − 0,0125)⁴ ≈ **4,9 %** |
| **Planwert Screen/Zyklus** (Korrelation, Annahme) | **~10 %** | **~3 %** |
| bei 24 Zyklen/Tag | **~2–3** Screen-Ereignisse/Tag | **~0,7** (~1/Tag) |
| Cooling bestätigt | 3× `regime_flag ≥ 2` (Run-Length) | A1 adaptiv: 2× Unreliable / 5× Real-Drift |
| `r₂³`-Näherung (bestätigt, i.i.d.) | bei r₂≈10 % → **~0,1 %** (~1/1.000 Zyklen) | niedriger (Bonferroni dämpft Screen); separat in 30-Tage-Eval |
| **Soft-Adapt (A8)** | `SOFT_ADAPT_STEP` = **0,05** (+1,67 %/Zyklus IID-Pfad) | `SOFT_ADAPT_STEP` = **0,10** (+3,3 %/Zyklus IID-Pfad); geändert 2026-08-28 · Gap-Audit Schrittweite (`68edfe9b`) |

**v1:** Keine Bonferroni-Korrektur — bewusst empfindlich; Cooling-Off als Run-Length-Filter.

**v2:** Bonferroni in A7 — gleiche Pre-Reg-Philosophie (Alarm bleibt bei `DRIFT_IID_UNRELIABLE`, nur Amendment gesperrt), aber **weniger Screen-Fehlalarme**.

### 30-Tage-Eval & >2×-Regel

Diese Zahlen sind **vorab festgehalten** (Pre-Reg), nicht nachträglich rekonstruiert.

- **Vergleichsbasis:** immer die Zeile der **laufenden Schema-Version** (`swarm_message` / Report-`schema`).
- **>2×-Amendment:** beobachtete Rate vs. **v2-Planwert** (ab 2026-08-28); Abweichung >2× → Pre-Reg-Amendment, keine stille Schwellenanpassung.
- **Versionswechsel v1→v2** ist **kein** >2×-Datenbefund (erwartete Screen-Rate fällt von ~10 % auf ~3 %) — dokumentierter Code-Stand, nicht Kalibrierung an Livedaten.
- **`SOFT_ADAPT_STEP` v1→v2** (0,05 → 0,10, 2026-08-28): ebenfalls **kein** Datenbefund — dokumentierte Spec-Korrektur (Gap-Audit); Adaptionsgeschwindigkeit auf IID-Pfad verdoppelt sich von +1,67 % auf +3,3 %/Zyklus.
- **Ausnahme i.i.d.:** Abweichung allein aus `r₂³`-Näherung (überlappende Fenster / Autokorrelation) löst kein Amendment aus.

**Hinweis:** Permutation-KS pro Feature nutzt `seed=42`; Unabhängigkeits-Obergrenze bleibt konservative Worst-Case-Schranke.

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

**α = 0.01** (Legacy `regime_drift.assess_price_series`) · Schwarm-A7 v2: Bonferroni `α_eff = KS_SCREEN_ALPHA/m` (siehe Multiplizität).

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
