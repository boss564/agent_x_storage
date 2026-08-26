# M7 Spike — Ergebnis

**Charakter:** Engineering · keine Pre-Reg
**Gate:** `M7_LOSES_ELL_SELECTIVITY` · 8.1s
**Seeds:** `20261711…20261713`

## sticky-ℓ Selektivität + Batterie

| Mode | ell-selektiv (≥2/3) | Batterie A∧B∧C (≥2/3) |
|:-----|:-------------------:|:---------------------:|
| EWMA (Vorher) | ✓ | ✓ |
| M7 median | ✗ | ✓ |

## Per seed (M7)

| Seed | ell_ρ | A ρ | B mae_n | C |ΔΔR| | eval/thin | recip_via_led |
|-----:|------:|----:|--------:|----------:|----------:|--------------:|
| 20261711 | 0.915695 | 0.897928 | 0.128903 | 81.924219 | 18/79 | 0.0 |
| 20261712 | 0.905596 | 0.691517 | 0.077945 | 99.991695 | 19/78 | 0.0 |
| 20261713 | 0.920451 | 0.89652 | 0.160565 | 99.866353 | 18/81 | 0.0 |

**Reziprozität (Median frac sticky→Ledger-Rückkante):** 0.0

## Konsequenz

- `M7_PRESERVES_FIT` → Edge-Local Pre-Reg darf starten (nach Reziprozitäts-Check).
- `M7_BREAKS_FIT` / `M7_LOSES_ELL_SELECTIVITY` → Intake oder Signalpfad anpassen bevor Pre-Reg.
- Reziprozität vor Pre-Reg: wechselseitige Reaktion braucht Rückkanten.

Versiegeltes `ARCHITECTURE_FIT` (EWMA) bleibt Vorher-Zustand (§3.5.1).
