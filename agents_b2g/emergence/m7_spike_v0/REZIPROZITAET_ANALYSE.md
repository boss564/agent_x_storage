# Reziprozität = 0.0 — Traffic-Analyse

**Charakter:** Engineering-Diagnose · keine Pre-Reg  
**Bezug:** `m7_spike_v0` Gate `M7_LOSES_ELL_SELECTIVITY` · `frac_sticky_via_ledger = 0.0`

---

## 1. Urteil

**Artefakt des Traffic-Generators / Delivery-Schemas — kein Messfehler.**

Die Sticky-Kanten sind **gerichtet und rollen-pipeline-förmig**. Es entstehen
Dreiecks-Zyklen über Rollen, aber **keine** wechselseitigen Paare \((i,j)\) und
\((j,i)\). Deshalb ist `frac_sticky_via_ledger = 0.0` erwartbar, nicht anomal.

---

## 2. Nachrichtenfluss (`demo_producer_cluster` + Capture)

```text
Provider  --OFFER-->  Evaluator  --BHO_PROOF-->  Economic  --SETTLEMENT/broadcast-->  Provider
```

| Sticky-Eintrag | Gerichtete Ledger-Kante | Rückkante im Generator? |
|----------------|-------------------------|-------------------------|
| Provider → Evaluator | \((P,E)\) | nein — Evaluator antwortet an Economic, nicht an P |
| Evaluator → Economic | \((E,C)\) | nein — Economic broadcastet an Provider |
| Economic → Provider | \((C,P)\) | nein — Provider schreibt an Evaluator |

Es gibt einen **3-Zyklus über Rollen** \(P\to E\to C\to P\), aber Reziprozität
im Sinne der Edge-Local-Frage verlangt **dieselbe Kante in beide Richtungen**:
\(i\) reagiert auf \(\ell_{ij}\) **und** \(j\) auf \(\ell_{ji}\).

Arm C (Partner-Permutation) zerstört dann Paar-Schleifen — bei Reziprozität 0
gibt es keine solchen Paare.

---

## 3. Konsequenz für Option A

| Diagnose | Maßnahme |
|----------|----------|
| Generator-Artefakt (Pipeline) | Traffic so erweitern, dass **Antworten** die Rückkante schreiben (z. B. Evaluator→Provider ACK / Economic→Evaluator Receipt) **oder** Settlement beidseitig im Ledger verbuchen |
| Architektur (bewusst einseitig) | Edge-Local-Frage umformulieren (z. B. Zyklus-Kopplung statt Paar-Reziprozität) — anderes Design |

Empfehlung: **Generator erweitern** (Antwort-Kanten), nicht die Sticky-Permutation
umdefinieren. Sonst misst Arm C weiterhin nur Parameter-Umverteilung.

Zielmetrik vor Pre-Reg: Median `frac_sticky_via_ledger` **≫ 0** (Vorschlag:
mindestens ≥ 0.3 auf ≥2/3 Seeds), gemessen mit demselben Screen wie der M7-Spike.

---

## 4. M7 (sekundär)

Unverändert: Median zerstört sticky-ℓ-Selektivität. Erst nach Reziprozitäts-Fix
Filter justieren (Trimmed Mean / EWMA+Gate).

---

## 5. Status

```text
Engpass 1: Reziprozität = 0.0  → Pipeline-Traffic (Artefakt) — primär
Engpass 2: M7_LOSES_ELL_SELECTIVITY → Filter — sekundär
Pre-Reg:   gesperrt bis Engpass 1 adressiert
```
