# KOPPLUNG_EIJ_v1 — κ-Sweep Ergebnis

**Pre-Reg:** `docs/KOPPLUNG_EIJ_v1_PREREG.md` (BINDEND · I1_PASS)
**Lauf:** FULL · warmup=32 · cycles=512 · 365s · EXIT 0
**JSON:** `/tmp/emergence_eij_sweep/KOPPLUNG_EIJ_SWEEP.json`

## Verdict

**`KOPPLUNG_INVALID`** — Arm C COUPLED (Mehrheit) at some κ — §1.1 falsified

## Gate §3.3 je κ (Arm B vs C)

| κ | Seeds Gate-OK | ≥4/6 |
|--:|-------------:|:----:|
| 0.0 | 0/6 | no |
| 0.2 | 0/6 | no |
| 0.4 | 0/6 | no |
| 0.6 | 0/6 | no |
| 0.8 | 0/6 | no |
| 1.2 | 0/6 | no |

## Arm C (§1.1)

| κ | assess COUPLED Seeds | ≥4/6 |
|--:|---------------------:|:----:|
| 0.0 | 0/6 | no |
| 0.2 | 3/6 | no |
| 0.4 | 3/6 | no |
| 0.6 | 4/6 | YES |
| 0.8 | 2/6 | no |
| 1.2 | 2/6 | no |

Vorhersage gehalten: **NEIN**

## Form §3.2

r̄_B(κ) = [0.1361, 0.2503, 0.2437, 0.2144, 0.1958, 0.1787]
SD_pool = 0.0777 · Form-OK = False
D_dyn(A) mean = 1.0656 · κ* = None

## Regel

Keine Schwellen-Nachjustierung. HARKing auf Alt-Daten aktiv.
