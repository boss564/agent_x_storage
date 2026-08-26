# Reziprozität = 0.0 — Traffic-Analyse

**Charakter:** Engineering-Diagnose · keine Pre-Reg  
**Bezug:** `m7_spike_v0` Gate `M7_LOSES_ELL_SELECTIVITY` · `frac_sticky_via_ledger = 0.0`

---

## 1. Urteil

**Artefakt des Traffic-Generators / Delivery-Schemas — kein Messfehler.**

Die Sticky-Kanten sind **gerichtet und rollen-pipeline-förmig**. Es entstehen
Dreiecks-Zyklen über Rollen, aber **keine** wechselseitigen Paare \((i,j)\) und
\((j,i)\). Deshalb ist `frac_sticky_via_ledger = 0.0` erwartbar, nicht anomal.

**Kern:** Zyklus ≠ Reziprozität. `P→E→C→P` ist geschlossen, aber einseitig.

---

## 2. Nachrichtenfluss (`demo_producer_cluster` + Capture)

### Vorher (Diagnose)

```text
Provider  --OFFER-->  Evaluator  --BHO_PROOF-->  Economic  --SETTLEMENT/broadcast-->  Provider
```

| Sticky-Eintrag | Gerichtete Ledger-Kante | Rückkante im Generator? |
|----------------|-------------------------|-------------------------|
| Provider → Evaluator | \((P,E)\) | nein — Evaluator antwortet an Economic, nicht an P |
| Evaluator → Economic | \((E,C)\) | nein — Economic broadcastet an Provider |
| Economic → Provider | \((C,P)\) | nein — Provider schreibt an Evaluator |

### Nachher (Option A — ACK/Receipt)

```text
Request:  P → E (OFFER)     Receipt: E → P
Request:  E → C (BHO_PROOF) Receipt: C → E
Request:  C → P (SETTLEMENT) Receipt: P → C
```

Sticky-Rolle für Rückkanten: `receipt:<partner_id>` (kein gemeinsamer Key — sonst
Freeze-Kollision bei einem Sender → viele Empfänger).

Verifikation: `scripts/run_reciprocity_ack_check.py` → `reciprocity_ack_v0/`  
**Gate PASS** · Median `frac_sticky_via_ledger` = **1.0** (3/3 Seeds ≥ 0.3).

---

## 3. Konsequenz

| Schritt | Status |
|---------|--------|
| 1. Traffic ACK/Receipt | erledigt (`b9da5efe`) |
| 2. Reziprozität ≥ 0.3 | PASS (1.0) |
| 3. M7-Filter (sekundär) | **PASS** — `trimmed_m7` · Gate `M7_PRESERVES_FIT` |
| 4. Edge-Local Pre-Reg mit Wechselseitigkeit | freigegeben (Engineering-Vorbedingungen) |

Siehe `m7_filter_v0/M7_FILTER_ERGEBNIS.md` (Seeds `20261731–33`).

---

## 4. M7 (erledigt)

Canonical Intake: **`trimmed_m7`** = MAD-Gate + oberes Trimmed Mean (10 %).  
Vergleich: `median_m7` und `ewma_gate` ebenfalls ell-selektiv unter ACK-Traffic;
`ewma_gate` bleibt ρ-näher an EWMA.

---

## 5. Status

```text
Engpass 1: Reziprozität — BEHOBEN (via_led = 1.0)
Engpass 2: M7_LOSES_ELL_SELECTIVITY — BEHOBEN (trimmed_m7, M7_PRESERVES_FIT)
Pre-Reg:   Edge-Local mit Wechselseitigkeit darf spezifiziert werden
```
