# Emergenz — Relationale Kanten-Kopplung (E_ij): Pre-Registration

**Arbeitstitel:** `KOPPLUNG_EIJ_v1` · **DRAFT 1**  
**Status:** **BINDEND → KOPPLUNG_INVALID** — 2026-08-25 · I1_PASS · κ-Sweep final · §1.1 widerlegt.  
**Freigabe zur DRAFT-Initiierung:** 2026-08-25 (Pfad 1).  
**Architektur-Referenz:** `agents_b2g/emergence/ARCHITEKTUR_REFERENZ_EIJ.md` (keine Hypothese).  
**Vorgänger (geschlossen):** Queue `KOPPLUNG_INVALID` · Reputation `I1_FAILED` · Screening `NONE_CLOSE` / Ausgang 3.

### HARKing-Sperre (strikt)

Folgende Datensätze dürfen **nicht** für Hypothesentests dieser Studie verwendet werden:

- `agents_b2g/emergence/state_screen/`
- `agents_b2g/emergence/kopplung_full/`
- `agents_b2g/emergence/reputation_i1/`

Neue Läufe · neue Seeds · neue Artefakte.

---

## Ablauf (nach Bindung)

1. DRAFT vervollständigen → Freigabe `DRAFT → BINDEND`  
2. Adapter (Teil-2-Kanten-Speicher minimal) + **nur** I1-Edge  
3. I1 PASS → κ-Sweep · I1 FAIL → `SIGNAL_BLIND`  

**BINDEND.** Adapter + I1-Edge freigegeben. Kein Sweep vor I1 PASS.

---

## 0. Zweck und Abgrenzung

### 0.1 Ausgangslage

Knotenbasierte Größen `S_i` (Queue, Honor, 18 Screening-Dimensionen) erfüllen keine
Partnerselektivität unter Permutation. Partnerselektivität muss **konstruktional** in
gerichteten Kanten `E_ij` liegen.

### 0.2 Forschungsfrage

Erzeugt ein relationaler Kanten-Zustand `E_ij ∈ ℝ^k` unter lokaler Taktraten-Kopplung
eine messbare, shuffle-sensitive Struktur (Partnerselektivität auf Graphenebene), die
unter Kanten-Permutation zusammenbricht?

### 0.3 Was „Partnerselektivität auf Kanten“ heißt (Definition)

**Partnerselektivität auf Kanten** liegt vor, wenn:

1. die Verteilung der Kantenmerkmale **heterogen** ist (nicht alle `E_ij` gleich), und  
2. eine **Permutation der Kanten-Zuordnung** (welche Kantenhistorie ein Sender für die
   Kopplung liest) die beobachtete Kopplungs-Eingangszeitreihe messbar ändert, und  
3. die Kantenzeitreihen **nicht** alle dem globalen Kantenmittel folgen.

Das ist die Graph-Analogie zu I1-V / I1-S / I1-G der Knotenstudien — angewendet auf
Kanten, nicht auf Agentenvektoren `S_i`.

### 0.4 Nomenklatur

| Begriff | Bedeutung |
|---------|-----------|
| Arm A / B / C | Studienarme (Baseline / echte Kantenmap / Kanten-Shuffle) |
| Population | 27 Agenten: 9 Provider, 9 Evaluator, 9 Economic |
| Kanten-Segment | gerichtete Paare innerhalb eines Routing-Kanals (z. B. Provider→Evaluator) |
| `E_ij` | Zustandsvektor der gerichteten Kante von Sender `i` zu Empfänger `j` |
| Tensor | je Segment `9 × 9 × k` (Sender × Empfänger × Merkmale); drei Segmente |
| Nicht diese Studie | kommerzieller Pitch-Track; ephemere Worker (Teil 1) als Messknoten |

---

## 1. Hypothesen

