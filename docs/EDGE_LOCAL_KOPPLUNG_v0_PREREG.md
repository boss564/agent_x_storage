# Emergenz — Edge-Local Coupling (κ_ij, wechselseitig): Pre-Registration (**BINDEND**)

**Arbeitstitel:** `EDGE_LOCAL_KOPPLUNG_v0`  
**Status:** **BINDEND** — 2026-08-26 · Freigabe User · Sweep freigegeben  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) — **neuer Strang** (nicht Fortsetzung der geschlossenen Serie)  
**Capture:** `agents_b2g/emergence/edge_local_kopplung_capture.py`  
**Runner:** `scripts/run_edge_local_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/edge_local_kopplung_v0/`

### Bindungs-Vermerk

```text
Status: DRAFT → BINDEND
Dokument: docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md
Datum: 2026-08-26
Freeze: F1–F5 (§2)
Arme: A/B/C
Seeds: 20261801…06 (ältere Seeds gesperrt — HARKing)
Spot: 20261801
Per-κ-Nachprüfung: Batterie A∧B∧C auf R_ij ∧ Reziprozität
PRECONDITION_LOST / RECIPROCITY_LOST: bindend
§1.1 / κ*: nur vorbedingungs-intakte κ
Canonical ℓ: trimmed_m7 (F4)
Reziprozität: ACK/Receipt (F5), Gate ≥ 0.3
Gate: Δr_min=0.10, r_floor=0.34, ≥4/6, α=0.05
```
### HARKing-Sperre (strikt)

Nicht für Hypothesentests / Gate-Auswertung dieser Studie verwenden:

- `agents_b2g/emergence/closed_loop_kopplung_v0/` und `docs/CLOSED_LOOP_KOPPLUNG_v0_PREREG.md` (Verdict `KOPPLUNG_INVALID`)
- `agents_b2g/emergence/closed_loop_v0/`, `edge_individuation_v0/`, `r_ij_screen_v0/`
- `agents_b2g/emergence/kopplung_ledger_v1/`, `eij_*`, `kopplung_full/`, `reputation_i1/`
- `agents_b2g/emergence/m7_spike_v0/`, `m7_filter_v0/`, `reciprocity_ack_v0/`
  (Engineering-Freeze-Fakten dürfen **zitiert** werden; Zahlen nicht als Sweep-Outcome übernehmen)
- Alle Seeds ≤ `20261799` für Sweep-/Gate-Zellen

Neue Seeds · neue Läufe · neue Artefakte unter `agents_b2g/emergence/edge_local_kopplung_v0/`.

### Abgrenzung zur geschlossenen Serie

`docs/KOPPLUNG_SERIE_ABSCHLUSS.md` versiegelt:

> Globale Modulation `1+κ·h` erzeugt Kohärenz netzwerk-weit — Arm C koppelt mit.

Diese Pre-Reg ist der **neue Strang**, den der Abschluss explizit freihält:

> Welche Kopplungsdynamik erzeugt **kanten-spezifische** Kohärenz statt
> netzwerk-weiter Kohärenz?

Architekturwechsel: **κ_ij auf gerichteter Kante + wechselseitige Reaktion**, nicht erneutes κ-Raster auf `1+κ·h`.

---

## 0. Zweck und Abgrenzung

### 0.1 Freeze-Fakten (Engineering → Architektur, keine Hypothese)

| Fakt | Quelle | Rolle hier |
|------|--------|------------|
| ACK/Receipt → `frac_sticky_via_ledger` Median **1.0** | `b9da5efe` · `reciprocity_ack_v0` | Vorbedingung Wechselseitigkeit messbar |
| Canonical ℓ-Intake: **`trimmed_m7`** (MAD + oberes 10 %-Trim) | `ec524fc9` · `m7_filter_v0` · Gate `M7_PRESERVES_FIT` | F2 / F4 |
| Batterie A∧B∧C auf `R_ij` (Freeze F3 Schritt 2) | `CLOSED_LOOP_RESPONSE_v0_DRAFT` | Per-κ-Vorbedingung |
| Global `1+κ·h` → `KOPPLUNG_INVALID` (§1.1) | `CLOSED_LOOP_KOPPLUNG_v0` | Motiv: Architektur wechseln, nicht Schwellen |

