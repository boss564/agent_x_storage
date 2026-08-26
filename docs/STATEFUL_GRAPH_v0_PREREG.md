# Stateful Graph Automata: Pre-Registration (**BINDEND**)

**Arbeitstitel:** `STATEFUL_GRAPH_v0`  
**Status:** **BINDEND** — 2026-08-26 · Sweep freigegeben  
**Dokument-Historie:** `docs/STATEFUL_GRAPH_v0_DRAFT.md`  
**Proto:** `prototypes/v2_stateful_graph/` · `PROTO_PASS` 3/3  
**Capture / Runner:** `prototypes/v2_stateful_graph/` (Sandbox-only)  
**Artefakte:** `prototypes/v2_stateful_graph/runs/stateful_graph_v0/`  
**Vorläufer:** `docs/KOPPLUNG_SERIE_ABSCHLUSS.md` — φ/ρ-Familie **geschlossen** · dies ist **Serie 1**, nicht Studie 11

## Bindungs-Vermerk

```text
Status: DRAFT → BINDEND
Dokument: docs/STATEFUL_GRAPH_v0_DRAFT.md
F3c: ΔQ ≥ 0.5
F3/F3b: H ≥ 2.0 bit, H_max=4 (Paare, log2)
F10: Arm A σ = crc-Zufall (kein σ=q_i)
F5: Warmup=32, Measure=80
§1.1: Replikations-Vorhersage (Seeds 20270201–06)
CONTAMINATION: bleibt
Transfer: verboten
Seeds: Sweep 20270201–06 · Spot 20270201 · Proto ≤20270199 gesperrt
```

## Primärfrage

Erzeugt diskrete Repulsion auf Sticky-Kanten eine relationale Zustandsstruktur
(ΔQ ≥ 0,5 ∧ H_Kante ≥ 2,0 bit ∧ Arm-C-Bruch), die unter π(M) bricht —
ohne φ/ρ und ohne κ?

## Freeze (bindend)

| ID | Inhalt |
|----|--------|
| F1 | \|Q\|=4 |
| F2 | \(q'=(\sigma+1+(q\bmod2))\bmod\|Q\|\) |
| F3 | H = Shannon über **Paare** \((q_i,q_{j^*})\) · **Bit** · \(H_{\max}=4\) |
| F3b | H ≥ 2,0 |
| F3c | ΔQ ≥ 0,5 |
| F4 | Arm-C-Margin ≥ 0,15 |
| F5 | N=9 · Warmup=32 · Measure=80 |
| F6–F7 | Sticky Ring M · π(M) seed-crc |
| F8 | Anti vs. **true** Partner |
| F9 | Sandbox-only |
| F10 | Arm A: σ = crc-Zufall in Q · **nicht** σ=q_i |

## Arme

| Arm | σ-Quelle | Rolle |
|-----|----------|-------|
| A | crc-Zufall (F10) | Baseline |
| B | q[M(i)] | Intervention |
| C | q[π(M)(i)] | Kontrolle; Metrik vs. true M |

## Vorbedingung / Gate (pro Seed, Arm B, Measure-Fenster)

ΔQ ≥ 0,5 ∧ H ≥ 2,0 bit ∧ (anti_B − anti_C) ≥ 0,15  
Sonst → `STRUCTURE_LOST`.

**Spot zusätzlich:** Arm A berichtet ΔQ ≥ 0,5 und H ≥ 2,0 (Baseline-Sanity; kein relationales Gate).

## §1.1 Replikation

Arm-C-Bruch ≥4/6 auf Seeds `20270201–06`. Fail → `RELATION_INVALID`.

## Mehrheit / Verdicts

| Label | Regel |
|-------|-------|
| `STRUCTURE_RELATIONAL` | Triade ≥4/6 ∧ §1.1 |
| `NO_STRUCTURE` | Triade <4/6 |
| `RELATION_INVALID` | §1.1 fail |
| `SIGNAL_BLIND` | Spot fail |
| `CONTAMINATION` | Kopplungs-Import / Seed-Leck |

## HARKing

Proto-Seeds / Zahlen `20270101–03` und alle φ/ρ-Artefakte nicht für Gate/Sweep.

## Schwellen-Sperre

Keine Absenkung von F3b / F3c / F4 nach Datenblick.
