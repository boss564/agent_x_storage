# Shadow Evaluator (Strang B.1) — Pre-Reg

**Status:** FREIGABE (2026-08-31) — Amendments A1–A3 · **kein Code vor Implementierung**  
**Erstellt:** 2026-08-31  
**Freigegeben:** 2026-08-31 (A1 `regime_flag` T2 · A2 volle `INSUFFICIENT_HISTORY` · A3 `KELLY_SIGN_UNCERTAIN`)  
**Strang:** Offline Shadow Evaluator — passive Replay der eingefrorenen Stufe-3-Methodik  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Parent:** [`PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) (Strang B, **FROZEN**) · [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) · [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md)  
**Außerhalb:** Fenster W (Live-Shadow, `k=4966`) · Cluster-State · `paper_trades.worm.jsonl` · `PaperLedger` · `POSITION_SIZING_ENABLED`

---

## 0. Abgrenzung — was dies NICHT ist

| Nicht | Warum |
|-------|--------|
| Live-Order-Pfad | `order_send=false` bleibt; kein Exchange, kein Ledger-Mutate |
| Ersatz für Strang B | B0–B8 im Daemon bleibt autoritativ nach Gate n≥50; B.1 **bereitet** nur vor |
| Vorstufe zum Live-Gang | Dry-Run unter Real**daten**, nicht Real**execution** |
| Teil von Fenster W | W sammelt weiter ungestört; Evaluator liest nur Snapshots/Exports |
| Methodik-Tuning | Kelly/Z3/Gebühren **referenzieren** [`PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — keine parallele Formel |
| HARKing-Werkzeug | Ergebnisse dürfen Strang B **nicht** nachträglich anpassen |

**Zweck (eine Zeile):** Unter Realbedingungen (echte Edges, echte Regime-Zyklen, echte PhaseSignals) **passiv** protokollieren, was Strang B **hypothetisch** entschieden hätte — ohne State, Charter oder Fenster W zu berühren.

---

## 1. Claims (falsifizierbar)

| ID | Claim |
|----|--------|
| **H1** | Der Evaluator wendet die **eingefrorene** Stufe-3-Logik (Kelly §2, Z3 §3, Post-Only/Maker §3.3 von Parent) **rein passiv** an — kein Schreiben in WORM, Ledger, ConfigMap oder Pod-State. |
| **H2** | Jeder Lauf erzeugt konsistente Zeilen in `shadow_eval.jsonl` (append-only, Schema §4) mit `diagnostic_only=true`. |
| **H3** | Bit-identische Fenster-W-Artefakte vor/nach Evaluator-Lauf (`paper_edges.jsonl`, RT-Zähler, WORM-Fills, `n_eligible_at_freeze_k`) — Evaluator ist **read-only** auf Quellen. |
| **H4** | Der Evaluator **ersetzt nicht** das Strang-B-Gate (`n_eligible ≥ 50` → `POSITION_SIZING_ENABLED`); er liefert nur Vorbereitungs-Metriken ab n≥25. |

---

## 2. Invarianten

| ID | Invariante |
|----|------------|
| **I1** | **Read-only** auf Fenster-W- und Host-Quellen; **kein** `kubectl`, kein Pod-Exec, kein Patch. |
| **I2** | **Write-only** auf dedizierten Shadow-Pfad (`shadow_eval.jsonl` unter `data/audit/` oder `exports/shadow/` — bei Implementierung festlegen, nicht WORM). |
| **I3** | Pro verarbeitetem Ereignis (eligible Edge abgeschlossen **oder** synchronisierter Regime-Zyklus): eine Shadow-Zeile mit Kelly + Z3-Entscheidung **als Parent definiert**. |
| **I4** | Kein Einfluss auf Fenster W: kein zusätzlicher BUY/SELL, kein `force_exit`, kein Sizing-Enable. |
| **I5** | Strang B.1 ist **orthogonal** zu Fenster W — eigener Prozess/Cron/CLI, nicht im `regime-swarm`-Daemon. |
| **I6** | `order_send=true` in Shadow-Output → **hard fail** (Smoke S4, Charter §7). |

---

## 3. Methodik (Referenz — nicht neu erfinden)

**Freeze-Regel:** Alle Formeln, Schwellen und Gates sind **By-Reference** aus [`PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md). Abweichungen in B.1 = Bug, kein Tuning.

### 3.1 Kelly-Sizing (Parent §2)

```text
kelly_raw     = (p · b − (1 − p)) / b
f*_raw        = max(0, γ · kelly_raw)
f*_point      = min(f*_raw, kelly_fraction_cap)    # K1 = 0.25
```

| Input | Quelle (read-only) |
|-------|---------------------|
| `p`, `b` | Rollierendes Fenster N=50 **eligible** `profit_fraction` aus `paper_edges.jsonl` / WORM-Replay (Parent §1, §4.2) |
| `γ` | `classified_regime` → Map Parent §5.2 |
| `regime_flag` | Regime-Zyklus-Export (`drift_summary.regime_flag`) — Parent §2.6 T2 |
| Bootstrap | B=1000, `f*_p05`/`f*_p95` Parent §2.4 |
| Schranke | `max_notional = capital × 0.02`; Gate `LIMIT_OK` nur wenn `f*_p05 > 0` Parent §2.5 |

**A1 — Parent §2.6 T2 (`regime_flag`):** Kelly wird nur berechnet bei **`regime_flag >= 1`**. Bei `regime_flag < 1`: `shadow_gate_decision = BLOCKED`, `regime_flag` wird protokolliert, **keine** Kelly-Berechnung (kein Sizing in STABLE-only-Phasen).

**A2 — `INSUFFICIENT_HISTORY` (Parent §2.5, konjunktiv zu §2.3):** `INSUFFICIENT_HISTORY` wenn `stats_count < 50` **ODER** `n_wins < 5` **ODER** `n_losses < 5` **ODER** `b <= 0` **ODER** `b` undefiniert (`min_wins = min_losses = 5`). Kein Kelly mit Fallback-p (Parent H3).

**Ab n≥25 (Pilot):** Evaluator **darf starten**, protokolliert `stats_count`, `n_wins`, `n_losses` — **kein** `LIMIT_OK` / `LIMIT_EXCEEDED` / `KELLY_SIGN_UNCERTAIN` als Freigabe.

### 3.2 Z3 Risk Gates (Parent §3 — nicht vereinfachen)

Der Entwurf mit „Regime ACTIVE / Spread / Cross-Venue p_NN“ ist **verworfen**. Maßgeblich:

| Gate | Parent | Shadow-Aktion |
|------|--------|---------------|
| Z3-P0/P1/P2 | PhaseSources `news_sentiment` / `price_gap` | `z3_blocked: true`, Feld `phase_gate` |
| Z3-D1 | Daily loss ≤ −2 % | `daily_loss_gate_tripped` |
| Z3-O1 | `post_only_limit` | `execution_mode` in Shadow-Zeile |

Lookback: 24 h News, 1 h Price-Gap (Parent §3.1). Schwellen D1: `impact_score ≥ 0.70`, `sentiment < −0.30`.

### 3.3 Maker-Fee & Execution (Parent §1.1, §3.3, D2)

Shadow rechnet **Post-A1-Estimand** (auch für historische Trips: WORM-Rückrechnung vor `PAPER_SIZING_A1_EPOCH_TS`):

| Komponente | Freeze |
|------------|--------|
| Execution | `post_only_limit` (theoretisch: Fill nur im Spread; kein Taker-Fallback) |
| Gebühren | **Maker**-Schedule aus `FeeSchedule` / `ledger.py` (Ist-Default: **7,5 bps** je Seite — **nicht** frei erfundene 2 bps) |
| Slippage (Shadow) | **0** zusätzlich zum synthetischen Spread — explizit als **Optimistic bound** labeln |

**Wichtig:** Maker-Rate ist **nicht** in diesem Strang neu zu setzen — bei Implementierung aus bestehender `FeeSchedule` lesen; Änderung nur via Parent-Amendment.

### 3.4 Was der Evaluator zusätzlich protokolliert (Shadow-only)

| Feld | Bedeutung |
|------|-----------|
| `shadow_pnl_eur` | Hypothetische Trip-PnL unter Post-A1 + Maker (Replay) |
| `shadow_would_size` | `f*_point × capital` wenn alle Gates offen (Diagnose, keine Empfehlung) |
| `shadow_gate_decision` | `BLOCKED` \| `INSUFFICIENT_HISTORY` \| `LIMIT_OK` \| `LIMIT_EXCEEDED` \| `Z3_BLOCKED` \| **`KELLY_SIGN_UNCERTAIN`** |
| `kelly_sign_uncertain` | `true` iff `shadow_gate_decision == KELLY_SIGN_UNCERTAIN` (Parent §2.5 dritter Zustand) |
| `fenster_w_unchanged` | Hash-Snapshot der gelesenen Edge-Zeile (H3-Nachweis) |

**A3 — dritter Kelly-Zustand (Parent §2.5):** `KELLY_SIGN_UNCERTAIN` wenn `f*_p05 <= 0` — **kein** `LIMIT_OK` / `LIMIT_EXCEEDED`. Zusätzlich `kelly_sign_uncertain: true` protokollieren (Parent-Konsistenz).

---

## 4. Ausgabe-Schema (`shadow_eval.jsonl`)

Append-only. Schema `shadow_evaluator_v0`:

```json
{
  "schema": "shadow_evaluator_v0",
  "ts": "2026-08-31T12:00:00+00:00",
  "edge_id": "…",
  "swarm_cycle_id": "SWARM-…",
  "regime_flag": 1,
  "stats_count": 12,
  "n_wins": 3,
  "n_losses": 2,
  "p": null,
  "b": null,
  "gamma": 0.20,
  "gamma_source": "regime_map",
  "kelly_fraction_gamma_uncapped": null,
  "kelly_fraction_computed": null,
  "kelly_fraction_p05": null,
  "kelly_fraction_p95": null,
  "shadow_gate_decision": "INSUFFICIENT_HISTORY",
  "kelly_sign_uncertain": false,
  "z3_gate_reason": null,
  "execution_mode": "post_only_limit",
  "shadow_pnl_eur": null,
  "source_hashes": { "edge": "sha256…" },
  "diagnostic_only": true,
  "live_execution": false,
  "order_send": false,
  "not_investment_advice": true,
  "scope": "DEFENSIVE_CAUSAL_GROUNDING"
}
```

Keine Felder: `advisory_position_size`, `recommended_units`, `should_trade`.

---

## 5. Gate-Disziplin (zeitliche Reihenfolge)

| Stufe | Bedingung | Aktion |
|-------|-----------|--------|
| **G0** | Diese Pre-Reg **FREIGABE** (2026-08-31, A1–A3) | Implementierung erlaubt (~200 LOC Ziel) |
| **G1** | News-24h-Scheduler-Gate **PASS** ([`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md)) | Evaluator-Design final; Start noch nicht |
| **G2** | `n_eligible_at_freeze_k ≥ 25` | Evaluator **starten** (Pilot, nur Deskriptiv) |
| **G3** | `n_eligible_at_freeze_k ≥ 50` | Volle Auswertung + Abgleich mit Strang B nach Enable |
| **G4** | Strang B Enable | Separater Runbook-Schritt — **nicht** durch Shadow-Ergebnis auslösen |

