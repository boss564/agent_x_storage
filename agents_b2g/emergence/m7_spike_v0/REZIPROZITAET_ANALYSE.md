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
| 1. Traffic ACK/Receipt | erledigt |
| 2. Reziprozität ≥ 0.3 | PASS (1.0) |
| 3. M7-Filter (sekundär) | offen |
| 4. Edge-Local Pre-Reg mit Wechselseitigkeit | gesperrt bis Schritt 3 |

---

## 4. M7 (sekundär)

Unverändert: Median zerstört sticky-ℓ-Selektivität. Erst nach Reziprozitäts-Fix
Filter justieren (Trimmed Mean / EWMA+Gate).

---

## 5. Status

```text
Engpass 1: Reziprozität — behoben (ACK/Receipt, Median via_led = 1.0)
Engpass 2: M7_LOSES_ELL_SELECTIVITY → Filter — sekundär (nächster Schritt)
Pre-Reg:   gesperrt bis Engpass 2 adressiert
```
