# M7 Filter — Ergebnis

**Charakter:** Engineering · keine Pre-Reg
**Gate:** `M7_PRESERVES_FIT` · 13.4s
**Candidate:** `trimmed_m7` (MAD + upper 10% trim)
**Seeds:** `20261731…20261733`
**Reziprozität (Median via_led):** 1.0

## sticky-ℓ Selektivität + Batterie

| Mode | median ell_ρ | ell-selektiv (≥2/3) | Batterie (≥2/3) |
|:-----|-------------:|:-------------------:|:---------------:|
| ewma | 0.245401 | ✓ | ✓ |
| median_m7 | 0.63911 | ✓ | ✓ |
| trimmed_m7 | 0.643809 | ✓ | ✓ |
| ewma_gate | 0.249563 | ✓ | ✓ |

## Per seed (trimmed_m7)

| Seed | ell_ρ | ell_pass | A | B | C | via_led |
|-----:|------:|:--------:|:-:|:-:|:-:|--------:|
| 20261731 | 0.652622 | True | True | True | True | 1.0 |
| 20261732 | 0.615915 | True | True | True | True | 1.0 |
| 20261733 | 0.643809 | True | True | True | True | 1.0 |

## Konsequenz

- `M7_PRESERVES_FIT` → Engpass 2 behoben; Edge-Local Pre-Reg freigegeben.
- Sonst → Intake weiter justieren (frac / MAD_K / ewma_gate).

Versiegeltes `ARCHITECTURE_FIT` (EWMA) bleibt Vorher-Zustand (§3.5.1).
