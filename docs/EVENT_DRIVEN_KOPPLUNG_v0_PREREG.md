# Emergenz — Ereignisbasierte Kopplung (Discrete Event-Driven): Pre-Registration (**BINDEND**)

**Arbeitstitel:** `EVENT_DRIVEN_KOPPLUNG_v0`  
**Status:** **BINDEND** — 2026-08-26 · PROTO_PASS · Sweep freigegeben  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) — **neuer Strang**  
**Abgrenzung:** Kopplungs-Serie (`KOPPLUNG_SERIE_ABSCHLUSS.md`, 7× `INVALID`) bleibt **versiegelt**  
**Proto:** `agents_b2g/emergence/event_driven_proto_v0/` · Gate `PROTO_PASS` (3/3, 0.01s)  
**Capture:** `agents_b2g/emergence/event_driven_kopplung_capture.py`  
**Runner:** `scripts/run_event_driven_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/event_driven_kopplung_v0/`  
**DRAFT:** `docs/EVENT_DRIVEN_KOPPLUNG_v0_DRAFT.md` (historisch)

### Bindungs-Vermerk

```text
Status: DRAFT → BINDEND
Dokument: docs/EVENT_DRIVEN_KOPPLUNG_v0_PREREG.md
Datum: 2026-08-26
F5: Inter-Arrival (κ · h steuert nächsten Gap der Event-Uhr)
Snapshot: Events in festem Zeitfenster Δt=64 aggregiert → Phase/State
Phase: φ_i = 2π · (t_last / T_i)
Arme: A/B/C · Delivery auf M · Signal π(M)
Seeds: 20262001…06 · Spot 20262001 · ≤20261999 gesperrt
Gate: Δr_min=0.10 · r_floor=0.34 · ≥4/6 · α=0.05 · n_surrogates=200
Serie: versiegelt
```

### HARKing-Sperre (strikt)

Nicht für Hypothesentests / Gate-Auswertung dieser Studie verwenden:

- Gesamte Kopplungs-Serie inkl. `EDGE_LOCAL_KOPPLUNG_v0`, `CLOSED_LOOP_KOPPLUNG_v0`, Ledger/EIJ/Queue  
- Proto-Screen `event_driven_proto_v0/` und Seeds `20261901–03`  
  (Freeze-Fakten zitierbar; Zahlen nicht als Sweep-Outcome)  
- Alle Seeds ≤ `20261999` für Sweep-/Gate-Zellen  

Neue Seeds · neue Läufe · neue Artefakte unter `event_driven_kopplung_v0/`.

### Abgrenzung zur geschlossenen Serie

Die Serie zeigte: **iterative, zeitkontinuierliche** Taktraten-Modulation erzeugt
netzwerk-weite Kohärenz (Arm C koppelt). Dieser Strang wechselt die **Dynamik**:

> Eliminiert den kontinuierlichen Taktgeber. Updates nur an diskreten Impulsen
> (agent-private Event-Uhr). Ziel: keine synchrone Trägerwelle \(S_{\mathrm{COMMON}}\).

Kein Re-Run von `1+κ·h` / `h^{\leftrightarrow}` auf Tick-EWMA.

---

## 0. Zweck

### 0.1 Freeze-Fakten

| Fakt | Quelle | Rolle |
|------|--------|-------|
| Proto-Gate A∧B | `PROTO_PASS` 3/3 | F0 |
| Diskrete Impulse | Proto | F1 |
| Agent-private Event-Uhr | Proto | F2 |
| Ordinal-Event-Index für Batterie-ρ | Proto | F3 |
| \(R = a(1+\gamma)(S-b)\), \(\mathbf{P}_{1\ldots9}\) | Kontinuität | F4 |
| **Inter-Arrival-κ** | User-BINDEND | **F5** |
| **Snapshot Δt=64** | User-BINDEND | **F6** |
| Serie versiegelt | `45e7f4c6` | Motiv |

### 0.2 Forschungsfrage

Erzeugt eine **ereignisbasierte** Intervention (diskrete Impulse, agent-private
Event-Uhr, **kein** kontinuierliches \(\ell_{ij}(t)\), κ auf **Inter-Arrival**)
einen **Gate-Abstand Arm B ↔ Arm C** bei intakter Batterie A∧B∧C?

### 0.3 Vorbedingung (bindend, per κ) — Batterie A∧B∧C

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **A** | Median \|ρ\| \(R\)-Serie (Event-Index) vs. Schwarm-Mittel | ≤ 0.90 · `n_corr ≥ 9` |
| **B** | `mae_norm` unter Partnerpermutation Sticky-Event-Antworten | ≥ 0.05 |
| **C** | mean \|ΔR(S_low)−ΔR(S_high)\| | ≥ 0.05 |