**H1:** Lokale Kopplung der Taktrate an ein Kantenmerkmal `e_ij = g(E_ij)` erzeugt bei
hinreichendem Interventionsparameter `κ` eine Graphstruktur / Phasenkohärenz, die unter
**Kanten-Zuordnungs-Permutation** (Arm C) mindestens den Gate-Abstand zu Arm B verliert
und Arm C nicht mehrheitlich `COUPLED` bleibt.

**H0:** Arm B und Arm C bleiben ununterscheidbar — die Kantenmechanik trägt keine
Partnerselektivität (oder erzeugt keine Varianz).

### 1.1 Riskante Vorhersage (nach Bindung eingefroren)

**Arm C bleibt bei allen κ-Stufen `NO_COUPLING` nach Gate §3 + Mehrheitsregel.**

### 1.2 I1-Edge (Voraussetzung)

I1 prüft Kanten-Selektivität **ohne** Taktraten-Intervention (`κ = 0`). Scheitert I1 →
`SIGNAL_BLIND`, kein Sweep.

---

## 2. Design

### 2.1 Kanten-Zustand `E_ij ∈ ℝ^k`

**k = 3** Merkmale (Reihenfolge fix):

| Index | Name | Semantik |
|------:|------|----------|
| 0 | `trust` | kumulierte Erfolgsneigung auf der Kante ∈ [0, 1] (Thompson-Posterior-Mittel) |
| 1 | `risk` | kumuliertes Risiko / Fehlschlag-Gewicht ∈ [0, 1] |
| 2 | `freshness` | `e^(−γ Δt)` seit letztem Update ∈ (0, 1] |

**Primäre Kopplungsgröße (Skalar):**

```
e_ij = trust_ij · freshness_ij · (1 − risk_ij)
e_ij ∈ [0, 1]
```

Keine knotenweiten Aggregate als Eingang. Kein globales Mittel von `trust`.

### 2.2 Update-Regeln (Parameter vorab — Blocker)

#### 2.2.1 Exponentieller Decay

```
E_ij(t) = E_ij(t−1) · e^(−γ Δt) + S_neu
```

komponentenweise auf `trust`/`risk` nach Clip auf [0, 1]; `freshness` wird neu gesetzt.

| Symbol | Wert | Bedeutung |
|--------|-----:|-----------|
| `γ` | **0.05** | pro globalem Tick (`Δt = 1`) · Retention ≈ 0.951 |
| Clip | [0, 1] | verhindert erneute Sättigung analog `H_cap` |

`S_neu`: Ereignisbeitrag §2.2.3. Nach Bindung: `γ` unveränderlich.

#### 2.2.2 Kaltstart — Thompson-Sampling

Für Kante ohne Historie (`E_ij = ∅` / nie aktualisiert):

| Größe | Festlegung |
|-------|------------|
| Prior | **Beta(α₀, β₀) = Beta(1, 1)** (uniform) |
| Sample | `θ ~ Beta(α, β)` je Auswahl unter Kandidaten derselben Rolle |
| Update | Erfolg: `α ← α+1` · Fehlschlag: `β ← β+1` |
| `trust` | Posterior-Mittel `α / (α+β)` nach jedem Update |

Exploration nur bei `∅` oder wenn Sticky-Freeze noch nicht aktiv ist (Warm-up).  
Nach Freeze: keine Neu-Exploration; Map fest (wie Vorgänger-Freeze).

#### 2.2.3 Ereignis → `S_neu` (rollenweise)

| Kante / Ereignis | Erfolg | `S_neu` auf trust | `S_neu` auf risk |
|------------------|:------:|------------------:|-----------------:|
| Provider→Evaluator, Check holds | ja | +0.10 | 0 |
| Provider→Evaluator, Check fails | nein | 0 | +0.10 |
| Evaluator→Economic, Settlement | ja | +0.10 | 0 |
| sonst idle | — | 0 | 0 |

(Gewichte 0.10 vor Bindung fix; keine Nachjustierung nach Datenblick.)

#### 2.2.4 Z3-Kanten-Integration (Studie: vereinfacht)

Für den Emergenz-DRAFT gilt die **logische** Kopplung (Implementierung darf stubben):