### 0.2 Forschungsfrage

Erzeugt eine **kanten-lokale** Intervention `κ_ij` auf echter Sticky-Kante `(i,j)`
mit **wechselseitiger** Topologie (Rückkante `(j,i)` in Sticky+Ledger) einen
**Gate-Abstand Arm B ↔ Arm C** — messbare, shuffle-sensitive Kohärenz —
**während** die Batterie A∧B∧C je κ erhalten bleibt?

### 0.3 Vorbedingung (bindend, per κ)

#### 0.3.1 Reaktions-Batterie (wie Closed-Loop Schritt 2 / F3)

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **A** | Median \|ρ\| Sticky-`R` vs. Schwarm-Mittel | ≤ 0.90 · `n_corr ≥ 14` |
| **B** | `mae_norm = MAE/(σ_R+ε)` unter Partnerpermutation auf Sticky-`R` | ≥ 0.05 |
| **C** | mean \|ΔR(S1)−ΔR(S2)\| (Antwort-Heterogenität) | ≥ 0.05 |

#### 0.3.2 Reziprozität (neu, Strang-Vorbedingung)

| Metrik | Schwelle | Wann |
|--------|----------|------|
| `frac_sticky_via_ledger` | ≥ **0.3** | Spot κ=0 und jeder Seed vor Gate-Auswertung (Median über Seeds ≥ 0.3; pro Seed Bericht) |

**Regel:** Nach jedem Zellenlauf (Seed × κ × Arm-B-Maßfenster):

- Batterie A∧B∧C **und** Reziprozität ≥ 0.3 → Zelle **vorbedingungs-intakt**.  
- Sonst → **`PRECONDITION_LOST`** (keine Umdeutung in `NO_COUPLING` / `COUPLED`).  
- Zählt **nicht** für κ\*, Form oder §1.1-Mehrheit.

---

## 1. Hypothesen

**H1:** Bei hinreichendem `κ` entsteht Gate-Abstand B vs. C (Mehrheit ≥4/6),
Arm C bleibt nach Gate + Mehrheitsregel **nicht** mehrheitlich `COUPLED`,
**und** die Per-κ-Vorbedingung (Batterie ∧ Reziprozität) bleibt auf Arm B erhalten.

**H0:** Kein Gate-Abstand, oder Vorbedingung geht unter Intervention verloren
(`PRECONDITION_LOST`), oder Arm C koppelt mehrheitlich (§1.1 fail).

### 1.1 Riskante Vorhersage (§1.1)

**Arm C bleibt bei allen κ-Stufen mit erhaltener Vorbedingung `NO_COUPLING`
nach Gate + Mehrheitsregel (≥4/6 Seeds).**

κ-Stufen mit `PRECONDITION_LOST` zählen **nicht** gegen §1.1 und **nicht** für κ\* / Form.

*Begründung der Riskanz:* Der Vorgängerstrang scheiterte an Arm-C-Kohärenz unter
globaler Modulation. Edge-Local + Wechselseitigkeit muss diese Kohärenz
**brechen**, sonst wieder `KOPPLUNG_INVALID`.

---

## 2. Design

### 2.1 Dynamik — Freeze F1–F5

\[
R_{ij}=a_i(1+\gamma_{ij})(\ell_{ij}-b_i(\sigma)),\quad
\ell=\texttt{avg\_latency}\ \text{via}\ \texttt{trimmed\_m7}
\]

\[
\gamma_{ij}\leftarrow\tanh(\gamma_{ij}+\eta\cdot\delta_{ij}),\quad
\delta_{ij}=R_{ij}-\bar R_{i\cdot},\quad \eta=\mathbf{1.0}
\]

**Wechselseitige Paar-Ehre (Kern der neuen Architektur):**

