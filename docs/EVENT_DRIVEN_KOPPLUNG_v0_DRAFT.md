# Emergenz — Ereignisbasierte Kopplung (Discrete Event-Driven): Arbeitsprotokoll (**DRAFT**)

**Arbeitstitel:** `EVENT_DRIVEN_KOPPLUNG_v0`  
**Status:** **DRAFT → BINDEND** — siehe `docs/EVENT_DRIVEN_KOPPLUNG_v0_PREREG.md` (2026-08-26)  
**Hinweis:** F5 Inter-Arrival · F6 Snapshot Δt=64 festgeschrieben. Dieses DRAFT-Dokument ist historisch.  
**Charakter:** Interventionsstudie (Dreiarm A/B/C) — **neuer Strang**  
**Abgrenzung:** Kopplungs-Serie (`KOPPLUNG_SERIE_ABSCHLUSS.md`, 7× `INVALID`) bleibt **versiegelt**  
**Proto:** `agents_b2g/emergence/event_driven_proto_v0/` · Gate `PROTO_PASS` (3/3, 0.01s)  
**Capture (geplant nach BINDEND):** `agents_b2g/emergence/event_driven_kopplung_capture.py`  
**Runner (geplant):** `scripts/run_event_driven_kopplung_v0_sweep.py`  
**Artefakte (geplant):** `agents_b2g/emergence/event_driven_kopplung_v0/`

### Freigabe-Vermerk

