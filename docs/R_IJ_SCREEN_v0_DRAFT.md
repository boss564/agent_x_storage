# R_ij-Screening v0 — Protokoll (kein Pre-Reg)

**Status:** DRAFT · S_i-Probe FULL 2026-08-25 · **`S_COMMON` (sticky)** · Pre-Reg: NEIN  
**Datum:** 2026-08-25  
**Compare R:** `R_IJ_SCREEN_COMPARE.json` · **S-Probe:** `S_I_COMMONALITY_FULL_ERGEBNIS.md`

### S_i-Commonality (vor R-Transform)

| Größe | Median \|ρ\| (3 Seeds) | Lesart |
|-------|----------------------:|--------|
| sticky-ℓ vs ē | **0.348** | Kante selektiv (bekannt) |
| S_i pairwise (Agenten) | **0.050** | Sender-Mittel **nicht** global sync |
| sticky-S vs ē | **0.964** | **`S_COMMON`** — viele Sticky-Keys teilen dieselbe `S_i`-Serie |

Schicht-A-Fail bei v0.2: nicht weil alle Agenten dasselbe sehen, sondern weil die
**Sticky-Panel-Konstruktion** dieselbe `S_i`-Zeitreihe mehrfach einträgt (`ρ(a·x,x)=1`).
Reaktionsschicht kann das nicht lösen. Engpass = Topologie / Key-Fächerung, nicht `f_i`.
Nächster Strang wäre Topologie — kein weiterer R-Screen, keine Pre-Reg hier.  
**Folgeprotokoll:** `docs/EDGE_INDIVIDUATION_v0_DRAFT.md` (φ aus Ledger · Rauschen nur Kontrolle · ρ=Befund · A∧B∧C).

### Amend v0.1 → Vorbehalt → v0.2

| Formel | Form | Schicht B | Schicht C (Vorhersage) |
|--------|------|-----------|-------------------------|
| v0 Amplitude | \(f(S\cdot(1+\gamma))\) | ΔR≡0 | — |
| **v0.1** Schwelle | \(f_i(S)-\theta_i(1+\gamma_{ij})\) | PASS | **FAIL** (ΔR=θ\|Δγ\|, S-unabhängig) |
| **v0.2** Empfindlichkeit | \(a_i(1+\gamma_{ij})(S-b_i)\) | PASS | **PASS** (ΔR∝\|S−b\|) |

v0.1 erzeugt einen **konstanten Kantenversatz**. Unter Arm-C-Permutation bleibt die
*Menge* der Versätze gleich — strukturell dasselbe Muster wie die Serie (Eigenschaft
belegt ≠ Eigenschaft, die der Kontrollarm prüft). Deshalb Schicht C **vor** Pre-Reg.

\[
R_{ij}^{(0.2)} = a_i\,(1+\gamma_{ij})\,(S - b_i),
\quad \gamma_{ij}=\ell_{ij}/(\sigma+\varepsilon),\quad
a_i=g_i,\quad b_i=\theta_i\cdot\sigma
\]

(γ aus Ledger, erworben; keine Typ-Paar-Matrix.)

### Was dieses Dokument ist

Isolierter Pre-Check: Ist die **Antwort** `R_ij` partnerabhängig?  
Erst bei PASS beider Schichten (unten) wäre eine *neue* Pre-Reg mit neuer Fragestellung zulässig.

### Was dieses Dokument nicht ist

- Keine Pre-Registration  
- Kein κ-Raster, keine Arme A/B/C-Kopplungsstudie  
- Keine Typ-Paar-Matrix, keine Domänen-Etiketten in der Auswertung  
- Kein HARKing auf versiegelte Kopplungs-/Ledger-Datensätze

---

## 0. Diagnose (fest)

Der Ledger-Sweep hatte partnerselektiven **Eingang** und trotzdem Arm-C-Kohärenz.
Die Übertragungsfunktion ist partnerblind, nicht der Eingang:

\[
R_{ij} = f_i\!\bigl(S_j \cdot W_{ij}\bigr)
\quad\text{mit bislang identischem } f \text{ für alle } i.
\]

---

## 1. Constraints (bindend für v0 und jede Folge)

