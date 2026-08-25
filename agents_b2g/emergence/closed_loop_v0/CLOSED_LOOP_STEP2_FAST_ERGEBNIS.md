# Closed-Loop Schritt 2 (FAST)

**Protokoll:** `docs/CLOSED_LOOP_RESPONSE_v0_DRAFT.md` (BAU_FREIGEGEBEN)
**Majority:** `RESPONSE_HETEROGENEOUS` · Pre-Reg erlaubt: **JA** · 3s

| Seed | A | ρ | B | mae_n | C | \|ΔΔR\| | η | Label |
|-----:|:-:|--:|:-:|------:|:-:|-------:|--:|:------|
| 20261501 | ✓ | 0.884224 | ✓ | 0.655501 | ✓ | 1.655467 | 0.0500 | `RESPONSE_HETEROGENEOUS` |
| 20261502 | ✓ | 0.849998 | ✓ | 0.87852 | ✓ | 1.813581 | 0.0500 | `RESPONSE_HETEROGENEOUS` |
| 20261503 | ✓ | 0.852017 | ✓ | 0.678015 | ✓ | 1.145687 | 0.0500 | `RESPONSE_HETEROGENEOUS` |

## Freeze (Bau-Default)

- F1 η: pro Seed im JSON `freeze.F1_eta`
- F2 ℓ: nur LedgerBook.update
- F3 B: MAE unter Partnerpermutation

Vor Pre-Reg §2.2 schließen. Kein κ-Sweep.
