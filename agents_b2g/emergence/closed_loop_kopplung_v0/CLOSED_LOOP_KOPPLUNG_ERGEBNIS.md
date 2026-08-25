# CLOSED_LOOP_KOPPLUNG_v0 — κ-Sweep Ergebnis

**Pre-Reg:** `docs/CLOSED_LOOP_KOPPLUNG_v0_PREREG.md` (BINDEND)
**Lauf:** FULL · 404s · EXIT 0
**JSON:** `/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage/agents_b2g/emergence/closed_loop_kopplung_v0/CLOSED_LOOP_KOPPLUNG_FULL.json`
**η:** 1.0 (F1) · Seeds `20261601…20261606`

## κ=0 Spot-Check (Seed 20261601)

- Batterie intact: **True** (INTACT)
- A ρ=0.158327 · B mae_n=0.590541 · C |ΔΔR|=1.106504
- SIGNAL_BLIND: **NEIN**

## Verdict

**`KOPPLUNG_INVALID`** — Arm C COUPLED (Mehrheit) on precondition-intact κ — §1.1 falsified

## Per-κ Batterie + Gate (Arm B vs C)

| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED |
|--:|-------:|:------|--------:|:---------:|----------:|
| 0.0 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.2 | 6/6 | INTACT | 0/6 | no | 6/6 |
| 0.4 | 6/6 | INTACT | 0/6 | no | 6/6 |
| 0.6 | 6/6 | INTACT | 0/6 | no | 6/6 |
| 0.8 | 6/6 | INTACT | 0/6 | no | 6/6 |
| 1.2 | 6/6 | INTACT | 0/6 | no | 6/6 |

§1.1 gehalten: **NEIN**
κ* = None · Form-OK = False · SD_pool = 0.0665
r̄_B (NaN = PRECONDITION_LOST stage) = [0.1362, 0.2862, 0.3016, 0.2874, 0.2624, 0.2418]

## Regel

Keine Schwellen-Nachjustierung. Screening-Seeds gesperrt. HARKing-Sperre aktiv.
