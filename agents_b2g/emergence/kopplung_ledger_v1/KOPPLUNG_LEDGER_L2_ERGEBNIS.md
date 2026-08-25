# KOPPLUNG_LEDGER_v1 — κ-Sweep Ergebnis (interaction_count)

**Pre-Reg:** `docs/KOPPLUNG_LEDGER_v1_PREREG.md` (BINDEND)
**Größe:** `interaction_count` · Lauf: FULL · 720s · EXIT 0
**JSON:** `/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage/agents_b2g/emergence/kopplung_ledger_v1/KOPPLUNG_LEDGER_L2_FULL.json`

## κ=0 Spot-Check (Seed 20261301)

- L1 avg_latency intact: **True** (mae_norm=1.624517, ρ=0.348407)
- L2 interaction_count intact: **True** (mae_norm=1.336582, ρ=0.155926)

## Verdict

**`KOPPLUNG_INVALID`** — Arm C COUPLED (Mehrheit) on precondition-intact κ — §1.1 falsified

## Per-κ Vorbedingung + Gate (Arm B vs C)

| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED |
|--:|-------:|:------|--------:|:---------:|----------:|
| 0.0 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.2 | 6/6 | INTACT | 1/6 | no | 6/6 |
| 0.4 | 6/6 | INTACT | 0/6 | no | 3/6 |
| 0.6 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.8 | 6/6 | INTACT | 0/6 | no | 2/6 |
| 1.2 | 6/6 | INTACT | 0/6 | no | 1/6 |

§1.1 gehalten: **NEIN**
κ* = None · Form-OK = False · SD_pool = 0.0771
r̄_B (NaN = PRECONDITION_LOST stage) = [0.0991, 0.3008, 0.1729, 0.1789, 0.1715, 0.2211]

## Regel

Keine Schwellen-Nachjustierung. HARKing auf Abnahme-Datensatz gesperrt.
