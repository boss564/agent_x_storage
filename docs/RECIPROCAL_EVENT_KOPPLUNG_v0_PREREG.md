# Emergenz — Reziprozitäts-basierte Event-Kopplung: Pre-Registration (**BINDEND**)

**Arbeitstitel:** `RECIPROCAL_EVENT_KOPPLUNG_v0`  
**Status:** **BINDEND** — 2026-08-26 · Freigabe erteilt · Sweep freigegeben  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) — Ereignis-Strang (offen)  
**Dokument-Historie:** `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_DRAFT.md`  
**Capture:** `agents_b2g/emergence/reciprocal_event_kopplung_capture.py`  
**Runner:** `scripts/run_reciprocal_event_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/reciprocal_event_kopplung_v0/`

## Bindungs-Vermerk

```text
Status: DRAFT → BINDEND
Dokument: docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md
Datum: 2026-08-26
F7: κ nur wenn receipt_from == signal_partner
F5: Inter-Arrival (Amplitude-κ verboten)
F6: Snapshot Δt=64 (event-window aggregation)
Seeds: Sweep 20262201–06 · Spot 20262201 · Proto 202621xx gesperrt
Gate: Δr_min=0.10 · r_floor=0.34 · ≥4/6 · α=0.05
Tick-Serie: versiegelt · Hybrid Tick/Event: verboten
```

## Forschungsfrage

Erzeugt reziprozitäts-gegate Inter-Arrival-Kopplung einen Gate-Abstand B↔C bei
intakter Batterie A∧B∧C, während Arm C nach §1.1 `NO_COUPLING` bleibt?

## Hypothesen

- **H1:** Gate B↔C (≥4/6), Arm C nicht mehrheitlich `COUPLED`, Batterie intakt.
- **H0:** Kein Gate, oder `PRECONDITION_LOST`, oder Arm C koppelt mehrheitlich.
- **§1.1:** Arm C bleibt auf intakten κ `NO_COUPLING` (≥4/6).

## Design (bindend)

- Delivery bleibt auf echter Sticky-Map M.
- Signalpartner: Arm B = M, Arm C = π(M).
- Receipt kommt immer vom echten Delivery-Partner.
- **F7-Regel:** κ wirkt nur, wenn `receipt_from == signal_partner`.
- **F5-Regel:** Inter-Arrival passt den nächsten Gap an:
  `next_gap = base_gap / (1 + κ · h(R_sig))` bei F7=true, sonst `next_gap = base_gap`.
- **F6-Regel:** Snapshots in festen Event-Zeitfenstern Δt=64, Kuramoto/D_dyn auf
  Snapshot-Zeitreihe.

## Vorbedingung (per κ)

- A: Median |ρ| ≤ 0.90
- B: mae_norm ≥ 0.05
- C: mean |ΔR(S_low)-ΔR(S_high)| ≥ 0.05
- Sonst: `PRECONDITION_LOST` (nicht für κ*/§1.1/Gate).

## Konstanten

- κ-grid: `{0, 0.2, 0.4, 0.6, 0.8, 1.2}`
- Seeds: `20262201…20262206`
- Spot: `20262201`
- α=0.05, n_surrogates=200, Δr_min=0.10, r_floor=0.34, Mehrheit=4/6

## HARKing-Sperre

- Keine Wiederverwendung von Proto-Seeds `20262101…03`.
- Keine Wiederverwendung Event-Sweep-Seeds `20262001…06`.
- Keine Wiederverwendung Tick-Serien-Datensätze.

