# KOPPLUNG_EIJ_v1 — κ-Sweep Ergebnis (FINAL)

**Status:** FINAL · Pre-Reg BINDEND · I1_PASS · keine Nachjustierung  
**Pre-Reg:** `docs/KOPPLUNG_EIJ_v1_PREREG.md`  
**Lauf:** FULL · warmup=32 · cycles=512 · 365 s · 78 Zellen · EXIT 0  
**Artefakte:** `/tmp/emergence_eij_sweep/` · `agents_b2g/emergence/eij_sweep/` (Sicherung)

## Verdict (bindend)

**`KOPPLUNG_INVALID`** — Arm C bei κ=0.6 mehrheitlich `COUPLED` (4/6) → §1.1 **widerlegt**.

| Kennzahl | Wert |
|----------|------|
| Gate §3.3 (B vs C) | nirgends ≥4/6 |
| κ\* | `None` |
| Form §3.2 | False |
| I1-Edge | `I1_PASS` (Voraussetzung erfüllt) |
| §1.1 gehalten | **NEIN** |

## Arm C (§1.1)

| κ | COUPLED Seeds | ≥4/6 |
|--:|-------------:|:----:|
| 0.0 | 0/6 | no |
| 0.2 | 3/6 | no |
| 0.4 | 3/6 | no |
| 0.6 | 4/6 | YES |
| 0.8 | 2/6 | no |
| 1.2 | 2/6 | no |

## Kennzahlen

r̄_B(κ) = [0.1361, 0.2503, 0.2437, 0.2144, 0.1958, 0.1787] · SD_pool = 0.0777  
D_dyn(A) mean = 1.0656

## Einordnung (append-only)

I1-Edge bestand (Partnerselektivität der Größe `e_ij`). Der Sweep scheitert dennoch an
§1.1: unter Intervention wird Arm C bei mindestens einem κ mehrheitlich `COUPLED`.
Gate B↔C bleibt unerfüllt. Keine Schwellen-Nachjustierung.

## Regel

Studie geschlossen als Negativbefund auf der Interventions-Ebene. HARKing auf Alt-Daten aktiv.