\[
h_{ij}=\mathrm{clip}\!\left(\frac{|R_{ij}|}{|R_{ij}|+1},0,1\right),\quad
h^{\leftrightarrow}_{ij}=\tfrac12\bigl(h_{ij}+h_{ji}\bigr)
\]

Falls Rückkante `(j,i)` im Ledger fehlt oder nicht `ever_updated`:  
\(h^{\leftrightarrow}_{ij}:=h_{ij}\) **und** Zelle markiert `reciprocity_thin`  
(zählt wie Vorbedingungs-Verletzung, wenn Seed-`frac_sticky_via_ledger` \< 0.3).

**Kanten-lokale Intervalmodulation (ersetzt globales `1+κ·h`):**

```text
# Sender i, Sticky-Partner j* (Arm B: j* aus M; Arm C: Signal aus π(M))
factor_ij = 1 + κ · h↔(i, j*)
interval_i ← base_i · factor_ij
```

| Freeze | Inhalt |
|--------|--------|
| **F1** | `η = 1.0` (Kontinuität Closed-Loop; Cap unverändert) |
| **F2** | `ℓ_ij` nur über `LedgerBook.update` bei Interaktion — **kein** Direktpfad \(R\to\ell\) |
| **F3** | Batterie-Schwellen A∧B∧C wie §0.3.1 |
| **F4** | `latency_mode = trimmed_m7` (MAD-Gate + oberes Trim 10 %, `n_min=14`) |
| **F5** | ACK/Receipt-Traffic aktiv (Generator unverändert seit `b9da5efe`); Reziprozitäts-Schwelle §0.3.2 |

**P_i:** Gas A1…A9 → nur \(\mathbf{P}_1\ldots\mathbf{P}_9\) (keine Typ-Paar-Matrix).

**Abgrenzung zum INVALID-Strang:** Es gibt **kein** gemeinsames
`interval_i = base_i · (1 + κ · h_i)` über einen beliebigen Partner-Honor ohne
Paar-Mittelung \(h^{\leftrightarrow}\). Modulation ist an die **gerichtete
Sticky-Kante** und ihre Rückkante gebunden.

### 2.2 Arme

| Arm | `κ` | Delivery (Sticky M) | Kopplungs-Signal `j*` / `h↔` |
|-----|-----|---------------------|------------------------------|
| **A** | `0` | M | Formel aus; Ledger + γ laufen |
| **B** | `>0` | M | `j*` = echte Sticky-Zuordnung; `h↔` auf `(i,j*)` und `(j*,i)` |
| **C** | `>0` | M (unverändert) | `j*` = Partner aus π(M); `h↔` unter permutierter Zuordnung |

Arm C: **Delivery bleibt auf M** (Traffic/Ledger real). Nur der
**Kopplungseingang** liest π(M). Shuffle-Mechanik = `permute_sticky_map`
(Kontinuität; gleiche Familie wie Closed-Loop).

### 2.3 κ-Raster und Seeds (neu)

| Parameter | Wert |
|-----------|------|
| `κ` | `{0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}` |
| Seeds | `{20261801 … 20261806}` |
| Gesperrt | alle Seeds ≤ `20261799` (HARKing) |
| `warmup_ticks` | 32 |
| `cycles` | 512 |
| η | **1.0** (F1) |
| `latency_mode` | **`trimmed_m7`** (F4) |

### 2.4 Spot-Checks (vor Sweep, bindend)

| Check | Seed | Erwartung | Fail-Label |
|-------|------|-----------|------------|
| κ=0 Batterie | `20261801` | A∧B∧C PASS | `SIGNAL_BLIND` → Sweep gesperrt |
| κ=0 Reziprozität | `20261801` | `frac_sticky_via_ledger ≥ 0.3` | `RECIPROCITY_LOST` → Sweep gesperrt |
| κ=0 ℓ-Mode | `20261801` | `latency_mode=trimmed_m7`, ell-Screen berichtet | Dokumentationspflicht |

---

## 3. Schwellen und Gate

