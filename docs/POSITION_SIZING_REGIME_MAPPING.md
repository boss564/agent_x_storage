# Position Sizing — γ-Regime-Map & A7-Trigger (Strang C)

**Status:** **DECIDED** (2026-08-28) · Follow-up zu PR #20 · Implementierung in separatem Code-PR  
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
| T2 | **`regime_flag >= 1`** (**DECIDED**) | Sizing nur bei Drift / Unreliable / Trend — nicht bei `STABLE`/`STABLE_SIDEWAYS` (flag 0) |
| T3 | Ledger ≥ **50** SELL-Roundtrips (B2 `min_trades`) | sonst: `INSUFFICIENT_HISTORY` (hard block, kein Fallback-p) |

### 3.1 Trigger-Alternativen (Review)

| Option | Trigger | Pro | Contra |
|--------|---------|-----|--------|
| **A (Vorschlag)** | `regime_flag >= 1` | Kopplung an A7 messbar; weniger Rauschen in Stable-Phasen | Kein Sizing in langen Stable-Runs (evtl. gewollt) |
| B | Jeder Leader-Zyklus | Maximale Observability | Viele `INSUFFICIENT_HISTORY`-Zeilen ohne Fills |
| C | Nur `regime_flag >= 2` | Nur Trend-Phasen | `LOW_LEVEL_DRIFT` unsichtbar für Sizing |

**Entscheidung:** Option **A** (`regime_flag >= 1`) — **DECIDED** 2026-08-28.

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

## 6. Review-Entscheidungen (**DECIDED** 2026-08-28)

### 6.1 `DRIFT_IID_UNRELIABLE`: γ = 0,00 — **DECIDED**

| Option | Verhalten | Entscheidung |
|--------|-----------|--------------|
| **Zero** | γ=0 → `hypothetical_notional=0`, Gate meist LIMIT_OK | **Gewählt** — charter-konservativ, kein Vertrauen in p/b |
| Hold last γ | γ bleibt vom vorherigen Regime | Verworfen |

Audit: `gamma_source: iid_safe_mode` wenn `classified_regime=DRIFT_IID_UNRELIABLE`.

### 6.2 Trigger: flag ≥ 1 — **DECIDED**

Option **A** aus §3.1: Sizing bei `regime_flag >= 1` (Warnung + Trend), nicht nur flag 2.

### 6.3 γ-Override via Helm/ConfigMap — **DECIDED**

| Mechanismus | Beschreibung |
|-------------|--------------|
| **Env-JSON** | `POSITION_SIZING_GAMMA_MAP` in ConfigMap (Helm `config:`) — Override ohne Image-Rebuild |
| Default | Built-in Map aus §2, wenn Env leer |

Entwurf: [`charts/regime-swarm/values-live-shadow.yaml`](../charts/regime-swarm/values-live-shadow.yaml) (`POSITION_SIZING_ENABLED=false`, γ-Map explizit — Strang D).

---

## 7. Freigabe-Kriterien — **abgeschlossen**

Siehe auch [§6 Review-Entscheidungen](#6-review-entscheidungen-decided-2026-08-28) (γ-Tabelle, Trigger, IID, Charter, Helm-Override).

- [x] γ-Tabelle von Team abgenickt (§2) — **2026-08-28**
- [x] Trigger-Option **A** (`regime_flag >= 1`) — **DECIDED** (§3.1, §6.2)
- [x] `DRIFT_IID_UNRELIABLE` → γ=0 — **DECIDED** (§6.1)
- [x] Charter-Check: weiterhin nur Schranken-Export ([§4 Parent-Doc](POSITION_SIZING_SUBSWARM.md))
- [x] Helm γ-Override via `POSITION_SIZING_GAMMA_MAP` — **DECIDED** (§6.3)

---

## 8. Implementierungs-Status

**PR #22 merged** (2026-08-28) — Code vollständig:

| # | Komponente | Status |
|---|------------|--------|
| 1 | `position_sizing/config.py` | ✅ `DEFAULT_GAMMA_MAP`, `POSITION_SIZING_GAMMA_MAP` |
| 2 | `position_sizing/orchestrator.py` (B0/B3) | ✅ `resolve_gamma`, IID→0 |
| 3 | `position_sizing/integration.py` | ✅ Trigger T2 `regime_flag >= 1` |
| 4 | `run_regime_swarm_daemon.py` | ✅ `drift_summary` → sizing hook |
| 5 | `run_regime_swarm_daemon.py` | ✅ Prometheus `sizing_*` |
| 6 | Tests | ✅ `make raas-position-sizing-smoke` |
| 7 | Helm | ✅ `values-live-shadow.yaml` (PR #23 — explizit `enabled=false`) |

**Default unverändert:** `POSITION_SIZING_ENABLED=false`.

### Nach Implementierung (Betrieb)

1. **Strang D:** Image-Rebuild + Cluster-Rollout — [`REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md` §9](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md#9-strang-d--image-update-pvc-sicher-post-pr-22)  
2. **Paper Exit (Voraussetzung):** [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) — Exit-Entscheidung + Round-Trip-Gate **vor** Strang B  
3. **Strang B:** `POSITION_SIZING_ENABLED=true` erst wenn **abgeschlossene Round-Trips ≥ 50** (`SELL` + `realized_pnl_eur` in WORM) **und** Ledger-Wiring  
4. **Grafana (optional):** Dashboard für `sizing_*` — später PR

**Hinweis (2026-08-28):** Live-Shadow erzeugte nur BUY (`break_price_below` unset). Exit **DECIDED: Option B** (feste Haltedauer k) — [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md). Strang B nach Exit-PR + Ledger-Wiring + **≥50 SELL-Round-Trips**.

---

## Siehe auch

- [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md)
- [`docs/RaaS_REGIME_DRIFT_PREREG.md`](RaaS_REGIME_DRIFT_PREREG.md) — A7-Klassen
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — laufender Shadow
