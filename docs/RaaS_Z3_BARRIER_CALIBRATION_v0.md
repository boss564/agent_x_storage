# RaaS — Z3 / Risk-Barrier Calibration Plan v0 (P6)

**Status:** PLAN v0 (2026-08-27) · **Plan only** · kein Retune · kein Code-Zwang  
**Priorität:** Arbeitspaket „Z3-Sicherheits-Schranken kalibrieren“ (Option 3 unter 4 Paketen)  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · kein Order-Send  
**Bindend:** `docs/RaaS_WARN_BAND_AMENDMENT_v0.md` · Parent-`definition_hash` eingefroren  
**Nicht:** Trip senken „für Recall“ · Observed anheben als Messoptik · profitable Trades als Erfolgskriterium

---

## 1. Offene Hypothese (vorab)

> Können **zusätzliche** bzw. **kandidatisch variierte** Risiko-Schranken
> (Spread-/Range-Proxy, Latenz-Jitter/M7, optional Orderbuch-Imbalance)
> Invarianten-Brüche **verlässlicher** kennzeichnen — gemessen als
> **getrennte** FP/FN für **Trip** und für **Warnung** —
> ohne das eingefrorene Trip-Versprechen stillschweigend zu ersetzen?

Antwort ist **nicht** vorher aufschreibbar. Ein FP/FN-Optimum auf einer Kurve
ist eine **Messung**; die Übernahme neuer Kanten ist eine **Design-Entscheidung**
(+ neues Amendment + neuer Hash).

---

## 2. Was „Kalibrieren“ hier heißt / was nicht

| Ja (dieser Plan) | Nein |
|------------------|------|
| Trade-off-**Oberfläche** messen (Kandidaten × FP/FN Trip & Warn) | Produktions-`EXEC_RISK_BLOCK` / `CASCADE_BLOCK` automatisch setzen |
| Gegenfaktische Schwellen **nur** als Screen-Label | Recall 3/21 „reparieren“ durch Absenken der Trip-Kante |
| Neue Feature-Kandidaten (M7-Jitter, HL-Spread-Proxy; später Depth) | Profit / Track-Record als Zielfunktion |
| Ergebnis → optional **eigenes** Design-Amendment | Warnung → BLOCK schleichend vermischen |

**Härte aus Warn-Band-Amendment:**  
`WARNUNG` allein ⇒ **kein** BLOCK. Kalibrierung darf das nicht unterlaufen.

**Härte aus FN-Screen:**  
18/18 FN = `STRUCTURAL_GAP_A`, `above_trip=0`. Die Lücke ist benannt; Kalibrierung
ersetzt sie nicht durch Retune unter altem Namen.

---

## 3. Zwei Versprechen × zwei Fehlertypen (immer getrennt)

| Versprechen | Ground (Observed) | Predicted | FP / FN |
|-------------|-------------------|-----------|---------|
| **Trip** | Ereignis ≥ Trip-Kante (Parent-MAP) | Risiko-Schicht würde BLOCKEN | FP = Block ohne Trip-Ground; FN = Trip-Ground ohne Block |
| **Warnung** | Ereignis in Observed∖Trip (Warn-Band) | System würde WARNEN | FP/FN analog, **eigene** P/R |

Eingefrorene Referenz-Kanten (bis Definitions-Amendment):

```text
definition_hash (parent) = bbae3cb16d893e6380665843415c430aedf9946a084010e94b88dca7a0ccb01b
Observed:  drop≥2.0% OR dd60≥5.0%
Trip:      drop≥2.4% OR dd60≥6.0%   (exec≥0.80 / cascade≥0.75)
```

„Profitable Trades nicht unnötig blockieren“ wird **nur** als Proxy über **Trip-FP**
(und optional diagnostische Paper-Ledger-Felder) gelesen — **nicht** als PnL-Ziel.

---

## 4. Schranken-Kandidaten (Kalibrier-Grid)

### 4.1 Bereits im Gate (Score-Pfad „Z3_CASCADE“ / P3)

| Parameter | Ist (frozen) | Kalibrier-Rolle |
|-----------|--------------|-----------------|
| `EXEC_RISK_BLOCK` | 0.80 | Gegenfaktisches Grid **nur** im Screen |
| `CASCADE_BLOCK` | 0.75 | dito |
| `EXEC_RISK_SCALE_PCT` / `CASCADE_RISK_SCALE_PCT` | 3.0 / 8.0 | dito — Ändern ≡ anderes Mapping |

Grid v0 (vorab, nicht nach erstem Blick erweitern ohne Amendment):

```text
exec_block   ∈ {0.70, 0.75, 0.80, 0.85}
cascade_block∈ {0.65, 0.70, 0.75, 0.80}
```

Jeder Punkt = **Counterfactual Label**, nicht Prod-Config.

### 4.2 Neu / bisher ungemappt (Feature-Erweiterung)

