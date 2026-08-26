# Emergenz — Reziprozitäts-basierte Event-Kopplung: Arbeitsprotokoll (**DRAFT**)

**Arbeitstitel:** `RECIPROCAL_EVENT_KOPPLUNG_v0`  
**Status:** **BINDEND + Sweep abgeschlossen** — 2026-08-26 · Verdict `NO_COUPLING` · §1.1 JA  
**Kanonisches Pre-Reg:** `docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md`  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) — **Fortsetzung Ereignis-Strang** (nicht Tick-Serie)  
**Vorläufer:** `EVENT_DRIVEN_KOPPLUNG_v0` · Verdict `NO_COUPLING` · §1.1 gehalten · Gate B↔C fehlte  
**Tick-Serie:** `KOPPLUNG_SERIE_ABSCHLUSS.md` bleibt **versiegelt** (7× `INVALID`)  
**Proto:** `agents_b2g/emergence/reciprocal_event_proto_v0/` · Gate `PROTO_PASS` (3/3)  
**Capture:** `agents_b2g/emergence/reciprocal_event_kopplung_capture.py`  
**Runner:** `scripts/run_reciprocal_event_kopplung_v0_sweep.py`  
**Artefakte:** `agents_b2g/emergence/reciprocal_event_kopplung_v0/` · Ergebnis dort

### Freigabe-Vermerk

```text
Status: DRAFT → BINDEND → Sweep DONE
Verdict: NO_COUPLING · §1.1 JA · Batterie alle κ 6/6
Verdrahtung: κ angeschlossen (T_mean Δ≈−0.33 @ κ=1.2 vs 0; States≠)
r_B flach (Span≈0.028 < sd_pool≈0.045) — echtes Negativ, kein Wiring-Fail
Dokument: docs/RECIPROCAL_EVENT_KOPPLUNG_v0_PREREG.md
Seeds: Sweep 20262201–06 · Spot 20262201 · Proto 202621xx gesperrt
```

### HARKing-Sperre (strikt)

Nicht für Hypothesentests / Gate-Auswertung dieser Studie verwenden:

- Gesamte Tick-Kopplungs-Serie inkl. `EDGE_LOCAL_KOPPLUNG_v0`  
- `EVENT_DRIVEN_KOPPLUNG_v0` Sweep-Zellen / Seeds `20262001–06`  
  (Verdict `NO_COUPLING` und §1.1-Halten zitierbar; Zahlen nicht als Sweep-Outcome)  
- Proto `reciprocal_event_proto_v0/` und Seeds `20262101–03`  
- Alle Seeds ≤ `20262199` für Sweep-/Gate-Zellen  

Neue Seeds · neue Läufe · neue Artefakte unter `reciprocal_event_kopplung_v0/`.

### Abgrenzung

| Strang | Status | Was er zeigte |
|--------|--------|---------------|
| Tick-Serie (7 Studien) | **versiegelt** | Arm C koppelt netzwerk-weit → `KOPPLUNG_INVALID` |
| `EVENT_DRIVEN_v0` | abgeschlossen | Arm C bricht (§1.1 JA) · Arm B bricht mit → `NO_COUPLING` |
| **dieser DRAFT** | offen | κ nur bei Reziprozität → Arm B an, Arm C aus |

Kein Hybrid Tick/Event. Delivery bleibt auf Sticky M; nur der **Kopplungseingang**
unterscheidet Signal-Partner (B = M, C = π(M)).

---

## 0. Zweck

### 0.1 Freeze-Fakten (Engineering → Architektur)

| Fakt | Quelle | Rolle |
|------|--------|-------|
| Proto A∧B | `PROTO_PASS` 3/3 · ρ∈{0.15…0.34} · ΔR∈{1.34…1.56} | F0 |
| κ_on B=1.0 · C=0.0 | Proto Selectivity | F7 Kern |
| Diskrete Impulse · private Event-Uhr | Ereignis-Strang | F1–F2 |
| Ordinal-ρ / Payload-ΔR | Proto | F3 |
| \(R=a(1+\gamma)(S-b)\) · \(\mathbf{P}_{1\ldots9}\) | Kontinuität | F4 |
| Inter-Arrival als κ-Hebel | `EVENT_DRIVEN` F5 | F5 |
| Snapshot Δt=64 | `EVENT_DRIVEN` F6 | F6 |
| **Receipt-Gate** | User-Proto | **F7** |
| Tick-Serie versiegelt · Hybrid verboten | Abschluss | Motiv |

