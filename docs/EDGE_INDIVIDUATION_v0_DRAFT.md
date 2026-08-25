# Edge-Individuierung v0 — Arbeitsprotokoll (kein Pre-Reg)

**Status:** DRAFT · Schritt 1 Quell-Pfad **`PHI_L_SOURCE_PASS`** · Schritt 2 gesperrt · **kein** κ · **kein** Pre-Reg  
**Datum:** 2026-08-25  
**Vorläufer:** `docs/R_IJ_SCREEN_v0_DRAFT.md` · `KANTEN_LEDGER_v1` (PASS) · Serie geschlossen  
**Artefakte:** `agents_b2g/emergence/edge_individuation_v0/EDGE_INDIVIDUATION_phi_L_FULL_*`

### Was dieses Dokument ist

Arbeitsprotokoll für **Schritt 1**: Quell-Entkopplung.  
Engpass: partnerselektives Ledger wurde als **Modulator** eines gemeinsamen `S_i`
verwendet — es hätte das **Signal selbst** sein müssen.

### Was es nicht ist

- Keine ρ-Ziel-Optimierung · kein Produktions-Rauschen · keine Pre-Reg  
- Kein Schritt-2-`R_ij`-Nachweis · kein Eingriff in versiegelte Artefakte  

---

## 0. Befund

| Größe | Median \|ρ\| | Rolle bisher | Rolle richtig |
|-------|-------------:|--------------|---------------|
| sticky-S (`S_i`) | 0.964 | „Signal“ | gemeinsamer Broadcast |
| sticky-ℓ `avg_latency` | **0.348** | γ-Modulator | **Kandidat-Signal** |
| sticky-ℓ `interaction_count` | **0.156** | γ-Modulator | alternativ (Detrending-Risiko) |

`KANTEN_LEDGER_v1` (κ=0, 3 Seeds): beide Ledger-Komponenten S-S∧S-G PASS — deutlich
unter 0,90, nicht grenzwertig.

---

## 1. Constraints (bindend)

| # | Regel |
|---|--------|
| 1 | **Produktion:** Kanten-Signal aus **realer Interaktionshistorie** `(i,j)` — nicht aus Broadcast+Transform. Keine Typ-Paar-Matrix. |
| 2 | **Rauschen:** nur Positivkontrolle des Screenings — nie Produktionsquelle. |
| 3 | **ρ ist Befund, nicht Ziel.** Kein Schrauben bis Schwelle. |
| 4 | **Schicht A** = Median \|ρ\| zum **Schwarm-Mittel** (nicht paarweise). |
| 5 | **Batterie:** A ∧ B ∧ C vor Pre-Reg. |
| 6 | **P_i** erst nach belegter Quell-Entkopplung; abgeleitet, nicht gesweept; Formel vor Pre-Reg spezifizieren. |

**Amend Constraint 1 (Klarstellung):**  
`Path_ij` / Ledger ist die **Signalquelle**, nicht Parameter einer Abbildung von `S_i`.

---

## 2. Warum Broadcast+φ scheitert (Verallgemeinerung)

φ, die die **Identität** von `S_i` erhalten (Versatz, Skalierung, Verzögerung — glatt,
invertierbar, Varianz von `S_i` intakt), können sticky-|ρ| nicht brechen, wenn `S_i`
dominiert. Dekorrelieren tut nur Information**zerstörung** — genau das Rauschen
(Positivkontrolle 0,49–0,72), das als Prod unzulässig ist.

| Transformation | sticky \|ρ\| | Warum |
|----------------|-------------:|-------|
| raw `S_i` | 0.964 | gemeinsames Signal |
| Versatz / v0.1 | — | ρ versatzinvariant / Schicht C |
| φ₀ `S_i(1+γ)` | 0.885 | skaleninvariant — *fast nicht* entkoppelt |
| φ₁ `S_i(t−τ)` | 0.967 | hohe Autokorrelation → Delay ≈ Identität |
| Noise-Ctrl | 0.49–0.72 | zerstört Information — nur Instrument-Check |
| **ℓ_ij selbst** | **0.35 / 0.16** | **nicht** aus `S_i` abgeleitet |

```text
bisher   S_ij = φ(S_i, γ_ij)     γ aus Ledger, S gemeinsam   →  |ρ| ≥ 0.885
statt    S_ij = ℓ_ij             Ledger IST das Signal       →  |ρ| = 0.348 / 0.156
```

Vier Ebenen (Amplitude, Versatz, Verstärkung, Zeitachse) suchten eine Transformation,
die aus einem gemeinsamen Signal ein kantenspezifisches macht. Die Größe, die das
**ohne** Transformation erfüllt, lag daneben — in der falschen Rolle (Modulator).