Sonst → `PRECONDITION_LOST` (zählt nicht für κ\* / §1.1).

---

## 1. Hypothesen

**H1:** Gate-Abstand B vs. C (≥4/6), Arm C nicht mehrheitlich `COUPLED`, Batterie intakt.  
**H0:** Kein Abstand / `PRECONDITION_LOST` / Arm C koppelt.

### 1.1 §1.1

Arm C bleibt auf intakten κ `NO_COUPLING` (≥4/6).

---

## 2. Design

### 2.1 Dynamik — Freeze F0–F6

\[
R_i(e_k)=a_i(1+\gamma_i)(S_k^{(i)}-b_i(\sigma_S))
\]

**F5 Inter-Arrival (BINDEND):**

```text
base_gap = agent-private draw
h = clip(|R_j*| / (|R_j*| + 1), 0, 1)   # j* aus Signal-Map (Arm B/C)
next_gap = base_gap · (1 + κ · h)
next_event_i = t_now + next_gap
T_i := next_gap   # Periode der Event-Uhr
```

κ=0 / Arm A: `next_gap = base_gap` (h ungenutzt).

**F6 Snapshot (BINDEND):**

```text
Δt = 64 (Simulationszeit)
Fenster [t, t+Δt): alle Events in diesem Intervall
φ_i = 2π · (t_last_event_i / T_i)   # T_i = letzte Periode; wrap mod 2π via frac
State-Snapshot am Fensterende: phase, R_i, T_i, event_count_window
Kuramoto/D_dyn auf der Snapshot-Zeitreihe (nicht pro Einzel-Event)
```

| Freeze | Inhalt |
|--------|--------|
| F0–F4 | wie DRAFT |
| **F5** | **Inter-Arrival** — Amplitude verboten |
| **F6** | **Δt=64** Event-Aggregation → Snapshot |

### 2.2 Arme

| Arm | κ | Events/Delivery | Signal j* |
|-----|---|-----------------|-----------|
| A | 0 | M | aus |
| B | >0 | M | Sticky M |
| C | >0 | M | π(M) |

### 2.3 κ / Seeds

| Parameter | Wert |
|-----------|------|
| κ | `{0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}` |
| Seeds | `{20262001 … 20262006}` · Spot `20262001` |
| Gesperrt | ≤ `20261999` |
| Warmup | 16 Events/Agent verwerfen |
| Measure | ≥ 64 Events/Agent · Snapshots bis Maßfenster voll |

### 2.4 Spot

κ=0 Seed `20262001`: Batterie A∧B∧C → sonst `SIGNAL_BLIND`.

---

## 3. Gate

| Regel | Wert |
|-------|------|
| Gate COUPLED | p\<α · D_dyn\>0 · r_B−r_C≥0.10 · r_B≥0.34 |
| α | 0.05 · n_surrogates=200 |
| Mehrheit | ≥4/6 |
| §1.1 | Arm C NO_COUPLING ≥4/6 auf intakten κ |

---

## 4. Verdict-Labels

`SIGNAL_BLIND` · `PRECONDITION_LOST` · `KOPPLUNG_INVALID` · `NO_COUPLING` ·
`COUPLED_EMERGENT` · `COUPLED_FORCED`

---

## 5. Ablauf

1. ~~PROTO_PASS~~ · 2. ~~DRAFT~~ · 3. ~~BINDEND~~ **2026-08-26**  
4. Capture + Runner · 5. Spot · 6. Sweep · 7. Freeze (keine Schwellen-Nachjustierung)

## 6. Freigabe

| Stufe | Status |
|-------|--------|
| PROTO_PASS | ✅ |
| DRAFT | ✅ |
| **BINDEND** | ✅ 2026-08-26 |
| Sweep | freigegeben nach Spot PASS |

---

## 7. Checkliste BINDEND

| Anforderung | Status |
|-------------|--------|
| Frage / Hypothese / §1.1 | ✅ |
| Batterie A∧B∧C | ✅ |
| F5 Inter-Arrival | ✅ |
| F6 Snapshot Δt=64 | ✅ |
| Arme A/B/C | ✅ |
| Seeds 20262001–06 | ✅ |
| Gate-Zahlen | ✅ |
| HARKing | ✅ |
| **BINDEND** | ✅ |

---

## 8. Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | DRAFT v0 |
| 2026-08-26 | **BINDEND** — F5 Inter-Arrival · F6 Snapshot Δt=64 |
