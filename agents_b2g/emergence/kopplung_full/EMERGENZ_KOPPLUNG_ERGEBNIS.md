# Emergenz — Kopplungs-Umbau: Ergebnis

**Pre-Reg:** `docs/EMERGENZ_KOPPLUNG_PREREG.md` (BINDEND 2026-08-24)
**Lauf:** FULL · warmup=32 · cycles=512 · 493s
**JSON:** `/tmp/emergence_kopplung/EMERGENZ_KOPPLUNG_SWEEP.json`

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
| 0.2 | 6/6 | YES |
| 0.4 | 3/6 | no |
| 0.6 | 6/6 | YES |
| 0.8 | 6/6 | YES |
| 1.2 | 6/6 | YES |

Vorhersage gehalten: **NEIN**

## Form §3.2

r̄_B(κ) = [0.0933, 0.2907, 0.2234, 0.2344, 0.2427, 0.2405]
SD_pool = 0.0710
Form-OK = False · meta = `{"deltas": [0.1973166666666667, -0.06723333333333334, 0.010950000000000015, 0.008299999999999974, -0.0021999999999999797], "max_delta": 0.1973166666666667, "max_k": 0, "mean_below": 0.0, "sd_pool": 0.0709596464800342, "cond_3x_mean": false, "cond_2x_sd": true}`

D_dyn(A) mean = 1.0079
κ* = None

## Regel

Keine Schwellen-Nachjustierung. Bereichserweiterung = neue Pre-Reg.
