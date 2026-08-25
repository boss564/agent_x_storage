# Emergenz — Kopplungs-Umbau: Ergebnis (SMOKE)

**Pre-Reg:** `docs/EMERGENZ_KOPPLUNG_PREREG.md` (BINDEND 2026-08-24)
**Lauf:** SMOKE · warmup=8 · cycles=64 · 63s
**JSON:** `/tmp/emergence_kopplung/EMERGENZ_KOPPLUNG_SWEEP_SMOKE.json`
**SHA-256:** `d1f6ac4e1b09dccff8a1081d6958bc1ba49e0764c4aeb08ea47f16548eeaf2b7` (md) · `fbb2d46609bbc4567e058e16de2a8da5004ade05de08fc8c604d8a8e2b01cc78` (json, 27747 B)

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

## Arm C (§1.1 riskante Vorhersage)

| κ | assess COUPLED Seeds | ≥4/6 |
|--:|---------------------:|:----:|
| 0.0 | 0/6 | no |
| 0.2 | 1/6 | no |
| 0.4 | 5/6 | YES |
| 0.6 | 6/6 | YES |
| 0.8 | 6/6 | YES |
| 1.2 | 6/6 | YES |

Vorhersage gehalten: **NEIN**

## Form §3.2

r̄_B(κ) = [0.1291, 0.2388, 0.2714, 0.245, 0.2445, 0.2465]
SD_pool = 0.0638 · Form-OK = False · κ* = None

## Hinweis

Smoke ist **nicht** der bindende Lauf (verkürzte Zyklen). Full-Sweep läuft unter
`/tmp/emergence_kopplung/` (warmup=32, cycles=512). Ergebnis = was herauskommt.
