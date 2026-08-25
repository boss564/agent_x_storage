# Emergenz — Ledger-basierte Taktraten-Kopplung: Pre-Registration (BINDEND)

**Arbeitstitel:** `KOPPLUNG_LEDGER_v1`  
**Status:** **ABGESCHLOSSEN** — 2026-08-25 · Sweep ausgeführt · L1+L2: `KOPPLUNG_INVALID`  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) auf **gebautem** Kanten-Ledger  
**Architektur:** `docs/KANTEN_LEDGER_v1_DRAFT.md` · Implementierung `kanten_ledger.py`  
**Artefakte:** `agents_b2g/emergence/kopplung_ledger_v1/` · Abschluss: `ABSCHLUSS.md`  
**Serien-Schluss:** `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` (STRANG GESCHLOSSEN)

### Bindungs-Vermerk

```text
Status: DRAFT → BINDEND
Dokument: docs/KOPPLUNG_LEDGER_v1_PREREG.md
Datum: 2026-08-25
Normierung: σ (s(ℓ)=clip(ℓ/(σ_ℓ+ε),0,1); MAE_norm=MAE_raw/(σ_ℓ+ε))
κ=0-Spot-Check: ja (Seed 20261301, L1+L2)
Arme: A/B/C
L1: avg_latency · L2: interaction_count (getrennt)
Seeds: 20261301…06
Per-κ-Nachprüfung: S-S/S-G normiert
PRECONDITION_LOST: bindend
§1.1 / κ*: nur vorbedingungs-intakte κ
```

### HARKing-Sperre (strikt)

Nicht für Hypothesentests dieser Studie verwenden:

- `agents_b2g/emergence/kanten_ledger_v1/` (Abnahme-Datensatz κ=0)
- `agents_b2g/emergence/partnerselect_screen_v1/`
- `agents_b2g/emergence/eij_i1/`, `eij_sweep/`
- `agents_b2g/emergence/state_screen/`, `kopplung_full/`, `reputation_i1/`

Neue Seeds · neue Läufe · neue Artefakte unter `agents_b2g/emergence/kopplung_ledger_v1/`.

---

## 0. Zweck und Abgrenzung

### 0.1 Ausgangslage

Knoten-Zustände sind partnerblind / global synchron (`PARTNERSELECT_SCREEN_v1`:
`NONE_CLOSE`, `|ρ|≈0.999`). Parametrisches `E_ij` war I1-selektiv, Sweep trotzdem
`KOPPLUNG_INVALID`. Ein **bewusst gebautes** Ledger (`KANTEN_LEDGER_v1`) besteht
erstmals S-S∧S-G bei κ=0 für `interaction_count` und `avg_latency`.

### 0.2 Forschungsfrage

Erzeugt Taktraten-Kopplung an eine **Ledger-Komponente** `ℓ_ij ∈ {avg_latency,
interaction_count}` unter Intervention `κ` eine shuffle-sensitive Kohärenz
(Arm B vs. Arm C), **während** die Partnerselektivität von `ℓ_ij` unter κ>0
**erhalten** bleibt?

### 0.3 Neues Element (kein Vorgänger-Pre-Reg)

Die Vorbedingung wurde bei **κ=0** verifiziert. Im Sweep wird `ℓ_ij` **endogen**:
die Tickrate von i hängt von `ℓ_ij` ab, und `ℓ_ij` hängt von den Interaktionen ab,
die durch die Tickrate entstehen.

Zwei Ausgänge:

1. **Selektivität bleibt** → `r_B` vs. `r_C` misst, was §1.1 verlangt.  
2. **Selektivität homogenisiert** (`|ρ|→1` oder MAE kollabiert) → ein am Ende
   gemessenes `COUPLED` stützt sich auf eine Vorbedingung, die zum Messzeitpunkt
   nicht mehr gilt (strukturell analog zu gesättigten Konditionierern).

