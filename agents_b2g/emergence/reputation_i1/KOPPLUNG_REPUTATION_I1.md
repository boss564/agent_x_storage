# KOPPLUNG_REPUTATION_v1 — I1 Ergebnis (FINAL)

**Pre-Reg:** `docs/KOPPLUNG_REPUTATION_v1_PREREG.md`  
**Status:** `BINDEND → I1_FAILED`  
**Verdict:** `SIGNAL_BLIND` · i1_pass=False  
**Folge:** κ-Sweep gesperrt · kein Arm-Sweep · keine Nachjustierung  
**Seed:** 20260901 · warmup=32 · cycles=64 · κ=0

| Kriterium | Wert | Pass |
|-----------|-----:|:----:|
| I1-V | σ ≈ 257 | YES |
| I1-S | MAE = 0 | no |
| I1-U | 1.0 | YES |
| I1-G | \|ρ\| ≈ 0.99 | no |

## Interpretation (append-only)

Honor ist in der gebundenen Operationalisierung **nicht partnerselektiv**:

1. **Sättigung:** `H ≫ H_cap=200` → `s(H)≈1` für praktisch alle Agenten.
2. **Globale Synchronität:** median `|ρ(H_i,H̄)|≈0.99`.

Entscheidend: unter Partnerpermutation ändert sich das beobachtete Signal nicht (`MAE=0`).

## Regel

Keine Änderung von `H_cap`, `s(H)` oder I1-Schwellen. Keine Umdeutung.  
Fortsetzung nur als neuer DRAFT mit neuer Pre-Reg.

## Artefakte

`agents_b2g/emergence/reputation_i1/` · `/tmp/emergence_reputation_i1/`