Fenster W läuft während G2–G4 **unverändert** (`PAPER_HOLD_SECONDS=4966`, kein Evaluator-Hook im Daemon).

---

## 6. Smoke (Fault-Injection)

| ID | Test | Erwartung |
|----|------|-----------|
| **S1** | Fixture-Edge + Fixture-Regime + leere PhaseSignals | `shadow_gate_decision` ∈ {`BLOCKED`, `INSUFFICIENT_HISTORY`, `LIMIT_OK`, `LIMIT_EXCEEDED`, `Z3_BLOCKED`, `KELLY_SIGN_UNCERTAIN`} |
| **S2** | Zwei Läufe, gleiche Inputs | Zwei Zeilen in `shadow_eval.jsonl`; zweite `prev_hash`/`hash` Kette optional |
| **S3** | Vorher/Nachher-Hash von `paper_edges.jsonl` (Fixture-Kopie) | Identisch — I4/H3 |
| **S4** | Output-Zeile mit `order_send: true` | Validator/Writer wirft vor Append |

**Gate:** S1–S4 grün vor erstem Lauf gegen Live-Exports.

---

## 7. Anti-HARKing

1. Methodik = Parent [`PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — **FROZEN**; B.1 fügt keine neuen Schwellen hinzu.
2. Shadow-Ergebnisse dürfen γ, K1, Z3-Schwellen oder N **nicht** motivieren zu ändern.
3. Shadow dient **Kalibrierung der Implementierung** (Code = Spec), nicht **Kalibrierung der Spec** (Spec = Daten).
4. Kein „wenn Shadow LIMIT_OK, dann früher enablen“ — G4 bleibt.

---

## 8. Charter

`diagnostic_only` · `live_execution=false` · `order_send=false` auf jeder Zeile.

Der Evaluator beantwortet: „Hätte die **eingefrorene** Methodik an diesem Punkt BLOCKED oder LIMIT_OK gesagt?“ — nicht: „Soll gehandelt werden?“

---

## 9. Was der Evaluator zeigt — und was nicht

| Zeigt | Zeigt nicht |
|-------|-------------|
| Konsistenz Spec ↔ Code unter **realen** Edge-Zeiten | Echte Slippage/Latenz/Depth |
| Verteilung `shadow_gate_decision` vor n=50 | Live-Execution-Qualität |
| Z3-Block-Rate mit echten PhaseSignals | Börsen-Maker-Rebate-Drift |
| Ab n≥25: Trend von `stats_count` / `p` / `b` | Ersatz für Strang-B-Audit im Pod |

**Label:** Optimistic offline bound — Dry-Run, kein Live-Validierungsersatz.

---

## 10. Implementierungs-Scope (nach FREIGABE)

| Artefakt | Vorschlag |
|----------|-----------|
| Modul | `scripts/shadow_evaluator.py` oder `prototypes/raas_paper_trading/shadow_eval/` |
| CLI | `PYTHONPATH=. python3 -m … --once` (Host, nicht Cluster) |
| Inputs | `paper_edges.jsonl`, Regime-Export, `data/phase_signals/*.jsonl` (read-only) |
| Output | `data/audit/shadow_eval.jsonl` |
| Tests | `scripts/test_shadow_evaluator.py` — S1–S4 |

Keine Änderung an: `run_regime_swarm_daemon.py`, `ledger.py`, Helm, Fenster-W-Env.

---

## 11. Review-Checkliste (FREIGABE 2026-08-31)

- [x] Parent-Referenz [`PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) akzeptiert (keine parallele Kelly/Z3-Formel)
- [x] Z3 = PhaseSources + Daily Loss + Post-Only (nicht Spread/Cross-Venue-Vereinfachung)
- [x] Maker-Fee aus `FeeSchedule`, nicht ad-hoc 2 bps
- [x] G2/G3/G4 Zeitdisciplin akzeptiert
- [x] S1–S4 als einziges Smoke-Gate
- [x] A1 `regime_flag >= 1` (Parent §2.6 T2)
- [x] A2 volle `INSUFFICIENT_HISTORY`-Konjunktion (Parent §2.3 + §2.5)
- [x] A3 `KELLY_SIGN_UNCERTAIN` + `kelly_sign_uncertain` (Parent §2.5)
- [x] Kein Code vor Status FREIGABE

**Nach FREIGABE:** Implementierung → Smoke S1–S4 → Commit → Start ab n≥25 (G1 News-24h-Gate PASS weiterhin vor erstem Live-Lauf).

---

## Siehe auch

- [`docs/PAPER_SIZING_PREREG.md`](PAPER_SIZING_PREREG.md) — Strang B, FROZEN
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Fenster W
- [`docs/AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) — Writer vs. Inline-Gate
