# RECIPROCAL_EVENT_KOPPLUNG_v0 — κ-Sweep Ergebnis

**Pre-Reg:** `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md` (BINDEND)  
**Lauf:** FULL · Seeds `20262201…20262206`  
**JSON:** `RECIPROCAL_EVENT_KOPPLUNG_FULL.json`  
**F5:** Inter-Arrival · **F6:** Snapshot Δt=64 · **F7:** Receipt Gate  

## κ=0 Spot (Seed 20262201)

- Intact: **True** (INTACT)
- A ρ=0.184155 · B mae_n=0.445989 · C |ΔΔR|=1.625847
- SIGNAL_BLIND: **NEIN**

## Verdict

**`NO_COUPLING`** — Gate unmet on all precondition-intact κ

| κ | Intact | Label | Gate-OK | ≥4/6 Gate | C-COUPLED |
|--:|-------:|:------|--------:|:---------:|----------:|
| 0.0 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.2 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.4 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.6 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 0.8 | 6/6 | INTACT | 0/6 | no | 0/6 |
| 1.2 | 6/6 | INTACT | 0/6 | no | 0/6 |

§1.1 gehalten: **JA** · κ*=None · Form-OK=False

## Mittlere Kuramoto-r (Seed-Mittel)

| κ | r̄_A | r̄_B | r̄_C |
|--:|-----:|-----:|-----:|
| 0.0 | 0.2867 | 0.2867 | 0.2867 |
| 0.2 | — | 0.2881 | 0.2909 |
| 0.4 | — | 0.2863 | 0.3298 |
| 0.6 | — | 0.2817 | 0.2813 |
| 0.8 | — | 0.2789 | 0.3008 |
| 1.2 | — | 0.3069 | 0.2840 |

`r_B` ist flach: Span über κ ≈ 0.028 gegen `sd_pool` ≈ 0.045 — Modulation bleibt unter Seed-Streuung.
Bei κ=0 steht r bereits ≈ 0.29 (kein Sprung wie in der Tick-Serie).

## Interventionsstärke (Verdrahtung) — Seed 20262201 Arm B

| Observable | κ=0 | κ=1.2 | Δ |
|------------|----:|------:|--:|
| `frac_coupling_on` | 0.0 | 1.0 | +1.0 |
| `T_mean` (Snapshot-Periode) | 1.305 | 0.979 | **−0.326** |
| `msg_t_span` | 164 | 156 | −8 |
| States / Messages | — | — | **ungleich** |

**κ ist angeschlossen.** Verhalten ändert sich; Phasenkohärenz (Gate) entsteht nicht.

## Interpretation (mit Vorbehalt → geklärt)

1. **§1.1 hält** erstmals vollständig (Arm C nirgends mehrheitlich `COUPLED`) — Design/Kontrollarm funktionieren; Ergebnis ist **interpretierbar**.
2. **Kein Verdrahtungsfehler:** Observablen differieren zwischen κ=0 und κ=1.2 (siehe oben).
3. **Echtes Negativ:** Wechselseitige kanten-lokale Inter-Arrival-Modulation (F7) verändert Timing/Zustand, erzeugt aber **keine** Gate-fähige Phasenkohärenz B↔C.

Tick-Serie versiegelt · Hybrid Tick/Event verboten · keine Schwellen-Nachjustierung.
