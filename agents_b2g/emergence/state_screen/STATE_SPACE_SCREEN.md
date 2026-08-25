# Zustandsraum-Screening (kein Studien-Verdict)

**Zweck:** Charakterisierung — welche Dimensionen sind unter Partnerpermutation
selektiv und nicht global synchron? Keine Hypothese, keine Pre-Reg.

**Lauf:** seed=20260901 · warmup=32 · cycles=64 · κ=0 · 1.06s · D=18
**Outcome-Label:** `NONE_CLOSE` (Arbeitsbezeichnung, kein bindendes Verdict)

**HARKing-Sperre:** Kandidaten aus diesem Lauf nicht im selben Datensatz
als Hypothese testen. Nächste Studie = neuer DRAFT + neue Läufe.

| Dimension | σ_last | MAE_scaled | |ρ| | static | Candidate |
|-----------|-------:|-----------:|----:|:------:|:---------:|
| `phase` | 0.306565 | 0.316732 | — | yes | no |
| `risk_factor` | 0.042591 | 0.270833 | — | yes | no |
| `decision_bias` | 0.318361 | 0.229167 | — | yes | no |
| `honor` | 257.196685 | 0.046808 | 0.994464 |  | no |
| `checks_failed` | 2.601775 | 0.037489 | 0.959944 |  | no |
| `amount_multiplier` | 0.332138 | 0.025938 | — | yes | no |
| `strictness` | 0.410267 | 0.025 | — | yes | no |
| `checks_passed` | 8.200132 | 0.024839 | 0.997063 |  | no |
| `checks_performed` | 9.863744 | 0.016451 | 0.996596 |  | no |
| `settlements` | 7.741736 | 0.014275 | 0.994399 |  | no |
| `total_fee_burned` | 104.513433 | 0.014275 | 0.994399 |  | no |
| `total_volume` | 348378.110237 | 0.014275 | 0.994399 |  | no |
| `total_reported` | 592358.374601 | 0.013331 | 0.996916 |  | no |
| `inbox_len` | 7.69282 | 0.013069 | 0.044413 |  | no |
| `milestone_count` | 9.970469 | 0.008301 | 0.996801 |  | no |
| `failure_count` | 0.0 | 0.0 | — | yes | no |
| `s_honor` | 0.0 | 0.0 | — | yes | no |
| `tick_count` | 0.0 | 0.0 | 1.0 |  | no |

**Kandidaten:** (keine)

## Lesart der drei Ausgänge

- `SOME_CANDIDATES` — belegte Vorbedingung für eine *neue* Pre-Reg
- `NONE_CLOSE` — evtl. Transformation prüfen (neuer DRAFT), nicht hier nachjustieren
- `NONE_CLEAR` — Hinweis: partnerselektiver Zustand fehlt; Architekturfrage
