# Emergenz — Reziprozitäts-Verstärkung: Pre-Registration (**BINDEND**)

**Arbeitstitel:** `RECIPROCITY_AMP_KOPPLUNG_v0`  
**Status:** **BINDEND** — 2026-08-26 · Vierarm A/B/C/D · Sweep freigegeben  
**Dokument-Historie:** `docs/RECIPROCITY_AMP_KOPPLUNG_v0_DRAFT.md` (v1)  
**Capture:** `agents_b2g/emergence/reciprocity_amp_kopplung_capture.py`  
**Runner:** `scripts/run_reciprocity_amp_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/reciprocity_amp_kopplung_v0/`

## Bindungs-Vermerk

```text
Status: DRAFT v1 → BINDEND
Konfund: behoben (Gate B↔D, matched κ)
P1: κ̄_B ≫ κ̄_C (relationale κ-Verstärkung)
P2: Gate B↔D bei matched κ (relationale Phasenkohärenz)
P1_ONLY: gültiges Verdict
N=9 · r_floor=1/√N+0.15=0.483
α-Raster: {0, 0.10, 0.25, 0.40, 0.60, 1.00}
Seeds: 20262401–06 · Spot 20262401 · Proto 202623xx gesperrt
Δκ_min=0.50 · Δamp_min=0.50 · Δr_min=0.10 · ≥4/6 · α_stat=0.05
§1.1d auf Arm D (nicht auf C)
Tick-Serie versiegelt · Hybrid verboten
```

## Primärfragen

- **P1:** F8 erzeugt `κ̄_B − κ̄_C ≥ 0.50` und `frac_amp_B − frac_amp_C ≥ 0.50` (≥4/6)?
- **P2:** Gate B↔D (matched κ) bei intakter Batterie, Arm D `NO_COUPLING` (§1.1d)?

## Arme

| Arm | Signal | κ | Rolle |
|-----|--------|---|-------|
| A | — | 0 | Baseline |
| B | M | endogen F8 | Intervention |
| C | π(M) | endogen F8 | P1 |
| D | π(M) | exogen = κ̄_B | P2 + §1.1d |

Match: pro `(seed, α)` zuerst B → `κ̄_B` → D mit diesem Skalar.

## Gate P2

`p_B < 0.05` · `D_dyn_B > 0` · `r_B − r_D ≥ 0.10` · `r_B ≥ 0.483`