| Kandidat | Datenlage | v0-Status |
|----------|-----------|-----------|
| HL-Spread-/Range-Proxy `(H−L)/close` | 1m Klines vorhanden | **Screen-fähig** |
| Latenz-Jitter → `latency_spike` / M7 | Live-Z3-Latenz-Screens existieren; Kline-Retro: schwach | **teilweise** (separater Latenz-Corpus) |
| Orderbuch-Imbalance | nicht im Public-Kline-Cache | **DATA_INSUFFICIENT** bis Depth-Feed |

Keine Orderbuch-Claims aus Klines erfinden.

---

## 5. Phasen (Reihenfolge bindend)

| Phase | Deliverable | Gate |
|-------|-------------|------|
| **P0** | Dieses Plan-Dokument | ✅ |
| **P1** | Counterfactual-Screen: Grid §4.1 × 180d Klines; Tabellen Trip-P/R + Warn-P/R + FP-Zählung; gleicher Parent-`definition_hash` für Ground | `RAAS_BARRIER_CAL_SURFACE_PASS` |
| **P2** | Feature-Add-on Screen: HL-Proxy als *zusätzliches* Warn- oder Trip-Signal (eigenes Label), FP/FN vs. Baseline ohne Retune der Frozen-Edges | `RAAS_BARRIER_FEATURE_PASS` oder `DATA_INSUFFICIENT` |
| **P3** | Nur bei bewusster Wahl: **Design-Amendment** neuer Kanten/Features + neuer Hash — dann erst Code | Startsignal erforderlich |
| **P4** | Orderbuch-Imbalance (wenn Feed da) | gesperrt bis Daten |

**Pause nach P1 ist erlaubt.** P3 ist nie automatische Folge von „besserer Kurve“.

### 5.1 Verdict-Semantik (bindend)

| Verdict | Bedeutet | Bedeutet **nicht** |
|---------|----------|---------------------|
| `RAAS_BARRIER_CAL_SURFACE_PASS` | P1-Screen **durchgelaufen** (Grid × Daten × Tabellen geschrieben, Charter-Stamps ok) | Aussage über „gute“/„schlechte“ Schranken; Freigabe neuer Prod-Kanten; Beleg für Option-1-Retune |
| `RAAS_BARRIER_FEATURE_PASS` | P2-Feature-Screen durchgelaufen unter vorab gesetzten Mindestregeln | Dass der HL-Proxy „das Gate verbessert“ |
| `DATA_INSUFFICIENT` | Zu wenige Ereignisse / fehlende Daten für belastbare Feature-Aussage | Peinliches Scheitern — gültiger wissenschaftlicher Ausgang |

**P1 ist explorativ.** Oberflächen-Zahlen (P/R, FP/FN pro Grid-Punkt) stehen im Report; das `PASS`-Verdict zitiert man nicht als Schranken-Beweis.

**P2 / Ereigniszahl:** 180d Retro hatte **21 Observed**-Ereignisse — für ein Zusatzsignal (HL-Proxy) ist das knapp. Unterschreitet die vorab gesetzte Mindestzahl (Screen-Skript: z. B. `n_observed < 30` oder `n_warn_band < 15`, konkret im Runner einfrieren) → **`DATA_INSUFFICIENT`**, kein Overclaim.

---

## 6. Abbruch- / Integritätsregeln

```text
live_execution = false
order_send = forbidden
prod_trip_edges = frozen until dedicated amendment
warn_band ≠ trip
no_single_recall_merge
pnl_not_objective
klines ≠ training labels for a deployable classifier claim
```

---

## 7. Abgrenzung zu anderen Arbeitspaketen

| Paket | Warum nachrangig |
|-------|------------------|
| 1 Gebührenmodell (P3) | Konfig / Diagnostik, keine FP/FN-Hypothese am Gate |
| 2 Schatten-Paare erweitern | Coverage, keine Schranken-Frage |
| 4 Tagesberichte / Webhooks | Automatisierung nach stabiler Semantik |

---

## 8. Verweise

| Artefakt | Rolle |
|----------|-------|
| `docs/RaaS_WARN_BAND_AMENDMENT_v0.md` | NORMAL/WARNUNG/TRIP · kein BLOCK aus Warnung |
| `docs/RaaS_FN_BELT_SCREEN_v0.md` | A SUPPORTED · Definitionslücke |
| `docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md` | Parent-MAP · Replay |
| `services/fail_closed_gate/gate_core.py` | Prod-Schwellen (unverändert bis P3) |
| Tag `v1.0-raas-baseline` | Fixpunkt |

---

## 9. Nächster konkreter Schritt

**P1 Counterfactual-Surface-Screen** (Skript + Make), wenn Startsignal — nicht vorher Prod anfassen.  
Commit dieses Plans separat möglich (Dokumentation only).