**Bindende Regel:** I1-Kriterien (S-S / S-G) werden **je κ-Stufe erneut** auf dem
Sweep-Datensatz geprüft. Scheitern → Zellenlabel `PRECONDITION_LOST` (kein
`NO_COUPLING`, kein verwertbarer Kopplungsbefund für diese Zelle).

### 0.4 Nomenklatur

| Begriff | Bedeutung |
|---------|-----------|
| Arm A / B / C | Baseline κ=0-Intervention aus / echte Sticky-Map / Partner-Shuffle |
| Population | 27 Agenten (9/9/9) |
| `ℓ_ij` | Skalar aus Ledger `E[i][j]` (Komponente) |
| Größe L1 | `avg_latency` (primär) |
| Größe L2 | `interaction_count` (parallel, eigene Mehrheitsregel) |

---

## 1. Hypothesen

**H1 (je Größe L1, L2 getrennt):** Kopplung
`interval_i = base_i · (1 + κ · s(ℓ_ij*))` erzeugt bei hinreichendem κ einen Gate-Abstand
B vs. C und hält Arm C nach Mehrheitsregel nicht mehrheitlich `COUPLED`, **und**
die Per-κ-Vorbedingung für `ℓ` bleibt auf Arm B erhalten.

**H0:** Kein Gate-Abstand, oder Vorbedingung geht unter Intervention verloren.

### 1.1 Riskante Vorhersage (§1.1)

**Arm C bleibt bei allen κ-Stufen mit erhaltener Vorbedingung `NO_COUPLING`
nach Gate + Mehrheitsregel (≥4/6 Seeds).**

κ-Stufen mit `PRECONDITION_LOST` zählen **nicht** gegen §1.1 und **nicht** für
κ\* / Form — sie werden separat ausgewiesen.

---

## 2. Design

### 2.1 Kopplungsgrößen

| ID | Komponente | Rolle | Begründung |
|----|------------|------|------------|
| **L1** | `avg_latency` | **primär** | beschränkt, Dynamik in beide Richtungen |
| **L2** | `interaction_count` | parallel | Pass in Abnahme; monoton → Detrending-Risiko; getrennt auswerten |

**Normierung für Kopplungseingang** (**BINDEND: σ**):

```text
σ_ℓ, μ_ℓ  = Stichproben-σ / Mittel über Sticky-Kanten am Freeze-Tick (Arm-B-Map)
s(ℓ)      = clip( ℓ / (σ_ℓ + ε) , 0, 1 )     # ε = 1e-9; Größen ≥ 0
MAE_norm  = MAE_raw / (σ_ℓ + ε)             # Schwelle weiterhin ≥ 0.05
```

### 2.2 Arme

| Arm | Mechanik |
|-----|----------|
| **A** | `κ = 0` auf der Interventionsformel; Ledger schreibt weiter; Sticky-Map M |
| **B** | `κ > 0`; `ℓ_ij*` von echter Sticky-Zuordnung M |
| **C** | `κ > 0`; Delivery bleibt auf M; Kopplung liest `ℓ` unter Partner-Permutation π(M) (wie E_ij §2.4) |

### 2.3 κ-Raster und Seeds (neu)

| Parameter | Wert |
|-----------|------|
| `κ` | `{0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}` |
| Seeds | `{20261301 … 20261306}` |
| `warmup_ticks` | 32 |
| `cycles` | 512 |
| Ledger | `KANTEN_LEDGER_v1` (γ=0.05, Update nur bei Interaktion) |

Zwei parallele Sweep-Spuren: eine mit L1, eine mit L2 (gleiche Seeds/κ; getrennte
Artefakte und Mehrheitsregeln).

### 2.4 Per-κ-Vorbedingung (bindend)

Nach jedem Zellenlauf (Seed × κ × Größe × Arm B-Maßfenster):

