# Emergenz — Reziprozitäts-Verstärkung (positive Rückkopplung): Arbeitsprotokoll (**DRAFT**)

**Arbeitstitel:** `RECIPROCITY_AMP_KOPPLUNG_v0`  
**Status:** **BINDEND** — 2026-08-26 · Vierarm A/B/C/D · Sweep freigegeben  
**Kanonisches Pre-Reg:** `docs/RECIPROCITY_AMP_KOPPLUNG_v0_PREREG.md`  
**Charakter:** Interventionsstudie (**Vierarm A/B/C/D**) — Ereignis-Strang  
**Vorläufer:** `RECIPROCAL_EVENT_KOPPLUNG_v0` · `NO_COUPLING` · §1.1 JA · κ verdrahtet, r flach  
**Tick-Serie:** versiegelt  
**Proto:** `agents_b2g/emergence/reciprocity_amp_proto_v0/` · `PROTO_PASS` (3/3, 0.02s)  
**Capture:** `agents_b2g/emergence/reciprocity_amp_kopplung_capture.py`  
**Runner:** `scripts/run_reciprocity_amp_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/reciprocity_amp_kopplung_v0/`

### Freigabe-Vermerk

```text
Status: DRAFT v1 → BINDEND
Dokument: docs/RECIPROCITY_AMP_KOPPLUNG_v0_PREREG.md
Datum: 2026-08-26
Strang: 1c Reziprozitäts-Verstärkung
Zwei getrennte Primärfragen:
  P1  Relationale κ-Verstärkung (B≫C auf κ̄)
  P2  Relationale Phasenkohärenz (Gate B↔D, matched κ)
Arme: A baseline · B echt+endogen · C π+endogen · D π+exogen=κ̄_B
Proto-Seeds: 20262301…03 gesperrt
Sweep-Seeds: 20262401…06 · Spot 20262401
N=9 · r_floor=1/√N+0.15=0.483 · Δr_min=0.10 · ≥4/6 · α=0.05
Tick-Serie versiegelt · Hybrid VERBOTEN
```

### Warum Arm D (BINDEND-Blocker behoben)

Unter F8 endet Proto mit **κ̄_B ≈ 1.5** und **κ̄_C ≈ 0.2** (Faktor ~7.5).  
Arm C unterscheidet sich von B dann **nicht nur** in der Zuordnung, sondern auch in der
Kopplungsstärke. Gate B↔C und „§1.1 auf C“ wären konfundiert / trivial.

| Arm | Zuordnung | κ | Prüft |
|-----|-----------|---|-------|
| **A** | — | 0 | Baseline |
| **B** | echt (M) | endogen (F8) | Intervention |
| **C** | π(M) | endogen (F8) | **P1:** wächst κ relational? |
| **D** | π(M) | **exogen = κ̄_B** (matched) | **P2:** Kohärenz relational? |

**B↔C** → relationale **κ-Verstärkung** (Stärke selbst).  
**B↔D** → relationale **Phasenkohärenz** bei gleicher Stärke.  
Erst D macht P2 zurechenbar.

### HARKing-Sperre (strikt)

- Tick-Serie · `EVENT_DRIVEN` · `RECIPROCAL_EVENT` Sweep-Zellen  
- Proto `reciprocity_amp_proto_v0/` · Seeds `20262301–03`  
- Alle Seeds ≤ `20262399` für Sweep-/Gate-Zellen  

Neue Artefakte nur unter `reciprocity_amp_kopplung_v0/`.

### Abgrenzung

| Studie | Status | Befund |
|--------|--------|--------|
| Tick-Serie (7) | versiegelt | Arm C koppelt netzwerk-weit |
| `EVENT_DRIVEN_v0` | abgeschlossen | §1.1 JA · kein Gate |
| `RECIPROCAL_EVENT_v0` | abgeschlossen | §1.1 JA · κ verdrahtet · r flach |
| **dieser DRAFT** | offen | F8 Amplifikation · **P1 vs P2 getrennt · Arm D** |

Kein Hybrid. Delivery immer auf Sticky M.

