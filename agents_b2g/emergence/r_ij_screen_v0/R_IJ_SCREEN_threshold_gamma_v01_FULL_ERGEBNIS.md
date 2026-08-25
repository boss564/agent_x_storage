# R_ij Screen — `threshold_gamma_v01`

**Protokoll:** `docs/R_IJ_SCREEN_v0_DRAFT.md` (kein Pre-Reg)
**Lauf:** FULL · 16s · warmup=32 · cycles=512
**JSON:** `/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage/agents_b2g/emergence/r_ij_screen_v0/R_IJ_SCREEN_threshold_gamma_v01_FULL.json`

## Majority

**`OFFSET_ONLY`** · Pre-Reg erlaubt: **NEIN**
A 3/3 · B 3/3 · C 0/3

| Seed | A | B | mean ΔR | C | |ΔΔR| | Label |
|-----:|:-:|:-:|--------:|:-:|------:|:------|
| 20261401 | ✓ | ✓ | 0.956119 | ✗ | 0.0 | `OFFSET_ONLY` |
| 20261402 | ✓ | ✓ | 1.053255 | ✗ | 0.0 | `OFFSET_ONLY` |
| 20261403 | ✓ | ✓ | 0.965886 | ✗ | 0.0 | `OFFSET_ONLY` |

## Lesart

- `OFFSET_ONLY`: A∧B, C fail — konstanter Kantenversatz (v0.1).
- `RESPONSE_HETEROGENEOUS`: A∧B∧C — Empfindlichkeit (v0.2-Kandidat).
- Pre-Reg nur bei A∧B∧C.
