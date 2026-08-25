# Geschlossener Kreis / Antwort-Heterogenität — Arbeitsprotokoll

**Status:** **SCHRITT2_PASS** · 2026-08-25 · Freeze §2.2 geschlossen · Pre-Reg **DRAFT**  
**Dokument:** `docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md`  
**Pre-Reg:** `docs/CLOSED_LOOP_KOPPLUNG_v0_PREREG.md` (BINDEND ausstehend · kein Sweep)  
**Voraussetzung:** `PHI_L_SOURCE_PASS` · Serie geschlossen  
**Artefakt:** `agents_b2g/emergence/closed_loop_v0/CLOSED_LOOP_STEP2_FULL_ERGEBNIS.md`

### Freigabe / Screen

```text
Status: DRAFT → BAU_FREIGEGEBEN → SCHRITT2_PASS (3/3 RESPONSE_HETEROGENEOUS)
Freeze F1–F3: in Pre-Reg zitiert (η=1.0)
Pre-Reg: DRAFT — Sweep erst nach BINDEND
```

---

## 0. Ausgangslage

| Schritt | Status |
|---------|--------|
| 1 φ_L | **`PHI_L_SOURCE_PASS`** (Full-Screen ℓ \|ρ\|≈0.34) |
| 2 `R_ij` A∧B∧C | **PASS** 3/3 Seeds `{20261501…03}` |
| 3 Pre-Reg | **`CLOSED_LOOP_KOPPLUNG_v0_PREREG.md`** · DRAFT · Freeze geschlossen |

Messfrage-Shift (Schritt 3): endogenes Signal → Selbstorganisation der Historie.

---

## 1. Constraints

E1–E6 (Edge-Individuation) · C7 kein Sweep · C8 γ/ℓ getrennt · C9 Formel vor Kreis.

---

## 2. R-Formel

\[
R_{ij}=a_i(1+\gamma_{ij})(\ell_{ij}-b_i),\quad \ell=\texttt{avg\_latency}
\]

\(a_i,b_i\) aus Gas→\(\mathbf{P}_i\); \(b_i=\theta_i\sigma_\ell\).

### 2.2 Freeze-Punkte (vor Pre-Reg)

| ID | Bau-Default (Full-Screen) | Vor Pre-Reg |
|----|---------------------------|-------------|
| **F1** δ/η | Warmup Median\|\δ\| < 0.1 → **η = 1.0** (cap) auf allen 3 Seeds; sonst wäre 0.05 | **η = 1.0** zitieren |
| **F2** ℓ | Nur `LedgerBook.update` bei Interaktion (EWMA). Kein direktes \(R\to\ell\) | zitieren |
| **F3** B | A: Median\|ρ\|≤0.90 · B: MAE_norm≥0.05 unter Partnerpermutation · C: \|ΔΔR\|≥0.05 | zitieren |

---

## 3. γ-Update

\(\gamma\leftarrow\tanh(\gamma+\eta\cdot\delta)\), \(\delta=R_{ij}-\bar R_{i\cdot}\).

---

## 4. P_i

Gas A1…A9; sortierte IDs mod 9; nur \(\mathbf{P}_1\ldots\mathbf{P}_9\).

---

## 5. Batterie / Seeds

A∧B∧C auf φ_L · Seeds `{20261501…03}` · warmup=32 · cycles=512 · κ_sweep=nein  
(κ_behavior=0.4 nur damit R Timing beeinflusst — kein κ-Raster.)

**Runner:** `scripts/run_closed_loop_step2_screen.py`  
**Artefakte:** `agents_b2g/emergence/closed_loop_v0/`
