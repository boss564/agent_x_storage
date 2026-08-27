# RaaS — FN-Gürtel Screen v0 (Ursachen A–D)

**Status:** MAP v0 (2026-08-27) · additiv · wissenschaftlicher Screen  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · kein Order-Send  
**Basis:** `docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md` · gleicher `definition_hash`  
**Nicht:** Gate-Schwellen nachjustieren, Feature-Engineering als „Fix“, Track-Record

---

## 1. Offene Hypothese

> Warum trippt die Gate-Risiko-Schicht nicht bei allen Observed-Breaks?
> 180d: 18 FN / 21 Observed — welche **Ursache** dominiert den FN-Gürtel?

Antwort vor dem Lauf **nicht** festschreiben. Kein Tuning der Trip-Schwellen
als Ergebnis dieses Screens (das wäre Konfigurations-Optimierung, kein Test).

---

## 2. Vier Ursachen (vorab operationalisiert)

| ID | Ursache | Testbare Vorhersage (v0) | Falsifikation |
|----|---------|--------------------------|---------------|
| **A** | Trip-Schwellen über Observed | Fast alle FN liegen in `drop∈[2.0, 2.4)` und/oder `dd∈[5.0, 6.0)` und **unter** Exec-/Cascade-Trip | Anteil FN mit `drop≥2.4` **oder** `dd≥6.0` und trotzdem kein Trip ≫ 0 |
| **B** | Feature-Extraktion unvollständig | FN unterscheiden sich von TP in verfügbaren Proxies (Volume-z, HL-Range) **nicht**, obwohl Trip-fähig — oder Proxy zeigt Signal, das Mapping ignoriert | Ohne Orderbuch: B nur **teilweise**; voller Test braucht Depth-Daten (ausstehend) |
| **C** | Score-Cascade-Gewichtung | Unter MAP v0 ist `cascade_risk = min(1, dd/8)` **univariat** → C ist von A (Skalierung) **nicht unabhängig** identifizierbar | Nur wenn multi-feature Cascade existiert; sonst Verdict `NOT_SEPARABLE` |
| **D** | Zeitliche Auflösung zu grob | Bei FN: Intra-Bar `(H−L)/close` ≫ Close-to-Close-Drop (Proxy für Sub-1m-Stress) | Proxy-Anteil niedrig **und/oder** 1s-Daten zeigen keine zusätzlichen Breaks |

**Bindend:** Observed-/Feature-/Gate-Definitionen = Retrospective MAP §3.
`definition_hash` muss mit dem Retro-Lauf übereinstimmen.

Ableitung Trip-Kanten (kein neues Tuning — nur Algebra aus Retro-MAP):

```text
exec_trip_drop_pct    = EXEC_RISK_BLOCK    * EXEC_RISK_SCALE_PCT    = 0.80 * 3.0 = 2.4
cascade_trip_dd_pct   = CASCADE_BLOCK      * CASCADE_RISK_SCALE_PCT = 0.75 * 8.0 = 6.0
```

---

## 3. Screen-Ablauf

1. Klines laden (Default `--days 180`, Symbol wie Retro).
2. Features + `evaluate_gate` wie Retro → Liste Observed / Predicted.
3. FN = `observed ∧ ¬predicted`; TP = beide true; FP/TN deskriptiv.
4. Jeden FN klassifizieren (A-Band vs. über Trip-Kante).
5. Proxies B/D berechnen; C als Separability-Check.
6. Verdicts pro Hypothese: `SUPPORTED` / `REJECTED` / `PARTIAL` / `NOT_SEPARABLE` / `DATA_INSUFFICIENT`.
7. WORM + Report unter `exports/reports/fn_belt_screen_latest.*`.

---

## 4. Metriken

| Metrik | Rolle |
|--------|-------|
| `fn_structural_gap_share` | Anteil FN unter Trip-Kante (A) |
| `fn_above_trip_count` | FN trotz Trip-fähiger Features (gegen A) |
| Volume-z / HL-Range FN vs TP | Proxy B/D |
| `definition_hash` Match | Integrität |

Kein Profit Factor. Kein Claim „Gate verbessern“.

---

## 5. Artefakte

| Pfad | Rolle |
|------|-------|
| `scripts/raas_fn_belt_screen.py` | Runner |
| `exports/reports/fn_belt_screen_latest.md` | Report (gitignored) |
| `logs/worm/fn_belt_screen.jsonl` | WORM (gitignored via `logs/`) |

Make: `make raas-fn-belt-screen` (180d).

---

## 5.1 Screen-Ergebnis (180d, `definition_hash` match)

| ID | Verdict | Befund |
|----|---------|--------|
| **A** | `SUPPORTED` | **18/18** FN = `STRUCTURAL_GAP_A`; `above_trip=0` |
| **B** | `PARTIAL` | A erklärt FN; Orderbuch fehlt → voller B-Test nicht möglich |
| **C** | `NOT_SEPARABLE` | Cascade univariat → ≡ Skalierung von A |
| **D** | `PARTIAL` | HL≫drop-Proxy bei 11/18 FN; Sub-1m-Daten ausstehend |

**Kern:** Der FN-Gürtel ist unter dem eingefrorenen Mapping primär die **Definitionslücke** Observed (2 %/5 %) ↔ Trip (2.4 %/6 %), kein Gate-Bug oberhalb der Trip-Kante.

### 5.2 Mögliche Design-Folgen (nicht jetzt — bewusste Entscheidung)

| Option | Änderung | Risiko |
|--------|----------|--------|
| 1 | Trip-Schwelle senken | mehr False-Positives |
| 2 | Observed-Schwelle anheben | echte Breaks aus der Observed-Menge verlieren |
| 3 | Dritte Stufe („Warnung“) zwischen Observed und Trip | zusätzliche Semantik / Ops-Last |

Das ist **Design**, kein automatisches Retune aus diesem Screen.

**Entscheidung (2026-08-27):** Option **3** gewählt — Design-Amendment
`docs/RaaS_WARN_BAND_AMENDMENT_v0.md` (Semantik + getrennte Metriken, **nicht** implementiert).

---

## 6. Verweise

| Artefakt | Rolle |
|----------|-------|
| `docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md` | Parent-Screen · §5.1 Ergebnisse |
| `docs/RaaS_WARN_BAND_AMENDMENT_v0.md` | Option-3 Design (Warnstufe), ohne Code |
| `services/fail_closed_gate/gate_core.py` | Unveränderte Schwellen |
| Tag `v1.0-raas-baseline` | Fixpunkt |