| # | Regel |
|---|--------|
| 1 | **Keine Typ-Paar-Matrix.** `Filter_i` / \(\mathbf{P}_i\) sind Agenten-Eigenschaften. Wer wen dämpft, ergibt sich; steht nicht im Code. |
| 2 | **Antwort-Heterogenität zuerst.** Kein κ bevor `R_ij`-Screen PASS. |
| 3 | **Freiheitsgrade.** \(\mathbf{P}_i\) und ggf. \(\gamma_{ij}\)-Seeds **vor dem Lauf fest**, abgeleitet (Gas/Ledger), nicht gesweept. |
| 4 | **Nomenklatur.** Nur \(\mathbf{P}_1\ldots\mathbf{P}_9\) / Vektoren. Keine Enneagramm-/Rollen-Psychologie in Logs oder Abschluss. |

---

## 2. Zielgröße

Zwei Schichten (beide nötig für „beide Seiten“):

### 2.1 Schicht A — kantige Antwort (MAE unter Permutation)

\(S_i\) = Mittel der Ledger-ℓ des Senders; \(\gamma_{ij}\) aus Kanten-ℓ; Formel je Version.
S-S ∧ S-G wie I1 (MAE_norm ≥ 0.05, Median \(|\rho|\leq 0.90\), \(n_\mathrm{corr}\geq 14\)).

### 2.2 Schicht B — Identical-S-Probe

Identisches \(S_i\), Partner \(j\neq k\) (inkl. π(M)): \(\overline{\Delta R}\geq 0.05\).

### 2.3 Schicht C — Signalabhängigkeit von ΔR (bindend vor Pre-Reg)

Zwei Pegel \(S_1\neq S_2\) (Q1/Q3 der Sender-Mittel), gleiche Partner-γ:

\[
\big|\Delta R_i(S_1) - \Delta R_i(S_2)\big|
\quad\text{Mittel} \geq 0.05
\]

v0.1: analytisch ≈ 0 → Label `OFFSET_ONLY`.  
v0.2: analytisch ∝ \|S−b\| → kann PASS.

---

## 3. Ableitung \(\mathbf{P}_i\) (keine freien Stellschrauben)

Gas-Profile `A1…A9` → neun feste Vektoren \(\mathbf{P}_1\ldots\mathbf{P}_9\), zyklisch auf Agenten-IDs (deterministisch, seed-unabhängig):

| Ableitung | Formel (v0) |
|-----------|-------------|
| \(g_i\) | \(\mathrm{fee}_i / \overline{\mathrm{fee}}\) |
| \(\theta_i\) | \(1/(1 + \mathrm{initial}_i/10)\) |
| \(s_i\) | \(\min(1,\mathrm{initial}_i/100)\) |

Keine Paar-Regeln. Keine Nachjustierung nach Datenblick in v0.

---

## 4. Laufparameter (Screen only)

| Parameter | Wert |
|-----------|------|
| Seeds | `{20261401, 20261402, 20261403}` (neu; keine Alt-Artefakte) |
| κ | 0 (keine Interventionskopplung) |
| warmup / cycles | 32 / 512 (`--fast`: 8 / 64) |
| Ledger-Komponente | `avg_latency` (L1) |
| Artefakte | `agents_b2g/emergence/r_ij_screen_v0/` |

---

## 5. Labels

| Label | Bedeutung |
|-------|-----------|
| `RESPONSE_SCREEN_FAIL` | Schicht A gescheitert |
| `TRANSFER_PARTNERBLIND` | Schicht B gescheitert |
| `OFFSET_ONLY` | A∧B, C fail — konstanter Versatz (v0.1) |
| `RESPONSE_HETEROGENEOUS` | A∧B∧C — Pre-Reg-Kandidat (v0.2) |

Pre-Reg **nur** bei `RESPONSE_HETEROGENEOUS`.

---

## 6. Nächster Schritt

1. Screen `--formula both` (v0.1 vs v0.2, Schicht C).  
2. Nur wenn v0.2 = `RESPONSE_HETEROGENEOUS`: neue Pre-Reg (neuer Strang).  
3. Kein κ vor A∧B∧C.

**Runner:** `scripts/run_r_ij_screen_v0.py --formula both`