---

## 0. Zweck

### 0.1 Freeze-Fakten (Engineering)

| Fakt | Quelle | Rolle |
|------|--------|-------|
| Proto A∧B | `PROTO_PASS` 3/3 | F0 Fitness |
| Diskrete Impulse · Event-Uhr | Ereignis-Strang | F1–F2 |
| Ordinal-ρ / Payload-ΔR | Proto | F3 |
| \(R\) v0.2 · \(\mathbf{P}_{1\ldots9}\) | Kontinuität | F4 |
| Inter-Arrival | F5 | F5 |
| Snapshot Δt=64 | F6 | F6 |
| Receipt-Gate | F7 | F7 |
| Positive Rückkopplung κ←κ+Δ | F8 | F8 Mechanik |
| N=9 · r_floor=0.483 | Vorab-Korrektur | Gate |
| Tick versiegelt · Hybrid verboten | Abschluss | Motiv |

**Nicht als bloßer Freeze-Nebensatz:** Proto-κ-Trennung B≫C ist **Primärbefund-Kandidat P1**
(§0.2 / §1.0), nicht nur „Selectivity-Hinweis“.

### 0.2 Zwei Primärfragen (getrennt)

**P1 — Relationale κ-Verstärkung (Stärke):**  
Erzeugt F8 unter Delivery auf M eine **signifikante Trennung** `κ̄_end` / `frac_amp`
Arm B ≫ Arm C (endogen), bei intakter Batterie?

*Proto-Hinweis (nicht Sweep-Outcome):* amp B=1.0 · C≤0.22 · κ̄_end B≈1.5 · C≈0.2.

**P2 — Relationale Phasenkohärenz (Ordnung):**  
Erzeugt dieselbe Mechanik einen **Gate-Abstand Arm B ↔ Arm D**
(D = π-Zuordnung, κ **exogen auf κ̄_B** gematcht), bei intakter Batterie —
**während** Arm D nach §1.1d `NO_COUPLING` bleibt?

P1 und P2 werden **getrennt** gelabelt. Ein Positiv nur auf B↔C (Stärke-Konfund)
zählt **nicht** als P2.

### 0.3 Vorbedingung — Batterie A∧B∧C (auf Arm B gemessen)

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **A** | Median \|ρ\| \(R\) vs. Schwarm | ≤ 0.90 · `n_corr ≥ 9` |
| **B** | `mae_norm` Partnerpermutation | ≥ 0.05 |
| **C** | mean \|ΔR(S_low)−ΔR(S_high)\| | ≥ 0.05 |

Sonst → `PRECONDITION_LOST` (keine P1/P2-Zählung auf dieser Stufe).

---

## 1. Hypothesen

### 1.0 P1 — Relationale κ-Verstärkung

**H1_κ:** Auf intakten α-Stufen (≥4/6 Seeds):  
`final_kappa_mean(B) − final_kappa_mean(C) ≥ Δκ_min` **und**
`frac_amp(B) − frac_amp(C) ≥ Δamp_min`.

**H0_κ:** Trennung unter Schwelle / Batterie verloren.

| Konstante | Wert |
|-----------|------|
| `Δκ_min` | **0.50** (absolut auf κ̄_end) |
| `Δamp_min` | **0.50** (absolut auf frac_amp) |

Proto lag weit darüber; Schwellen **vor** Sweep fixiert (kein HARKing aus Proto-Zahlen
als Gate-Zahlen außer als Motivationshinweis).

### 1.1 P2 — Relationale Phasenkohärenz (Gate B↔D)

**H1_φ:** Gate-Abstand B vs. D (≥4/6), Batterie auf B intakt,  
Arm D nicht mehrheitlich `COUPLED`.

**H0_φ:** Kein Gate B↔D, oder `PRECONDITION_LOST`, oder Arm D koppelt mehrheitlich.

### 1.1d Riskante Vorhersage (§1.1d — auf Arm D)

**Arm D bleibt auf vorbedingungs-intakten Stufen `NO_COUPLING` (≥4/6).**

