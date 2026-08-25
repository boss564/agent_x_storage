# Emergenz — Geschlossener Kreis (φ_L + R_ij): Pre-Registration

**Arbeitstitel:** `CLOSED_LOOP_KOPPLUNG_v0`  
**Status:** **DRAFT** — Freeze F1–F3 geschlossen · Bindung `DRAFT → BINDEND` ausstehend · **kein Sweep vor BINDEND**  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) auf **Reaktions-Heterogenität**  
**Vorläufer:** `docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md` (SCHRITT2_PASS) · Serie-Schluss `docs/KOPPLUNG_SERIE_ABSCHLUSS.md`  
**Capture:** `agents_b2g/emergence/closed_loop_capture.py`  
**Geplante Artefakte:** `agents_b2g/emergence/closed_loop_kopplung_v0/`

### Bindungs-Vermerk (bei Freigabe ausfüllen)

```text
Status: DRAFT  →  (BINDEND ausstehend)
Dokument: docs/CLOSED_LOOP_KOPPLUNG_v0_PREREG.md
Datum: —
Freeze: F1 η=1.0 · F2 LedgerBook.update only · F3 A∧B∧C-Schwellen Schritt 2
Arme: A/B/C
Seeds: 20261601…06 (Screening 20261501–03 gesperrt)
Per-κ-Nachprüfung: Batterie A∧B∧C auf R_ij
PRECONDITION_LOST: bindend
§1.1 / κ*: nur vorbedingungs-intakte κ
```

### HARKing-Sperre (strikt)

Nicht für Hypothesentests dieser Studie verwenden:

- `agents_b2g/emergence/closed_loop_v0/` (Schritt-2-Screen, Seeds `20261501–03`)
- `agents_b2g/emergence/edge_individuation_v0/`
- `agents_b2g/emergence/r_ij_screen_v0/`
- `agents_b2g/emergence/kopplung_ledger_v1/` und alle versiegelten Kopplungs-Artefakte
- `agents_b2g/emergence/kanten_ledger_v1/`, `partnerselect_screen_v1/`, `eij_*`, `state_screen/`, `kopplung_full/`, `reputation_i1/`

Neue Seeds · neue Läufe · neue Artefakte unter `agents_b2g/emergence/closed_loop_kopplung_v0/`.

### Abgrenzung zur geschlossenen Serie

`KOPPLUNG_SERIE_ABSCHLUSS.md` versiegelt den Strang „partnerselektive **Eingangsgröße** reicht nicht“.  
Diese Pre-Reg ist ein **neuer Strang**: partnerselektive **Antwort** (`R_ij` auf φ_L) im geschlossenen Kreis. Keine Re-Analyse versiegelter Datensätze.

---

## 0. Zweck und Abgrenzung

### 0.1 Ausgangslage

| Stufe | Befund |
|-------|--------|
| Serie | Auch gebautes Ledger → `KOPPLUNG_INVALID` (Antwort partnerblind) |
| φ_L | `S_ij = avg_latency` · `PHI_L_SOURCE_PASS` (\|ρ\|≈0.35) |
| Schritt 2 | `R_ij = a_i(1+γ_ij)(ℓ_ij−b_i)` · Batterie **A∧B∧C** 3/3 · `RESPONSE_HETEROGENEOUS` |

### 0.2 Forschungsfrage

Erzeugt der geschlossene Kreis (φ_L + `R_ij`-Rekursion) unter Intervention `κ` einen
**Kopplungseffekt nach §1.1** — messbare Differenz Arm B (echte Partner) vs. Arm C
(permutierte Partner) — **während** die Reaktions-Batterie A∧B∧C je κ erhalten bleibt?

### 0.3 Vorbedingung (bindend, per κ)

Die Vorbedingung ist die **Reaktions-Batterie** aus Schritt 2 (nicht nur Ledger-Selektivität):

| Schicht | Definition (Freeze F3) | Schwelle |
|---------|------------------------|----------|
| **A** | Median \|ρ\| der Sticky-`R`-Serie zum Schwarm-Mittel | ≤ 0.90 (`n_corr ≥ 14`) |
| **B** | MAE unter Partnerpermutation auf Sticky-`R`, `mae_norm = MAE/(σ_R+ε)` | ≥ 0.05 |
| **C** | Antwort-Heterogenität: mean \|ΔR(S1)−ΔR(S2)\| | ≥ 0.05 |

**Regel:** Nach jedem Zellenlauf (Seed × κ × Arm-B-Maßfenster) Batterie erneut prüfen.

- Bestehen A∧B∧C → Zelle **vorbedingungs-intakt**; Gate B vs. C auswertbar.  
- Scheitert mindestens eine Schicht → Zellenlabel **`PRECONDITION_LOST`**.  
  - Keine Umdeutung in `NO_COUPLING` / `COUPLED`.  
  - Zählt **nicht** für κ\*, Form oder §1.1-Mehrheit.

---

## 1. Hypothesen

**H1:** Bei hinreichendem `κ` entsteht Gate-Abstand B vs. C, Arm C bleibt nach Mehrheitsregel
nicht mehrheitlich `COUPLED`, **und** die Per-κ-Batterie bleibt auf Arm B erhalten.

**H0:** Kein Gate-Abstand, oder Batterie geht unter Intervention verloren (`PRECONDITION_LOST`).

### 1.1 Riskante Vorhersage (§1.1)

**Arm C bleibt bei allen κ-Stufen mit erhaltener Vorbedingung `NO_COUPLING`
nach Gate + Mehrheitsregel (≥4/6 Seeds).**

κ-Stufen mit `PRECONDITION_LOST` zählen **nicht** gegen §1.1 und **nicht** für κ\* / Form.

---

## 2. Design

