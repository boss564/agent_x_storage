# Emergenz — Kopplungs-Umbau: Ergebnis

**Pre-Reg:** `docs/EMERGENZ_KOPPLUNG_PREREG.md` (BINDEND 2026-08-24)
**Lauf:** SMOKE · warmup=8 · cycles=64 · 63s
**JSON:** `/tmp/emergence_kopplung/EMERGENZ_KOPPLUNG_SWEEP_SMOKE.json`

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
SD_pool = 0.0638
Form-OK = False · meta = `{"deltas": [0.10971666666666666, 0.03255000000000002, -0.026400000000000035, -0.00041666666666664853, 0.0020000000000000018], "max_delta": 0.10971666666666666, "max_k": 0, "mean_below": 0.0, "sd_pool": 0.06380892626763572, "cond_3x_mean": false, "cond_2x_sd": false}`

D_dyn(A) mean = 1.0270
κ* = None

## Regel

Keine Schwellen-Nachjustierung. Bereichserweiterung = neue Pre-Reg.
