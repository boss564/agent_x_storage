# completion_proof Screen — Gate Notes

**Status:** SCREEN only · kein Pre-Reg · 2026-08-26  
**Runner:** `python3 prototypes/v2_stateful_graph/completion_proof_screen.py`  
**Terminologie:** `completion_proof` = verifizierbarer Übergangs-Receipt (Mock-Z3 / Mock-BHO).  
**Nicht:** kryptographisches Proof-of-Work.

## Frage

Bleibt `STRUCTURE_RELATIONAL` bei \|Q\|=4, wenn \(q\to q'\) nur nach
deterministischem Nachweis greift?

## Freeze

| Fakt | Wert |
|------|------|
| \|Q\| | 4 (fix) |
| Mechanik | BINDEND (`stateful_graph_study`) |
| Seeds | `20270601–06` |
| Gate | ΔQ≥0,5 ∧ H≥2,0 ∧ Margin>0,1 |
| baseline | unverändert |
| always | Receipt immer ok |
| lossy | ≈25% Übergänge gebremst (`crc%4==0`) |

## Screen-Ergebnis (2026-08-26)

| Mode | Passes | Avg Margin | Avg brake | Verdict |
|------|--------|------------|-----------|---------|
| baseline | 6/6 | 0,495 | 0 | `STRUCTURE_RELATIONAL` |
| always | 6/6 | 0,495 | 0 | `STRUCTURE_RELATIONAL` (= baseline) |
| lossy | 6/6 | 0,431 | ≈0,28 | `STRUCTURE_RELATIONAL` |

**Hypothese: `HYPOTHESIS_CONFIRMED`** — relationale Trennung bleibt unter deterministischem
`completion_proof` stabil (auch bei ~28% Bremsung). Artefakt: `completion_proof_results.json`.