### 2.1 Dynamik (Freeze F1–F2)

\[
R_{ij}=a_i(1+\gamma_{ij})(\ell_{ij}-b_i),\quad \ell=\texttt{avg\_latency}
\]

\[
\gamma_{ij}\leftarrow\tanh(\gamma_{ij}+\eta\cdot\delta_{ij}),\quad
\delta_{ij}=R_{ij}-\bar R_{i\cdot},\quad \eta=\mathbf{1.0}
\]

- **F1:** `η = 1.0` (Warmup Median\|δ\| < 0.1, Cap; dokumentiert Schritt-2 Full-Screen).  
- **F2:** `ℓ_ij` nur über bestehendes `LedgerBook.update` bei Interaktion (EWMA). Kein direktes \(R\to\ell\).  
- **P_i:** Gas A1…A9 → nur \(\mathbf{P}_1\ldots\mathbf{P}_9\) (keine Typ-Paar-Matrix).

**Kopplungseingang:**

```text
h_ij = clip( |R_ij| / (|R_ij| + 1) , 0, 1 )
interval_i = base_i · (1 + κ · h_ij*)
```

wobei `h_ij*` je Arm aus echter bzw. permutierter Partnerzuordnung kommt.

### 2.2 Arme

| Arm | Mechanik |
|-----|----------|
| **A** | `κ = 0` auf der Interventionsformel; Ledger + γ-Rekursion laufen; Sticky-Map M |
| **B** | `κ > 0`; `h_ij*` von echter Sticky-Zuordnung M |
| **C** | `κ > 0`; Delivery bleibt auf M; Kopplung liest `h` / `R` unter Partner-Permutation π(M) |

### 2.3 κ-Raster und Seeds (neu)

| Parameter | Wert |
|-----------|------|
| `κ` | `{0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}` |
| Seeds | `{20261601 … 20261606}` |
| Screening-Seeds | `{20261501…03}` **gesperrt** (HARKing) |
| `warmup_ticks` | 32 |
| `cycles` | 512 |
| η | **1.0** (F1) |

Optional vor Sweep: κ=0-Spot-Check Seed `20261601` (Batterie A∧B∧C) — Scheitern → `SIGNAL_BLIND`, Sweep gesperrt.

### 2.4 Per-κ-Vorbedingung

Siehe §0.3. Auswertung nur auf **intakten** κ.

---

## 3. Schwellen und Gate

Kontinuität zu `KOPPLUNG_EIJ_v1` / `KOPPLUNG_LEDGER_v1` §3 (Zahlen bei BINDEND bestätigen, nicht nach Daten senken):

| Regel | Wert |
|-------|------|
| Batterie A | Median \|ρ\| ≤ 0.90, `n_corr ≥ 14` |
| Batterie B | `mae_norm ≥ 0.05` |
| Batterie C | mean \|ΔΔR\| ≥ 0.05 |
| Gate COUPLED | (1) `p < α` (2) `D_dyn > 0` (3) `r_B − r_C ≥ Δr_min` (4) `r_B ≥ r_floor` |
| `α` | 0.05 · `n_surrogates` = 200 |
| `Δr_min` | 0.10 |
| `r_floor` | 0.34 |
| Mehrheit | ≥ 4/6 Seeds |
| Gate B vs. C | ≥ 4/6 Seeds Abstand |

`κ*` / Form nur auf vorbedingungs-intakten κ.

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | κ=0-Spot auf neuen Seeds: Batterie scheitert |
| `PRECONDITION_LOST` | (Zellen-/Stufen-Label) Batterie A∧B∧C unter κ verloren |
| `KOPPLUNG_INVALID` | §1.1: Arm C mehrheitlich `COUPLED` auf intakten κ |
| `NO_COUPLING` | kein intaktes κ erfüllt Gate |
| `COUPLED_EMERGENT` | Gate + Form auf intakten κ |
| `COUPLED_FORCED` | Gate ohne Form auf intakten κ |

Anteil `PRECONDITION_LOST` wird explizit berichtet (kein Kopplungsbeleg).

---

## 5. Ablauf

1. Freigabe `DRAFT → BINDEND` (dieses Dokument)  
2. Optional: κ=0 Spot-Check Seed `20261601`  
3. Sweep A/B/C × κ × Seeds → `closed_loop_kopplung_v0/`  
4. Freeze Artefakte + Verdict  
5. Keine Nachjustierung von η / Schwellen / Labels nach Datenblick  

## 6. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **DRAFT** | Protokoll + Freeze F1–F3 geschlossen · HARKing-Sperre · Per-κ-Batterie |
| **BINDEND** | ausstehend — ein Wort genügt |
| **Sweep** | erst nach BINDEND |

**Geplanter Runner:** `scripts/run_closed_loop_kopplung_v0_sweep.py` (nach BINDEND)  
**Artefakte:** `agents_b2g/emergence/closed_loop_kopplung_v0/`

---

## 7. Checkliste DRAFT

| Anforderung | Status |
|-------------|--------|
| Frage: Kreis → §1.1? | ✅ §0.2 |
| Hypothese B vs. C | ✅ §1 |
| Vorbedingung Batterie A∧B∧C per κ | ✅ §0.3 |
| `PRECONDITION_LOST` | ✅ §0.3, §4 |
| Freeze F1 η=1.0 | ✅ §2.1 |
| Freeze F2 Ledger.update only | ✅ §2.1 |
| Freeze F3 Schwellen Schritt 2 | ✅ §0.3 |
| Arme A/B/C | ✅ §2.2 |
| Neue Seeds, Screening gesperrt | ✅ §2.3 / HARKing |
| §1.1 / κ* nur intakte κ | ✅ §1.1 |
| Kein Sweep vor BINDEND | ✅ §5–§6 |