```text
Status: PROTO_PASS → DRAFT  ←  BINDEND ausstehend
Dokument: docs/EVENT_DRIVEN_KOPPLUNG_v0_DRAFT.md
Datum: 2026-08-26
Strang: 1 Ereignisbasiert
Mechanik: diskrete Impulse · agent-private Event-Uhr · kein kontinuierliches ℓ(t)
Proto-Seeds: 20261901…03 (HARKing-gesperrt für Sweep)
Sweep-Seeds (geplant): 20262001…06 · Spot 20262001
Gate-Kontinuität: Δr_min=0.10 · r_floor=0.34 · ≥4/6 · α=0.05
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

### 0.1 Freeze-Fakten (Engineering → Architektur)

| Fakt | Quelle | Rolle |
|------|--------|-------|
| Proto-Gate A∧B | `PROTO_PASS` 3/3 · ρ∈{0.17…0.69} · ΔR∈{1.66…1.96} | F0: Strang darf DRAFT werden |
| Diskrete Impulse | `event_driven_proto.py` | F1: kein kontinuierliches ℓ(t) |
| Agent-private Event-Uhr | Inter-Arrival per `(seed, agent_id, k)` | F2: kein globaler Metronom |
| Ordinal-Alignment | Korrelation über Event-Index, nicht Wall-Clock-Tick | F3: Messbasis |
| \(R = a(1+\gamma)(S-b)\), Gas→\(\mathbf{P}_{1\ldots9}\) | Proto + Kontinuität | F4 |
| Serie versiegelt | `KOPPLUNG_SERIE_ABSCHLUSS.md` · `45e7f4c6` | Motiv, nicht Datenquelle |

### 0.2 Forschungsfrage

Erzeugt eine **ereignisbasierte** Intervention (diskrete Impulse, agent-private
Event-Uhr, **kein** kontinuierliches \(\ell_{ij}(t)\)) unter κ einen
**Gate-Abstand Arm B ↔ Arm C** — shuffle-sensitive Kohärenz — **während** die
Batterie A∧B∧C je κ erhalten bleibt?

### 0.3 Vorbedingung (bindend, per κ) — Batterie A∧B∧C

Messung auf **Event-Serien** (ordinal), nicht auf Tick-EWMA-Trägerwellen:

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **A** | Median \|ρ\| der agentischen \(R\)-Serie (Event-Index) zum Schwarm-Mittel | ≤ 0.90 · `n_corr ≥ 9` (9 Agenten) bzw. ≥14 wenn Sticky-Kanten ≥14 |
| **B** | `mae_norm` unter Partnerpermutation der Sticky-/Partner-Event-Antworten | ≥ 0.05 |
| **C** | mean \|ΔR(S_low)−ΔR(S_high)\| bzw. Payload-Klassen-Abstand (Antwort-Heterogenität) | ≥ 0.05 |

**Regel:** Nach jedem Zellenlauf (Seed × κ × Arm-B):

- A∧B∧C → **vorbedingungs-intakt**; Gate B vs. C auswertbar.  
- Sonst → **`PRECONDITION_LOST`** (keine Umdeutung).  
- Zählt nicht für κ\* / Form / §1.1-Mehrheit.

---

## 1. Hypothesen

**H1:** Bei hinreichendem κ entsteht Gate-Abstand B vs. C (≥4/6), Arm C bleibt
nach Gate + Mehrheit **nicht** mehrheitlich `COUPLED`, und die Per-κ-Batterie
bleibt auf Arm B erhalten.

**H0:** Kein Gate-Abstand, oder Batterie verloren (`PRECONDITION_LOST`), oder
Arm C koppelt mehrheitlich (§1.1 fail).

### 1.1 Riskante Vorhersage (§1.1)

**Arm C bleibt bei allen vorbedingungs-intakten κ-Stufen `NO_COUPLING`
nach Gate + Mehrheitsregel (≥4/6 Seeds).**

κ-Stufen mit `PRECONDITION_LOST` zählen nicht gegen §1.1.

*Riskanz:* Die Serie scheiterte unter kontinuierlicher Modulation. Ereignisbasis
muss die Trägerwelle zerstören — sonst erneut `KOPPLUNG_INVALID`.

---

## 2. Design

### 2.1 Dynamik — Freeze F0–F5

**Ereignis:** Impuls \(e_k^{(i)} = (t_k^{(i)}, S_k^{(i)})\) nur für Agent \(i\),  
Inter-Arrival und Payload aus agent-privater PRNG-Kette (crc32-Familie),  
**kein** gemeinsamer Tick-Loop als Kopplungsträger.

**Antwort (nur am Impuls):**

\[
R_i(e_k)=a_i\bigl(1+\gamma_i\bigr)\bigl(S_k^{(i)}-b_i(\sigma_S)\bigr)
\]

\(\gamma\) nur bei eigenem Impuls aktualisiert (event-triggered), kein Decay-pro-Tick
als globaler Sync-Kanal.

**Intervention κ (ereignisgebunden, ersetzt Tick-`1+κ·h`):**

```text
# Nur wenn Impuls die Sticky-Kante (i → j*) betrifft:
factor = 1 + κ · h(R_signal(i, j*))
# Verschiebt nächsten Inter-Arrival von i  ODER  skaliert Impuls-Amplitude
# — eine Variante vor BINDEND als F5 festziehen (Spot entscheidet nicht nach Daten)
```

| Freeze | Inhalt |
|--------|--------|
| **F0** | Proto `PROTO_PASS` — DRAFT erlaubt |
| **F1** | Kein kontinuierliches \(\ell_{ij}(t)\) / kein Tick-EWMA als Träger |
| **F2** | Agent-private Event-Uhr |
| **F3** | Ordinal-Event-Index für ρ / Batterie |
| **F4** | \(R\)-Formel v0.2 · \(\mathbf{P}_{1\ldots9}\) aus Gas · keine Typ-Paar-Matrix |
| **F5** | κ-Hebel: **Inter-Arrival-Modulation** (Default-Kandidat) — vor BINDEND bestätigen; Amplitude-Alternative nur wenn Spot κ=0 Batterie mit Interval-Hebel FAIL |

**Verboten in diesem Strang:** globale Tick-Phase als Kopplungsmedium;
Wiederverwendung von `update_sender_interval` auf jedem Swarm-Tick ohne Event.

### 2.2 Arme

| Arm | κ | Delivery / Events | Kopplungs-Signal |
|-----|---|-------------------|------------------|
| **A** | 0 | echte Event-Uhren + Sticky M | Formel aus |
| **B** | >0 | M unverändert | `j*` = echte Sticky-Zuordnung |
| **C** | >0 | M unverändert (Events real) | `j*` aus π(M); nur Signal permutiert |

Arm C: Delivery/Event-Realität auf M; Shuffle nur am Kopplungseingang
(`permute_sticky_map`, Kontinuität).

### 2.3 κ-Raster und Seeds

| Parameter | Wert |
|-----------|------|
| `κ` | `{0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}` |
| Sweep-Seeds | `{20262001 … 20262006}` |
| Spot | `20262001` |
| Gesperrt | ≤ `20261999` (inkl. Proto `20261901–03`) |
| Events/Agent (Sweep) | ≥ 64 (Proto-Kontinuität; vor BINDEND fixieren) |
| Warmup-Events | 16 (verwerfen vor Maßfenster) |

### 2.4 Spot-Checks (vor Sweep, bindend nach BINDEND)

| Check | Seed | Erwartung | Fail-Label |
|-------|------|-----------|------------|
| κ=0 Batterie | `20262001` | A∧B∧C PASS | `SIGNAL_BLIND` |
| F1-Sanity | `20262001` | kein Tick-EWMA-Pfad aktiv | Dokumentationspflicht |

---

## 3. Schwellen und Gate

Kontinuität zur Serie (**Zahlen nicht nach Daten senken**):

| Regel | Wert |
|-------|------|
| Batterie A/B/C | §0.3 |
| Gate `COUPLED` | (1) `p < α` (2) `D_dyn > 0` (3) `r_B − r_C ≥ Δr_min` (4) `r_B ≥ r_floor` |
| `α` | 0.05 · `n_surrogates` = 200 |
| `Δr_min` | **0.10** |
| `r_floor` | **0.34** |
| Mehrheit | ≥ **4/6** |
| §1.1 | Arm C `NO_COUPLING` ≥4/6 auf intakten κ |

Kuramoto / D_dyn: auf Event-getriggerten Zustands-Snapshots (nur Impuls-Zeiten
oder Impuls-getriebene Phase) — **nicht** auf dichter Tick-Phase der alten Serie.
Exact Snapshot-Regel vor BINDEND in Capture-Spec festhalten.

---

## 4. Verdict-Labels

| Label | Bedeutung |
|-------|-----------|
| `SIGNAL_BLIND` | Spot κ=0: Batterie scheitert |
| `PRECONDITION_LOST` | Batterie unter κ verloren |
| `KOPPLUNG_INVALID` | §1.1: Arm C mehrheitlich `COUPLED` |
| `NO_COUPLING` | kein intaktes κ mit Gate B↔C |
| `COUPLED_EMERGENT` / `COUPLED_FORCED` | Gate (± Form) auf intakten κ |

---

## 5. Ablauf

1. ~~16s-Proto-Gate~~ **`PROTO_PASS`** (2026-08-26)  
2. **DRAFT** (dieses Dokument) — Freigabe User → BINDEND  
3. Capture + Runner (F0–F5, Arme)  
4. Spot Seed `20262001`  
5. Sweep A/B/C × κ × `20262001–06`  
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
| Frage: Event-Dynamik → Gate B↔C? | ✅ §0.2 |
| Neuer Strang · Serie versiegelt | ✅ Kopf |
| H1 / H0 / §1.1 riskant | ✅ §1 |
| Batterie A∧B∧C (Event-Serien) | ✅ §0.3 |
| F0–F4 gesetzt | ✅ §2.1 |
| F5 κ-Hebel final wählen | ⬜ vor BINDEND |
| Snapshot-Regel Kuramoto/D_dyn | ⬜ vor BINDEND |
| Arme A/B/C · π(M) | ✅ §2.2 |
| Seeds `20262001–06` | ✅ §2.3 |
| Gate-Zahlen unverändert | ✅ §3 |
| HARKing | ✅ Kopf |
| **BINDEND** | ⬜ User |

---

## 8. Änderungsprotokoll

| Datum | Änderung |
|-------|----------|
| 2026-08-26 | DRAFT v0 nach `PROTO_PASS` Strang 1 |