Kontinuität zu `KOPPLUNG_EIJ_v1` / `CLOSED_LOOP_KOPPLUNG_v0` §3
(**Zahlen nicht nach Daten senken**):

| Regel | Wert |
|-------|------|
| Batterie A / B / C | §0.3.1 |
| Reziprozität | §0.3.2 |
| Gate `COUPLED` | (1) `p < α` (2) `D_dyn > 0` (3) `r_B − r_C ≥ Δr_min` (4) `r_B ≥ r_floor` |
| `α` | 0.05 · `n_surrogates` = 200 |
| `Δr_min` | **0.10** |
| `r_floor` | **0.34** |
| Mehrheit | ≥ **4/6** Seeds |
| Gate B vs. C | ≥ **4/6** Seeds Abstand |
| §1.1 | Arm C `NO_COUPLING` ≥4/6 auf **intakten** κ |

`κ*` / Form nur auf vorbedingungs-intakten κ.

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | Spot κ=0: Batterie scheitert |
| `RECIPROCITY_LOST` | Spot oder Seed: `frac_sticky_via_ledger` \< 0.3 |
| `PRECONDITION_LOST` | Batterie und/oder Reziprozität unter κ verloren |
| `KOPPLUNG_INVALID` | §1.1: Arm C mehrheitlich `COUPLED` auf intakten κ |
| `NO_COUPLING` | kein intaktes κ erfüllt Gate B↔C |
| `COUPLED_EMERGENT` | Gate + Form auf intakten κ |
| `COUPLED_FORCED` | Gate ohne Form auf intakten κ |

Anteil `PRECONDITION_LOST` / `RECIPROCITY_LOST` explizit berichten (kein Kopplungsbeleg).

---

## 5. Ablauf

1. ~~Freigabe `DRAFT → BINDEND`~~ **erledigt 2026-08-26**  
2. Capture + Runner (F1–F5, Arme, `trimmed_m7`, ACK-Traffic)  
3. Spot-Checks Seed `20261801` (Batterie ∧ Reziprozität)  
4. Sweep A/B/C × κ × Seeds `20261801–06`  
5. Freeze Artefakte + Verdict — **keine** Nachjustierung von η / Schwellen / Labels nach Datenblick  

## 6. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **DRAFT** | erreicht 2026-08-26 |
| **BINDEND** | **erreicht 2026-08-26** |
| **Sweep** | freigegeben nach Spot PASS |

**Runner:** `scripts/run_edge_local_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/edge_local_kopplung_v0/`

---

## 7. Checkliste BINDEND

| Anforderung | Status |
|-------------|--------|
| Frage: κ_ij + Wechselseitigkeit → Gate B↔C? | ✅ §0.2 |
| Neuer Strang (Serie geschlossen) | ✅ Abgrenzung |
| Hypothese + §1.1 riskant | ✅ §1 / §1.1 |
| Batterie A∧B∧C per κ | ✅ §0.3.1 |
| Reziprozität ≥ 0.3 | ✅ §0.3.2 |
| `PRECONDITION_LOST` / `RECIPROCITY_LOST` | ✅ §0.3, §4 |
| F1 η=1.0 | ✅ §2.1 |
| F2 Ledger.update only | ✅ §2.1 |
| F3 Batterie-Schwellen | ✅ §0.3.1 |
| F4 `trimmed_m7` | ✅ §2.1 |
| F5 ACK/Receipt | ✅ §2.1 |
| \(h^{\leftrightarrow}\) Paar-Mittel (nicht globales `1+κ·h`) | ✅ §2.1 |
| Arme A/B/C · Delivery auf M · Signal π(M) | ✅ §2.2 |
| Neue Seeds `20261801–06` | ✅ §2.3 |
| Gate-Zahlen unverändert (Δr_min=0.10, r_floor=0.34) | ✅ §3 |
| HARKing-Sperre | ✅ Kopf |
| **BINDEND** | ✅ 2026-08-26 |

---

## 8. Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | DRAFT v0 — Seeds, Gate, Arme, Freeze F1–F5 |
| 2026-08-26 | **BINDEND** (User-Freigabe) |