---

## 2.1 Kandidat φ_L — Ledger *ist* das Signal

\[
S_{ij}(t) \;=\; \ell_{ij}(t)
\quad\text{(primär: }\texttt{avg\_latency}\text{)}
\]

| Komponente | sticky \|ρ\| | Hinweis |
|------------|-------------:|---------|
| **`avg_latency`** | 0.348 | beschränkt, bidirektional — **primäre** Signalquelle |
| `interaction_count` | 0.156 | monotoner Zähler — Detrending-Risiko (Kuramoto-Falsch-Positiv); nicht primär |

Kein neues Erfinden: bereits vermessen (`KANTEN_LEDGER_v1` + Edge-Probe sticky-ℓ).  
Übergang: **Broadcast+Transform → Per-Edge-Signal-Generation**.

---

## 2.2 Geschlossener Kreis (vor „Schritt 1 erledigt“)

Wenn `S_ij = ℓ_ij` und das Verhalten der Agenten wiederum `ℓ_ij` verändert, gibt es
**keinen exogenen Antrieb** mehr. Das ist nicht per se falsch — selbstorganisierende
Systeme sehen so aus —, verschiebt aber, was eine spätere Kopplungsstudie misst:

| Früher (Broadcast) | Mit φ_L |
|--------------------|---------|
| Regeln sich Agenten auf *fremde* Signale ein? | Organisiert sich die *Interaktionshistorie* selbst? |

Das muss in der Pre-Reg (Schritt 3) explizit sein — nicht als Überraschung im Sweep.

---

## 3. Sequenz

```text
Schritt 1 (dieses Dokument):  S_ij = ℓ_ij (Quelle) — PHI_L_SOURCE_PASS (Runner)
Schritt 2:                     R_ij-Screening A∧B∧C auf Produktions-S_ij — GESPERRT
Schritt 3:                     Pre-Reg nur wenn 1 ∧ 2 PASS (+ geschlossener Kreis)
```

| Schritt | Tor | Stand |
|---------|-----|-------|
| **1** | Prod φ_L; sticky-\|ρ\| von `S_ij=ℓ(t)` < 0.90; Instrument ok | **PASS** 2026-08-25 |
| **2** | `RESPONSE_HETEROGENEOUS` | gesperrt |
| **3** | Pre-Reg + Kreis dokumentiert | gesperrt |

**Status Schritt 1:** Quell-Entkopplung im Runner-Pfad technisch belegt (`--mode phi_L`).  
Geschlossener Kreis relevant ab Schritt 3. Kein Nachjustieren von φ₀/φ₁/τ.

---

## 4. Probe-Zahlen (kein Fit)

### 4.1 Broadcast+Transform (gescheitert)

| Lauf | sticky median \|ρ\| |
|------|-------------------:|
| raw `S_i` | 0.964 |
| φ₀ Scale | 0.885 |
| φ₁ Delay | 0.967 |
| Noise-Ctrl | 0.49–0.72 (`SCREEN_SEES_NOISE`) |

### 4.2 φ_L Runner-Pfad — FULL `--mode phi_L` 2026-08-25

| Seed | φ_L \|ρ\| (`S_ij=ℓ_ij(t)`) | <0.90 |
|-----:|---------------------------:|:-----:|
| 20261401 | **0.348407** | ✓ |
| 20261402 | **0.348407** | ✓ |
| 20261403 | **0.348407** | ✓ |

Mittel = 0.348407 · T=512 · n_corr=64 · Label **`PHI_L_SOURCE_PASS`**.  
Identisch zum statischen Kanten-Ledger-Befund — als **dynamischer** Strom im Runner gesichert.

**Runner:** `scripts/run_edge_individuation_probe.py --mode phi_L`  
**Nächstes:** Schritt 2 — Spec `docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md`  
(`R_ij`-Screening A∧B∧C auf φ_L) — nicht Pre-Reg.

---

## 5. Labels

| Label | Bedeutung |
|-------|-----------|
| `SOURCE_MEASURED` | Panel gelaufen, ρ berichtet |
| `SCREEN_SEES_NOISE` / `SCREEN_BLIND` | Positivkontrolle |
| `PHI_L_SOURCE_PASS` | `S_ij=ℓ_ij(t)` im Runner \|ρ\|<0.90 (Schritt 1) |
| `STEP1_BLOCKED` | Quell-Pfad nicht belegt |
| `RESPONSE_HETEROGENEOUS` | Schritt 2 PASS |
| `PRE_REG_BLOCKED` | 1 oder 2 fehlt |

