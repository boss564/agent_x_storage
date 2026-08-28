# Position Sizing — γ-Regime-Map & A7-Trigger (Strang C)

**Status:** REVIEW (2026-08-28) · **Dokument only** — keine Code-Änderung in diesem PR  
**Parent:** [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) (§4 freigegeben, PR #19 merged)  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `POSITION_SIZING_ENABLED=false` (Default bis Freigabe)

Parallel zum laufenden **Live-Shadow** (Strang A): dieses Doc legt die Kopplung A7→B0 fest, bevor γ im Code verdrahtet wird.

---

## 1. A7-Regime (Ist-Stand Code)

Quelle: `prototypes/raas_paper_trading/regime_swarm/agents.py` → `DriftClassifierAgent` (A7).

| `classified_regime` | `regime_flag` | Typische Bedingung |
|---------------------|---------------|-------------------|
| `STABLE` | 0 | Kein Bonferroni-Hit, niedrige standardisierte Drift |
| `STABLE_SIDEWAYS` | 0 | Drift unter Schwellen, aber leichte Abweichung |
| `LOW_LEVEL_DRIFT` | 1 | Bonferroni-Hit, moderate Drift (`concept_drift_suspected`) |
| `DRIFT_IID_UNRELIABLE` | 1 | Bonferroni + i.i.d.-Artefakt, `allow_amendment=false` |
| `HIGH_VOL_TREND` | 2 | Starke Drift, `allow_amendment=true` |
| `HIGH_VOL_TREND_BEARISH` | 2 | Wie oben, bearish Bias |

**Hinweis:** Es gibt kein Label `LOW_VOL_DRIFT` im A7-Code — Review-Tabelle nutzt die **tatsächlichen** Strings.

---

## 2. γ-Regime-Map (Vorschlag v0)

Fraktionaler Kelly-Faktor γ in B3 (`KellyCalculator.gamma`). Default ohne Map: **0,25** (PR #19).

| `classified_regime` | `regime_flag` | γ (Vorschlag) | Begründung |
|---------------------|---------------|---------------|------------|
| `STABLE` | 0 | 0,25 | Baseline — keine Drift-Signatur |
| `STABLE_SIDEWAYS` | 0 | 0,10 | Seitwärts / schwache Signifikanz → konservativ |
| `LOW_LEVEL_DRIFT` | 1 | 0,20 | Warn-Drift, kein Amendment → moderate Schranke |
| `DRIFT_IID_UNRELIABLE` | 1 | **0,00** | Safe Mode: Statistik nicht i.i.d.-tauglich (s. §6.1) |
| `HIGH_VOL_TREND` | 2 | 0,40 | Starker Trend, Amendment erlaubt — höhere *hypothetische* Kelly-Skalierung |
| `HIGH_VOL_TREND_BEARISH` | 2 | 0,35 | Wie Trend, leicht reduziert (Volatility-Bias) |
| *unbekannt / fehlend* | — | 0,25 | Fallback = PR-#19-Default, Audit-Feld `gamma_source: default` |

**Charter:** γ skaliert nur `computed_hypothetical_notional_eur` (Diagnose). Export bleibt **Schranke** (`max_notional_before_limit_breach_eur`), nie Empfehlung.

---

## 3. A7-Trigger (wann B0 laufen?)

Voraussetzungen **kumulativ**:

| # | Bedingung | Verhalten |
|---|-----------|-----------|
| T0 | `POSITION_SIZING_ENABLED=true` | sonst: kein B-Zyklus, kein Audit |
| T1 | Regime-Zyklus abgeschlossen (A7 `classified_regime` vorhanden) | B0 bekommt Regime-Kontext |
| T2 | **`regime_flag >= 1`** (Vorschlag) | Sizing nur bei Drift / Unreliable / Trend — nicht bei reinem `STABLE`/`STABLE_SIDEWAYS` mit flag 0 |
| T3 | Ledger ≥ **50** SELL-Roundtrips (B2 `min_trades`) | sonst: `INSUFFICIENT_HISTORY` (hard block, kein Fallback-p) |

### 3.1 Trigger-Alternativen (Review)

| Option | Trigger | Pro | Contra |
|--------|---------|-----|--------|
| **A (Vorschlag)** | `regime_flag >= 1` | Kopplung an A7 messbar; weniger Rauschen in Stable-Phasen | Kein Sizing in langen Stable-Runs (evtl. gewollt) |
| B | Jeder Leader-Zyklus | Maximale Observability | Viele `INSUFFICIENT_HISTORY`-Zeilen ohne Fills |
| C | Nur `regime_flag >= 2` | Nur Trend-Phasen | `LOW_LEVEL_DRIFT` unsichtbar für Sizing |

**Review-Default:** Option **A**, bis Shadow-Daten Gegenargument liefern.

### 3.2 `POSITION_SIZING_ENABLED=false`

Kein B0-Lauf. Regime-Daemon verhält sich wie heute (PR #19 Integration no-op).

---

## 4. Schnittstelle Regime (A7) → Sizing (B0)

**Phase 1 (PR #19):** Daemon ruft `run_sizing_if_enabled(symbol, mark_price)` ohne Regime-Kontext.

**Phase 2 (nach Freigabe dieses Docs):**

```text
RegimeSwarmOrchestrator.run_cycle()
  → drift_summary.classified_regime, regime_flag
  → PositionSizingOrchestrator.run_cycle(..., regime=..., regime_flag=...)
  → sizing_envelope an Report (kein Paper-WORM)
```

| Feld | Quelle | B0-Nutzung |
|------|--------|------------|
| `classified_regime` | A7 / `drift_summary` | γ-Lookup (§2) |
| `regime_flag` | A7 | Trigger T2 |
| `allow_amendment` | A7 | **nicht** für γ; optional Audit-Kontext only |
| `cycle_id` | A1/Swarm | Korrelation `SWARM-*` ↔ `SIZE-*` im Audit |

Keine Agenten-RPC nötig — **ein Prozess**, struct out → struct in (wie A8 heute).

---

## 5. Prometheus (optional, Phase 2)

| Metrik | Typ | Labels | Bedeutung |
|--------|-----|--------|-----------|
| `sizing_gamma_current` | Gauge | `regime` | Aktuell angewandtes γ |
| `sizing_gate_block_total` | Counter | `reason` (`LIMIT_EXCEEDED`, `INSUFFICIENT_HISTORY`) | Schranke / Historie |
| `sizing_regime_trigger_total` | Counter | `regime`, `regime_flag` | B0-Läufe nach Trigger T2 |

Kein Helm in Phase 2-PR nötig — Env reicht (`POSITION_SIZING_GAMMA_*` oder JSON-Map-Pfad).

---

## 6. Offene Review-Fragen

### 6.1 `DRIFT_IID_UNRELIABLE`: γ = 0,00 oder Hold?

| Option | Verhalten | Empfehlung |
|--------|-----------|------------|
| **Zero (Vorschlag)** | γ=0 → `hypothetical_notional=0`, Gate meist LIMIT_OK | Konsistent mit „Statistik nicht vertrauenswürdig“ |
| Hold last γ | γ bleibt vom vorherigen Regime | Risiko: veralteter Trend in Unreliable-Phase |

**Vorschlag:** **Zero** + Audit-Feld `gamma_source: iid_safe_mode`.

### 6.2 Trigger: flag 1 oder nur flag 2?

Siehe §3.1 — Default **flag ≥ 1**, damit `LOW_LEVEL_DRIFT` und `DRIFT_IID_UNRELIABLE` sichtbar bleiben (Safe Mode vs. moderate Schranke).

### 6.3 ConfigMap / Helm-Override für γ?

| Option | Beschreibung |
|--------|--------------|
| **Env-JSON** (Vorschlag v1) | `POSITION_SIZING_GAMMA_MAP='{"LOW_LEVEL_DRIFT":0.2,...}'` |
| Helm `config:` | Erst wenn Sizing in Cluster aktiv (≥50 Fills, Strang B) |

---

## 7. Freigabe-Kriterien (vor Implementierungs-PR)

- [ ] γ-Tabelle von Team abgenickt (§2)
- [ ] Trigger-Option A/B/C entschieden (§3.1)
- [ ] `DRIFT_IID_UNRELIABLE`-Policy entschieden (§6.1)
- [ ] Charter-Check: weiterhin nur Schranken-Export ([§4 Parent-Doc](POSITION_SIZING_SUBSWARM.md))

---

## 8. Nächste Schritte nach Merge dieses Docs

1. **Implementierungs-PR:** γ-Lookup + A7-Trigger in `PositionSizingOrchestrator` + Daemon-Übergabe  
2. **Strang B:** `POSITION_SIZING_ENABLED=true` im Shadow-Cluster (≥50 Fills)  
3. **Strang D:** Prometheus §5 + optional Helm-Map  

---

## Siehe auch

- [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md)
- [`docs/RaaS_REGIME_DRIFT_PREREG.md`](RaaS_REGIME_DRIFT_PREREG.md) — A7-Klassen
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — laufender Shadow
