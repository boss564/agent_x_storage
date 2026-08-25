# Edge-Individuierung Probe (FULL)

**Protokoll:** `docs/EDGE_INDIVIDUATION_v0_DRAFT.md`
ρ = Befund · φ₁ bevorzugt · Rauschen = Positivkontrolle · kein Pre-Reg
**Instrument:** `SCREEN_SEES_NOISE` · 16s
**φ₁ unter 0.90:** False · deutlich (≤0.85 Mittel): False

| Seed | raw-S | φ₀ Scale | φ₁ Delay | noise | ℓ | Ctrl |
|-----:|------:|---------:|---------:|------:|----:|:-----|
| 20261401 | 0.964169 | 0.884521 | 0.966691 | 0.672367 | 0.348407 | `SCREEN_SEES_NOISE` |
| 20261402 | 0.964169 | 0.884521 | 0.966691 | 0.492382 | 0.348407 | `SCREEN_SEES_NOISE` |
| 20261403 | 0.964169 | 0.884521 | 0.966691 | 0.715237 | 0.348407 | `SCREEN_SEES_NOISE` |

## Disziplin

- Kein Fit auf ρ-Zielmarke.
- φ₀ = skaleninvariant (fast nicht entkoppelt).
- φ₁ = Zeitverschiebung aus avg_latency — bevorzugter Prod-Kandidat.
- Noise nur Kontrolle.
- Schritt 2 erst nach stabilem Prod-`S_ij`.
