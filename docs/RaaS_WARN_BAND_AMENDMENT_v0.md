# RaaS — Design-Amendment: Warnstufe (Option 3) v0

**Status:** AMENDMENT v0 (2026-08-27) · **Design only** · **nicht implementiert**  
**Entscheidung:** Option 3 (dritte Stufe „Warnung“) — bestätigt nach FN-Gürtel-Screen  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · kein Order-Send  
**Basis:** `docs/RaaS_FN_BELT_SCREEN_v0.md` §5.1–5.2 · Parent `docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md`  
**Nicht:** Trip-Schwelle senken · Observed anheben „für besseren Recall“ · Live-Auth

---

## 1. Warum dieses Amendment

180d FN-Screen: **18/18 FN = `STRUCTURAL_GAP_A`**, `above_trip=0`.  
Recall 3/21 maß den **Abstand zweier Definitionen**, nicht Detektor-Güte.  
Option 3 benennt diesen Abstand als eigenes Band — ohne das Trip-Versprechen zu ändern.

| Verworfene Option | Grund |
|-------------------|--------|
| 1 Trip senken | Retune / anderes Sicherheitsversprechen; FP-Risiko |
| 2 Observed anheben | Messoptik; keine bessere Detektion |

---

## 2. Drei Stufen (Soll-Semantik)

Schwellen bleiben die **eingefrorenen** Parent-MAP-Kanten (gleicher `definition_hash`
bis ein *neues* Definitions-Amendment den Hash ändert):

```text
Observed:  bar_drop ≥ 2.0%  OR  roll_dd_60 ≥ 5.0%
Trip:      bar_drop ≥ 2.4%  OR  roll_dd_60 ≥ 6.0%
           (≡ exec_risk≥0.80 / cascade_risk≥0.75 unter Parent-Skalierung)
```

| Stufe | Bedingung | Semantik | Gate-Entscheidung (Soll) |
|-------|-----------|----------|---------------------------|
| **NORMAL** | unter Observed | kein Safety-Ereignis dieser Art | keine zusätzliche Warn-/Block-Labelung |
| **WARNUNG** | Observed erreicht, Trip **nicht** | FN-Gürtel / Vor-Alarm — beobachten | **kein** BLOCK allein wegen Warnung; Trip-Kante unverändert |
| **TRIP / BLOCK** | ≥ Trip-Kante | hartes Risiko-Schicht-Ereignis | wie heute: `evaluate_gate` BLOCK bei P3/P8/Z3-Cascade | 

**Wichtig:** WARNUNG ist **kein** abgeschwächter Trip und **kein** Live-Freigabe-Signal.
Human-Latch und `live_execution=false` bleiben unberührt.

---

## 3. Metriken (getrennte Versprechen)

Zwei Envelope-Auswertungen, nie zu einer Recall-Zahl vermischt:

| Versprechen | Predicted | Observed (Ground) | Primärmetrik |
|-------------|-----------|-------------------|--------------|
| **Trip** | Gate BLOCK (Risiko-Schicht, Analyse-Modus wie Retro) | Ereignis ≥ Trip-Kante | Precision / Recall **Trip** |
| **Warnung** | System labelt WARNUNG | Ereignis in Observed∖Trip | Precision / Recall **Warnung** |

Ein Anstieg des „Gesamt-Recalls“ durch Absenken der Trip-Kante ist **kein**
Detektor-Gewinn, sondern ein **anderes Versprechen** und bedarf eines eigenen Amendments
(+ neuer `definition_hash`).

---

## 4. Was später implementiert werden müsste (nicht jetzt)

| Schritt | Inhalt | Status |
|---------|--------|--------|
| A | Enum/`band`: `NORMAL` \| `WARNUNG` \| `TRIP` in Retro-/FN-Reports | ausstehend |
| B | Getrennte `score_envelope_hits` für Trip- und Warn-Cohorts | ausstehend |
| C | Optional: Ops-/Dashboard-Hinweis „Warnung“ (kein Order-Pfad) | ausstehend |
| D | WORM-Felder `safety_band`, getrennte P/R, `definition_hash` | ausstehend |

**Auslöser Implementierung:** explizites Startsignal nach Review dieses Amendments.  
Kein automatisches Mitziehen aus Screens.

---

## 5. Integritätsregeln

```text
live_execution = false
order_send = forbidden
trip_edges = unchanged until dedicated amendment
warn_band ≠ trip
not_investment_advice = true
scope = DEFENSIVE_CAUSAL_GROUNDING
```

---

## 6. Verweise

| Artefakt | Rolle |
|----------|-------|
| `docs/RaaS_FN_BELT_SCREEN_v0.md` | A SUPPORTED · Design-Optionen |
| `docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md` | Parent-Definitionen · `definition_hash` |
| `services/fail_closed_gate/gate_core.py` | Unveränderte BLOCK-Schwellen |
| Tag `v1.0-raas-baseline` | Fixpunkt |
| `docs/RaaS_Z3_BARRIER_CALIBRATION_v0.md` | P6 Kalibrier-**Plan** (Trade-off-Oberfläche, kein Auto-Retune) |