Scheitert §1.1d → `KOPPLUNG_INVALID` (Stärke allein / Netzattraktor, Zuordnung egal).

**Nicht §1.1 auf Arm C:** C ist unter F8 absichtlich schwächer gekoppelt;
„C bleibt NO_COUPLING“ wäre keine riskante Vorhersage.

### 1.2 Rolle von Arm C (Bericht + P1)

Arm C liefert **P1** und den endogenen Kontrast.  
Kein Kohärenz-Gate B↔C als Primärlabel für P2.

---

## 2. Design

### 2.1 Dynamik — F0–F8

**Delivery:** REQUEST auf Sticky M. **Receipt:** an echten Absender.

\[
R_i(e_k)=a_i(1+\gamma_i)\bigl(S_k^{(i)}-b_i(\sigma_S)\bigr)
\]

**Arme B und C (endogen):**

```text
sig = signal_partner[i]   # B: M · C: π(M)
if receipt_from == sig:
    κ_i := min(κ_max, κ_i + α · h(R_sig))
    next_gap = base_gap / (1 + κ_i · h(R_sig))
else:
    κ_i := max(κ_floor, κ_i · decay)
    next_gap = base_gap
```

**Arm D (exogen, matched strength):**

```text
# Nach Abschluss der parallelen Arm-B-Zelle derselben (seed, α):
κ̄_B := mean_i κ_i^{final}(Arm B)
# Arm D: Signal π(M), aber Inter-Arrival mit festem κ = κ̄_B
# (kein F8-Wachstum; κ nicht endogen — Stärke von B übernommen)
next_gap = base_gap / (1 + κ̄_B · h(R_sig))   # sig = π(M)
```

**Match-Regel (bindend):** Pro Zelle `(seed, α)` zuerst Arm B laufen → `κ̄_B` speichern →
Arm D mit exakt diesem Skalar. Kein Cross-Seed-Pooling für den Match.

| Freeze | Inhalt |
|--------|--------|
| F0–F6 | wie Ereignis-Strang |
| F7 | endogene Amplifikation nur bei `receipt_from == signal_partner` (B/C) |
| F8 | positive Rückkopplung auf B/C |
| **F9** | **Arm D: κ exogen = κ̄_B, Zuordnung π(M)** |

**Parameter:**

| Symbol | Wert |
|--------|------|
| `κ_0` | 0.15 |
| `α` (amp_step) | Raster §2.3 |
| `κ_max` | 2.0 |
| `decay` | 0.98 |
| **N** | **9** |

**Verboten:** Hybrid · Amplitude-κ · Phase-Locking · Gate B↔C als P2-Ersatz.

### 2.2 Arme (Vierarm)

| Arm | Zuordnung (Signal) | κ | Primärrolle |
|-----|-------------------|---|-------------|
| **A** | — | 0 | Baseline / D_dyn-Vergleich |
| **B** | M | endogen F8 | Intervention |
| **C** | π(M) | endogen F8 | **P1** κ-Trennung |
| **D** | π(M) | **exogen κ̄_B** | **P2** Kohärenz + §1.1d |

Delivery/Receipt stets auf echter M-Kante.

### 2.3 Stufen und Seeds

| Parameter | Wert |
|-----------|------|
| `α` | `{0 · 0,10 · 0,25 · 0,40 · 0,60 · 1,00}` |
| Sweep-Seeds | `{20262401 … 20262406}` |
| Spot | `20262401` |
| Gesperrt | ≤ `20262399` |
| Warmup / Measure | 16 / ≥64 REQUEST · ≥48 Snapshots |
| **N** | **9** |

### 2.4 Spot-Checks

| Check | Seed | Erwartung | Fail |
|-------|------|-----------|------|
| α=0 Batterie | `20262401` | A∧B∧C PASS | `SIGNAL_BLIND` |
| Match-Sanity | `20262401` | bei α>0: `κ̄_D ≈ κ̄_B` (±1e-9 relativ) | `MATCH_FAIL` |
| P1-Sanity | `20262401` | `κ̄_B ≫ κ̄_C` berichtbar | Dokumentation |