### 0.2 Forschungsfrage

Erzeugt **reziprozitäts-gegate Inter-Arrival-Kopplung**
(κ nur wenn Receipt-Absender = Signal-Partner; Delivery auf M; Signal B=M / C=π(M))
einen **Gate-Abstand Arm B ↔ Arm C** bei intakter Batterie A∧B∧C —
**während** Arm C nach §1.1 `NO_COUPLING` bleibt?

### 0.3 Vorbedingung (bindend, per κ) — Batterie A∧B∧C

Messung auf Event-Serien (ordinal), nicht Tick-EWMA:

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **A** | Median \|ρ\| \(R\)-Serie (Event-Index) vs. Schwarm-Mittel | ≤ 0.90 · `n_corr ≥ 9` |
| **B** | `mae_norm` unter Partnerpermutation Sticky-Event-Antworten | ≥ 0.05 |
| **C** | mean \|ΔR(S_low)−ΔR(S_high)\| | ≥ 0.05 |

Sonst → `PRECONDITION_LOST` (zählt nicht für κ\* / §1.1).

**Berichtspflicht (kein Gate):** `frac_coupling_on` Arm B vs. Arm C je Seed
(Proto-Erwartung: B≈1.0 · C≈0.0).

---

## 1. Hypothesen

**H1:** Bei hinreichendem κ entsteht Gate-Abstand B vs. C (≥4/6 Seeds),
Arm C bleibt nach Gate + Mehrheit **nicht** mehrheitlich `COUPLED`,
und die Per-κ-Batterie bleibt auf Arm B erhalten.

**H0:** Kein Gate-Abstand, oder `PRECONDITION_LOST`, oder Arm C koppelt mehrheitlich.

### 1.1 Riskante Vorhersage (§1.1)

**Arm C bleibt bei allen vorbedingungs-intakten κ-Stufen `NO_COUPLING`
(≥4/6 Seeds).**

Kontinuität zu `EVENT_DRIVEN_v0` (dort bereits gehalten). Scheitert §1.1 hier,
ist der Reziprozitäts-Hebel unzureichend → `KOPPLUNG_INVALID`.

### 1.2 Zusätzliche Riskanz (Selektivität)

Unter intakten κ: Median `frac_coupling_on` Arm B **≫** Arm C
(Richtwert aus Proto: B≥0.9 · C≤0.1 über ≥4/6 Seeds).  
Das ist **Bericht**, kein zusätzliches Gate-Label — Gate bleibt B↔C + §1.1.

---

## 2. Design

### 2.1 Dynamik — Freeze F0–F7

**Delivery (unverändert):** REQUEST \(i \to j^*_{\mathrm{true}}\) auf Sticky M.  
**Receipt (unverändert):** Empfänger sendet RECEIPT an den **echten** Absender.

**Antwort (nur am Impuls):**

\[
R_i(e_k)=a_i(1+\gamma_i)\bigl(S_k^{(i)}-b_i(\sigma_S)\bigr)
\]

**F5 + F7 — Inter-Arrival nur bei Reziprozität:**

```text
# Nach RECEIPT an Requester i, Absender = receipt_from:
sig = signal_partner[i]          # Arm B: M · Arm C: π(M)
base_gap = agent-private draw
if receipt_from == sig:
    next_gap = base_gap / (1 + κ · h(R_sig))   # κ aktiv
else:
    next_gap = base_gap                          # κ inaktiv
T_i := next_gap
```

Arm B: `sig = true partner` → Receipt vom Delivery-Partner trifft → κ an.  
Arm C: `sig = π(true)` → Receipt vom Delivery-Partner ≠ sig → κ aus.

| Freeze | Inhalt |
|--------|--------|
| **F0** | Proto `PROTO_PASS` |
| **F1** | Kein kontinuierliches \(\ell(t)\) / kein Tick-EWMA-Träger |
| **F2** | Agent-private Event-Uhr |
| **F3** | Ordinal-Event-Index für Batterie-ρ |
| **F4** | \(R\) v0.2 · \(\mathbf{P}_{1\ldots9}\) · keine Typ-Paar-Matrix |
| **F5** | κ-Hebel = **Inter-Arrival** (Amplitude verboten) |
| **F6** | Snapshot Δt=**64** · \(\varphi_i=2\pi\cdot(t_{\mathrm{last}}/T_i)\) |
| **F7** | **κ nur wenn `receipt_from == signal_partner`** |

