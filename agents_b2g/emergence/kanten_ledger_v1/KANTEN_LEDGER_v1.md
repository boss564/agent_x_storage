# KANTEN_LEDGER_v1 — Abnahme-Screening

**Status:** ARCH_BINDEND · kein κ-Sweep
**DRAFT:** `docs/KANTEN_LEDGER_v1_DRAFT.md`
**Lauf:** seeds=[20261201, 20261202, 20261203] · warmup=32 · cycles=512 · κ=0 · 16.23s
**Outcome:** `LEDGER_SCREEN_PASS`

**Kandidaten (≥2/3):** `['avg_latency', 'interaction_count']`
**Near-Miss (≥2/3):** `(keine)`

## Pro Seed / Komponente

### Seed 20261201 (5.97s)

| Komponente | MAE | |ρ| | S-S | S-G | Pass | Near |
|------------|----:|----:|:--:|:--:|:----:|:----:|
| `interaction_count` | 1.404971 | 0.155926 | Y | Y | YES |  |
| `bilateral_balance` | 89524.280285 | — | Y | n | no |  |
| `trust_score` | 0.2927 | 0.952968 | Y | n | no |  |
| `avg_latency` | 0.248201 | 0.348407 | Y | Y | YES |  |
| `edge_risk` | 0.004053 | — | n | n | no |  |

### Seed 20261202 (5.14s)

| Komponente | MAE | |ρ| | S-S | S-G | Pass | Near |
|------------|----:|----:|:--:|:--:|:----:|:----:|
| `interaction_count` | 1.428034 | 0.155926 | Y | Y | YES |  |
| `bilateral_balance` | 100247.333044 | — | Y | n | no |  |
| `trust_score` | 0.287904 | 0.952968 | Y | n | no |  |
| `avg_latency` | 0.255074 | 0.348407 | Y | Y | YES |  |
| `edge_risk` | 0.004053 | — | n | n | no |  |

### Seed 20261203 (5.12s)

| Komponente | MAE | |ρ| | S-S | S-G | Pass | Near |
|------------|----:|----:|:--:|:--:|:----:|:----:|
| `interaction_count` | 1.488594 | 0.155926 | Y | Y | YES |  |
| `bilateral_balance` | 100247.333044 | — | Y | n | no |  |
| `trust_score` | 0.317803 | 0.952968 | Y | n | no |  |
| `avg_latency` | 0.267189 | 0.348407 | Y | Y | YES |  |
| `edge_risk` | 0.004053 | — | n | n | no |  |
