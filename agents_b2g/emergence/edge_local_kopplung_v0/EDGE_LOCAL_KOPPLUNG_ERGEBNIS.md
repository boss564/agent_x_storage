# EDGE_LOCAL_KOPPLUNG_v0 — κ-Sweep Ergebnis

**Pre-Reg:** `docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md` (BINDEND)
**Lauf:** FULL · 182s · EXIT 0
**JSON:** `/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage/agents_b2g/emergence/edge_local_kopplung_v0/EDGE_LOCAL_KOPPLUNG_FULL.json`
**η:** 1.0 (F1) · ℓ=`trimmed_m7` (F4) · Seeds `20261801…20261806`

## κ=0 Spot-Check (Seed 20261801)

- Intact: **True** (INTACT)
- A ρ=0.543905 · B mae_n=0.163901 · C |ΔΔR|=21.158695
- Reziprozität via_led=1.0 (Gate ≥ 0.3)
- SIGNAL_BLIND: **NEIN** · RECIPROCITY_LOST: **NEIN**

## Verdict

**`KOPPLUNG_INVALID`** — Arm C COUPLED (Mehrheit) on precondition-intact κ — §1.1 falsified

## Per-κ Batterie∧Reziprozität + Gate (Arm B vs C)

| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED | RecipLost |
|--:|-------:|:------|--------:|:---------:|----------:|----------:|
| 0.0 | 6/6 | INTACT | 0/6 | no | 0/6 | 0/6 |
| 0.2 | 6/6 | INTACT | 0/6 | no | 6/6 | 0/6 |
| 0.4 | 6/6 | INTACT | 1/6 | no | 6/6 | 0/6 |
| 0.6 | 6/6 | INTACT | 0/6 | no | 6/6 | 0/6 |
| 0.8 | 5/6 | INTACT | 0/6 | no | 4/6 | 0/6 |
| 1.2 | 6/6 | INTACT | 0/6 | no | 1/6 | 0/6 |

§1.1 gehalten: **NEIN**
κ* = None · Form-OK = False · SD_pool = 0.0573
r̄_B (NaN = PRECONDITION_LOST stage) = [0.185, 0.2558, 0.2678, 0.2689, 0.2677, 0.239]

## Regel

Keine Schwellen-Nachjustierung. Seeds ≤20261799 gesperrt. HARKing-Sperre aktiv.