---

## 3. Schwellen und Gates

### 3.1 Gemeinsam

| Regel | Wert |
|-------|------|
| Batterie | §0.3 auf Arm B |
| `α_stat` | 0.05 · `n_surrogates`=200 |
| `Δr_min` | **0.10** |
| **N** | **9** |
| **`r_floor`** | **`1/√N + 0.15 = 0.483`** |
| Mehrheit | ≥ **4/6** |

### 3.2 Gate P1 (κ)

Pro intakter α-Stufe: Seed zählt P1-Pass wenn  
`κ̄_B − κ̄_C ≥ Δκ_min` und `frac_amp_B − frac_amp_C ≥ Δamp_min`.  
Stufe P1-positiv wenn ≥4/6 Seeds.  
Gesamt P1: mindestens eine intakte α>0-Stufe P1-positiv.

### 3.3 Gate P2 (Phasenkohärenz B↔D)

Seed `COUPLED` für P2 wenn:

1. `p_B < α_stat`  
2. `D_dyn_B > 0`  
3. `r_B − r_D ≥ Δr_min`  
4. `r_B ≥ r_floor`

Stufe P2-positiv wenn Batterie-Mehrheit + Gate-Mehrheit ≥4/6.  
§1.1d: Arm D nicht mehrheitlich `COUPLED` auf intakten Stufen.

Kuramoto/D_dyn auf F6-Snapshots.

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | Spot α=0 Batterie FAIL |
| `MATCH_FAIL` | Arm-D-κ weicht von κ̄_B ab |
| `PRECONDITION_LOST` | keine intakte Stufe |
| `KOPPLUNG_INVALID` | §1.1d: Arm D mehrheitlich `COUPLED` |
| `P1_ONLY` | P1 positiv, P2 negativ (κ relational, Kohärenz nicht) |
| `P2_ONLY` | P2 positiv, P1 negativ (unerwartet; berichten) |
| `NO_COUPLING` | P1 und P2 negativ, §1.1d gehalten |
| `COUPLED_EMERGENT` / `COUPLED_FORCED` | P2 positiv (± Form) auf intakten Stufen |

**Hinweis:** `P1_ONLY` ist ein **gültiger wissenschaftlicher Abschluss**, kein Sweep-Fehler —
genau die Trennung, die Arm D erzwingt.

---

## 5. Ablauf

1. ~~Proto~~ `PROTO_PASS`  
2. **DRAFT v1** (dieses Dokument, Arm D) — User → BINDEND  
3. Capture + Runner (A/B/C/D · Match-Regel F9)  
4. Spot `20262401`  
5. Sweep × α × Seeds  
6. Freeze — keine Schwellen-Nachjustierung  

## 6. Freigabe

| Stufe | Status |
|-------|--------|
| PROTO_PASS | erreicht |
| DRAFT v0 | zurückgezogen (Dreiarm konfundiert) |
| **DRAFT v1** | erreicht |
| **BINDEND** | **erteilt 2026-08-26** |
| **Sweep** | freigegeben nach Spot PASS |

---

## 7. Checkliste vor BINDEND

| Anforderung | Status |
|-------------|--------|
| P1 und P2 getrennt formuliert | ✅ §0.2 / §1 |
| Arm D matched κ̄_B · π-Zuordnung | ✅ §2.2 / F9 |
| §1.1d auf D (nicht trivial auf C) | ✅ §1.1d |
| Gate Kohärenz = B↔D (nicht B↔C) | ✅ §3.3 |
| P1-Schwellen Δκ_min / Δamp_min fix | ✅ §1.0 |
| Batterie · N=9 · r_floor=0.483 | ✅ |
| Seeds / HARKing / Hybrid verboten | ✅ |
| **BINDEND** | ✅ 2026-08-26 |

---

## 8. Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | DRAFT v0 (Dreiarm) — BINDEND blockiert: C konfundiert (κ̄ 7.5× schwächer) |
| 2026-08-26 | **DRAFT v1:** Arm D · P1/P2-Trennung · §1.1d auf D · Gate B↔D |