```
Kante zulässig ⇔ (Δ = 0,00 € auf der TX) ∧ (risk_ij ≤ risk_limit)
risk_limit = 0.80
```

Verletzung → Fehlschlag-Update (`β++`, risk+), TX wird nicht als Erfolg auf `trust` gebucht.  
Vollständige ZK-Privatsphäre (Architektur §3) ist **außerhalb** dieses DRAFT-Messpfads
(optional später); sie ist keine Sweep-Voraussetzung.

### 2.3 Intervention (Taktrate)

```
interval_i = base_i × (1 + κ · e_ij*)
```

`e_ij*` = Skalar der Sticky-Kante des Senders zum gewählten Partner (Arm B) bzw. zur
**permutierten Kanten-Zuordnung** (Arm C).

Fehlende Kante / `∅`: `e_ij* := 0`.

### 2.4 Shuffle-Kontrolle (Kanten-Zuordnung — nicht Agenten-ID)

Nach Warm-up-Freeze der Sticky-Partner-Map `M: (sender_key, role) → partner_id`:

| Arm | Mechanik |
|-----|----------|
| **A** | `κ = 0`; Kanten dürfen fortgeschrieben werden |
| **B** | echte Map `M`; Kopplung liest `E_{i, M(i)}` |
| **C** | degree-preserving, **rollensegment-interne** Permutation `π` der Partner-Zuordnung; Kopplung liest `E_{i, π(M(i))}` — **dieselbe** Kanten-Historientabelle, anderer Index |

**Wichtig:** Es werden nicht die Agenten-Identitäten umbenannt, sondern welche
**Kantenhistorie** der Sender für `e_ij*` sieht. Das ist die direkte Analogie zur
Diagnose „Permutation ändert das Signal“.

### 2.5 κ-Raster und Seeds (neu)

| Konstante | Wert |
|-----------|------|
| `κ` | {0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2} |
| `run_seeds` | **{20261001 … 20261006}** (disjoint zu Queue/Reputation/Screening) |
| `warmup_ticks` | 32 |
| `cycles` (Sweep) | 512 |
| I1 cycles | 64 |

---

## 3. Schwellen (Gate, Entwurf — vor Bindung bestätigen)

| Konstante | Wert | Herkunft |
|-----------|-----:|----------|
| `N` | 27 | Population |
| `r_random` | 0,1925 | 1/√N |
| `α` | 0,05 | Surrogate |
| `n_surrogates` | 200 | Kontinuität |
| `Δr_min` | **0,10** | bestätigt (Kontinuität; Partnerselektivität-Abstand) |
| `r_floor` | 0,34 | Kontinuität |
| Mehrheit | ≥ 4/6 Seeds | Kontinuität |

### 3.1 Gate `COUPLED` (alle vier)

1. `p < α`  
2. `D_dyn > 0`  
3. `r_B − r_C ≥ Δr_min`  
4. `r_B ≥ r_floor`  

Form-Kriterium analog Vorgänger — erst nach I1 PASS interpretierbar.

---

## 4. I1-Edge — Instrumentationscheck

`κ = 0` · warmup=32 · cycles=64 · seed=`20261001` · Freeze `M` · Auswertung B vs. `π(M)`.

Messobjekt: Skalar `e_ij` über **aktive Kanten** (mindestens ein Update im Messfenster)
bzw. alle Sticky-Kanten der Freeze-Map.

### 4.1 Kriterien (alle Pflicht)

| ID | Kriterium | Schwelle |
|----|-----------|----------|
| **I1E-V** | Stichproben-σ von `{e_ij}` über Sticky-Kanten am Ende des Fensters | `≥ 0.05` |
| **I1E-S** | Mittel über Sender von `MAE_t(e_{i,M(i)}, e_{i,π(M(i))})` | `≥ 0.05` |
| **I1E-U** | Anteil Sticky-Kanten mit ≥1 Update im Messfenster | `≥ 0.40` |
| **I1E-G** | Median über Kanten von `\|corr_t(e_ij(t), ē(t))\|` | `≤ 0.90` |

