# R_ij Screen — `sensitivity_gamma_v02`

**Protokoll:** `docs/R_IJ_SCREEN_v0_DRAFT.md` (kein Pre-Reg)
**Lauf:** FULL · 15s · warmup=32 · cycles=512
**JSON:** `/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage/agents_b2g/emergence/r_ij_screen_v0/R_IJ_SCREEN_sensitivity_gamma_v02_FULL.json`

## Majority

**`RESPONSE_SCREEN_FAIL`** · Pre-Reg erlaubt: **NEIN**
A 0/3 · B 3/3 · C 3/3

| Seed | A | B | mean ΔR | C | |ΔΔR| | Label |
|-----:|:-:|:-:|--------:|:-:|------:|:------|
| 20261401 | ✗ | ✓ | 1.357561 | ✓ | 1.143067 | `RESPONSE_SCREEN_FAIL` |
| 20261402 | ✗ | ✓ | 1.362308 | ✓ | 1.153883 | `RESPONSE_SCREEN_FAIL` |
| 20261403 | ✗ | ✓ | 1.364538 | ✓ | 1.1624 | `RESPONSE_SCREEN_FAIL` |

## Lesart

- `OFFSET_ONLY`: A∧B, C fail — konstanter Kantenversatz (v0.1).
- `RESPONSE_HETEROGENEOUS`: A∧B∧C — Empfindlichkeit (v0.2-Kandidat).
- Pre-Reg nur bei A∧B∧C.