**Verboten:** Hybrid Tick/Event · Amplitude-κ · globales `1+κ·h` pro Tick.

### 2.2 Arme

| Arm | κ | Delivery / Receipt | Signal-Partner |
|-----|---|--------------------|----------------|
| **A** | 0 | M | Formel aus (Gaps = base) |
| **B** | >0 | M | echte Sticky-Zuordnung M |
| **C** | >0 | M (unverändert) | π(M) — nur Kopplungseingang |

### 2.3 κ-Raster und Seeds

| Parameter | Wert |
|-----------|------|
| `κ` | `{0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}` |
| Sweep-Seeds | `{20262201 … 20262206}` |
| Spot | `20262201` |
| Gesperrt | ≤ `20262199` (inkl. Proto `20262101–03`, Event-Sweep `202620xx`) |
| Warmup-Events | 16 REQUEST/Agent verwerfen |
| Measure | ≥ 64 REQUEST/Agent · ≥ 48 Snapshots (Δt=64) |

### 2.4 Spot-Checks (nach BINDEND, vor Sweep)

| Check | Seed | Erwartung | Fail-Label |
|-------|------|-----------|------------|
| κ=0 Batterie | `20262201` | A∧B∧C PASS | `SIGNAL_BLIND` |
| F7-Sanity | `20262201` | bei κ>0 Spot optional: `frac_on` B≫C berichtbar | Dokumentationspflicht |

---

## 3. Schwellen und Gate

Kontinuität (**Zahlen nicht nach Daten senken**):

| Regel | Wert |
|-------|------|
| Batterie A/B/C | §0.3 |
| Gate `COUPLED` | (1) `p < α` (2) `D_dyn > 0` (3) `r_B − r_C ≥ Δr_min` (4) `r_B ≥ r_floor` |
| `α` | 0.05 · `n_surrogates` = 200 |
| `Δr_min` | **0.10** |
| `r_floor` | **0.34** |
| Mehrheit | ≥ **4/6** |
| §1.1 | Arm C `NO_COUPLING` ≥4/6 auf intakten κ |

Kuramoto/D_dyn auf F6-Snapshots (nicht pro Einzel-Event).

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | Spot κ=0: Batterie scheitert |
| `PRECONDITION_LOST` | Batterie unter κ verloren |
| `KOPPLUNG_INVALID` | §1.1: Arm C mehrheitlich `COUPLED` |
| `NO_COUPLING` | Gate B↔C auf keinem intakten κ |
| `COUPLED_EMERGENT` / `COUPLED_FORCED` | Gate (± Form) auf intakten κ |

---

## 5. Ablauf

1. ~~16s-Proto~~ **`PROTO_PASS`** (2026-08-26) · κ_on B=1.0 / C=0.0  
2. **DRAFT** (dieses Dokument) — User → BINDEND  
3. Capture + Runner (F0–F7)  
4. Spot Seed `20262201`  
5. Sweep A/B/C × κ × `20262201–06`  
6. Freeze Artefakte — keine Schwellen-Nachjustierung nach Datenblick  

## 6. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **PROTO_PASS** | erreicht |
| **DRAFT** | **dieser Stand** |
| **BINDEND** | ausstehend (User) |
| **Sweep** | gesperrt bis BINDEND + Spot PASS |

---

## 7. Checkliste vor BINDEND

| Anforderung | Status |
|-------------|--------|
| Frage: Reziprozitäts-κ → Gate B↔C + §1.1? | ✅ §0.2 |
| Ereignis-Strang · Tick versiegelt · Hybrid verboten | ✅ Kopf |
| H1 / H0 / §1.1 / Selektivitäts-Bericht | ✅ §1 |
| Batterie A∧B∧C | ✅ §0.3 |
| F0–F6 Kontinuität Event-Strang | ✅ §2.1 |
| F7 Receipt-Gate | ✅ §2.1 |
| Arme A/B/C · Delivery M · Signal π(M) | ✅ §2.2 |
| Seeds `20262201–06` | ✅ §2.3 |
| Gate-Zahlen unverändert | ✅ §3 |
| HARKing | ✅ Kopf |
| **BINDEND** | ⬜ User |

---

## 8. Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | DRAFT v0 nach `PROTO_PASS` reciprocal-event (κ_on B=1.0 / C=0.0) |