`ē(t)` = Mittel der Sticky-Kanten-Skalare zur Zeit `t`.  
Weniger als 14 kantenweise corr-fähig → I1E-G Fail.

| Outcome | Folge |
|---------|--------|
| Alle PASS | I1-Edge bestanden → Sweep freigegeben |
| Sonst | `SIGNAL_BLIND` · Ende · keine Parameter-Nachjustierung |

---

## 5. Verdict-Mapping

| Verdict | Bedingung |
|---------|-----------|
| `SIGNAL_BLIND` | I1-Edge scheitert |
| `KOPPLUNG_INVALID` | Arm C mehrheitlich `COUPLED` → §1.1 widerlegt |
| `HOMOGENIZED` | analog Vorgänger |
| `COUPLED_EMERGENT` | Gate + Form |
| `COUPLED_FORCED` | Gate ohne Form |
| `NO_COUPLING` | kein κ erfüllt Gate |

---

## 6. Was bewusst nachgelagert bleibt

- ZK-Privatsphäre produktionsreif (Architektur-Mechanismus 3)  
- Voller Z3/HSM/MPC-Stack in der Messschleife  
- Kommerzieller Pitch / Docker-Track (Pfad 3)  
- Form-Hypothesen Event-κ / Quorum (frühere 2.1–2.3)

---

## 7. Bindungs-Checkliste (offen)

| Punkt | Stand |
|-------|--------|
| Hypothese „Partnerselektivität auf Kanten“ definiert | ✅ §0.3 / §1 |
| I1-Edge auf Kanten/Tensor spezifiziert | ✅ §4 |
| `γ = 0.05` fixiert | ✅ §2.2.1 |
| Thompson-Prior Beta(1,1) fixiert | ✅ §2.2.2 |
| Shuffle = Kanten-Zuordnung π | ✅ §2.4 |
| Seeds {20261001…20261006} | ✅ §2.5 |
| `Δr_min = 0.10` | ✅ §3 |
| Explizite Bindungs-Freigabe | ✅ §8 · 2026-08-25 |

**BINDEND.** Nächster Schritt: Adapter + I1-Edge (kein Sweep).

---

## 8. Freigabe-Vermerk

```text
Status: DRAFT → BINDEND
Datum: 2026-08-25
Studie: KOPPLUNG_EIJ_v1
Bedingung: Sweep erst nach I1-Edge PASS (§4).
Parameter eingefroren: γ=0.05 · Beta(1,1) · risk_limit=0.80 · e_ij-Formel §2.1
HARKing: state_screen / kopplung_full / reputation_i1 gesperrt.
Nächster Schritt: Kanten-Adapter + I1-Edge (kein Sweep).
```

---

## 10. I1-Edge-Ergebnis (2026-08-25)

| Feld | Wert |
|------|------|
| Lauf | warmup=32 · cycles=64 · κ=0 · seed=20261001 |
| Verdict | **`I1_PASS`** |
| I1E-V | PASS (σ ≈ 0.303 ≥ 0.05) |
| I1E-S | PASS (MAE ≈ 0.300 ≥ 0.05) |
| I1E-U | PASS (0.734 ≥ 0.40) |
| I1E-G | PASS (median \|ρ\| ≈ 0.389 ≤ 0.90) |
| κ-Sweep | **freigegeben** (noch nicht ausgeführt) |

Artefakte: `agents_b2g/emergence/eij_i1/`.

---

## 11. κ-Sweep-Abschluss (2026-08-25)

```text
Status: BINDEND → KOPPLUNG_INVALID
I1-Edge: I1_PASS
Verdict: KOPPLUNG_INVALID (§1.1 Arm C Mehrheit COUPLED bei κ=0.6)
Gate B↔C: nirgends ≥4/6 · κ*=None · Form=False
Artefakte: agents_b2g/emergence/eij_sweep/
Keine Nachjustierung.
```