1. Berechne S-S und S-G für `ℓ` auf Arm-B-Trace (gegen π(M) wie Abnahme).  
2. Bestehen beide → Zelle ist **vorbedingungs-intakt**; Gate B vs. C auswertbar.  
3. Scheitert mindestens eines → Zellenlabel **`PRECONDITION_LOST`**.  
   - Keine Umdeutung in `NO_COUPLING` oder `COUPLED`.  
   - Zählt nicht für κ\*, Form, oder §1.1-Mehrheit.

Wenn Selektivität genau dort verschwindet, wo der B↔C-Übergang läge: **interessantester
Befund** der Studie — endogene Homogenisierung durch die Intervention selbst.

---

## 3. Schwellen und Gate

Kontinuität zu `KOPPLUNG_EIJ_v1` §3 (Zahlen bei BINDEND bestätigen, nicht nach Daten senken):

| Regel | Wert |
|-------|------|
| S-S (normiert) | `≥ 0.05` |
| S-G | Median `|ρ| ≤ 0.90` (`n_corr ≥ 14`, sonst Vorbedingung nicht prüfbar → `PRECONDITION_LOST` oder `UNTESTABLE` je Zelle) |
| Gate COUPLED | wie E_ij §3.1 (vier Bedingungen) |
| Mehrheit | ≥ 4/6 Seeds |
| Gate B vs. C | ≥ 4/6 Seeds Abstand |

Auswertung **getrennt** für L1 und L2.

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | κ=0-Bestätigung auf **neuen** Seeds scheitert (optionaler Pre-Sweep-Check) |
| `PRECONDITION_LOST` | (Zellen-/Stufen-Label) Selektivität unter κ verloren |
| `KOPPLUNG_INVALID` | §1.1: Arm C mehrheitlich `COUPLED` auf vorbedingungs-intakten κ |
| `NO_COUPLING` | kein intaktes κ erfüllt Gate |
| `COUPLED_EMERGENT` | Gate + Form auf intakten κ |
| `COUPLED_FORCED` | Gate ohne Form auf intakten κ |

Gesamtverdict je Größe: aus intakten κ-Stufen; Anteil `PRECONDITION_LOST` wird
explizit berichtet (kein „Fehlschlag“, aber kein Kopplungsbeleg).

---

## 5. Ablauf (ABGESCHLOSSEN)

1. ~~Freigabe `DRAFT → BINDEND`~~ **erledigt 2026-08-25**  
2. ~~κ=0 Spot-Check Seed `20261301` (L1+L2)~~ **PASS**  
3. ~~Sweep L1 und L2~~ **beide `KOPPLUNG_INVALID` (§1.1 bei κ=0.2)**  
4. ~~Freeze Artefakte + Verdict je Größe~~ siehe `kopplung_ledger_v1/ABSCHLUSS.md`  
5. Keine Nachjustierung von Schwellen / Normierung / Labels nach Datenblick  

## 6. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **DRAFT** | Protokoll inkl. `PRECONDITION_LOST` und Per-κ-Regel |
| **BINDEND** | erreicht 2026-08-25 |
| **Abgeschlossen** | **erreicht 2026-08-25** — Verdict versiegelt |

**Runner:** `scripts/run_kopplung_ledger_v1_sweep.py`  
**Artefakte:** `agents_b2g/emergence/kopplung_ledger_v1/`

---

## 7. Checkliste DRAFT

| Anforderung | Status |
|-------------|--------|
| Dreiarm A/B/C | ✅ §2.2 |
| L1 `avg_latency` primär, L2 parallel | ✅ §2.1 |
| MAE/s(ℓ) streuungsnormiert | ✅ §2.1 |
| Per-κ S-S/S-G | ✅ §0.3, §2.4 |
| Label `PRECONDITION_LOST` | ✅ §0.3, §4 |
| HARKing Abnahme-Datensatz | ✅ Kopf |
| Neue Seeds | ✅ §2.3 |
| §1.1 nur auf intakten κ | ✅ §1.1 |
