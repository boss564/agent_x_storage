# Paper Feed-Gap — Invariante + Socket↔Tick-Konkordanz (Pre-Reg)

**Status:** FREIGABE (2026-08-29) · Review-Schärfungen S1–S4 + methodische Korrektur  
**Amendments (append-only):** **FGDC-A1** (2026-08-30) — WORM-H0-Abdeckung · siehe §9  
**Parent:** [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) §7 Gap-Filter · §8 / §8.1  
**Exit-Impl:** [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) (I2/I3)  
**Scope:** Live-Shadow · ETHUSDT · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Nicht Scope:** BTCUSDT / Multi-Asset · Strang B / Sizing · k-Retuning

**Branch:** `feature/feed-gap-concordance`

---

## 0. Was dieses Dokument **nicht** ist

„Wir messen Tick-Rate, Latenz und Lückenhäufigkeit“ ist **Instrumentierung**.
Dafür braucht es kein Pre-Reg: Es gibt kein Urteil, das nach Datenblick
verschoben werden könnte.

**Früherer ENTWURF-Fehler (korrigiert vor Implementierung):** Tick-Spacing-Gaps
(I1) und `hold_seconds_delta`-Ablehnungen (I2) sind **keine** zwei unabhängigen
Instrumente. Beide leiten sich aus derselben Tick-Zeitreihe mit derselben
Schwelle ab. Sei `t_prev` der letzte Tick vor der Deadline und `t_exit` der
erste gültige Tick danach:

```text
delta        = t_exit − deadline
gap-Kandidat = t_exit − t_prev
da t_prev ≤ deadline:   delta ≤ t_exit − t_prev
```

Daraus folgt strukturell: **`delta > 30 ⇒ Gap > 30` und Fenster-Überschneidung**.
Also immer:

```text
n_hold_delta_exceeded  ≤  n_gap_exit_window_hits_tick     (Invariante)
```

Die Zeile „I2 ≫ I1“ war **nicht beobachtbar**. `Δ` als Betrag suggerierte
Zweiseitigkeit, die es nicht gibt. Was `|I1−I2|≤1` prüfte, war Geometrie
(Restwartezeit &lt; 30 s trotz großer Lücke), keine Kreuzvalidierung — entgegen §0.

**Korrektur (beide Auswege):**

1. **Invariante H_inv:** `n_hold_delta_exceeded ≤ n_gap_exit_window_hits_tick`.
   Verletzung = Fehler (Clock-Skew, fehlende Gap-Writes, Restart-Artefakt).
2. **Echte Unabhängigkeit H2:** WebSocket **Disconnect/Reconnect** (`source:
   "socket"`) vs. Tick-Spacing (`source: "tick_spacing"`). Zwei Schichten,
   ein Phänomen; Auseinanderfallen ist informativ.

---

## 1. Fragestellung

Über 3–4 Tage Live-Feed **ohne** Lückenbehandlung im Exit-Pfad (Parent §8.1)
sollten **einige** Round-Trips am Hold-Delta scheitern. Parallel: Socket-Abbrüche
und Tick-Lücken sollen im Exit-Fenster **übereinstimmen** (±1), und die
Tick↔Delta-Invariante darf nie verletzt werden.

---

## 2. Definitionen (S1–S3)

### 2.1 S1 — Gap-Schwelle (explizit, Freeze-konsistent)

```text
gap_dt_s = PAPER_EXIT_GAP_DT_S = 30.0
```

**Identisch** mit:

| Ort | Verwendung |
|-----|------------|
| Parent §7 Kalibrierung | Δt &gt; `gap_dt_s` aus σ-Sample ausschließen |
| Exit-Impl I3 | Exit nur bei Tick mit Δt ≤ `gap_dt_s` |
| Diese Pre-Reg | Tick-Spacing-Gap ⇔ Δt &gt; `gap_dt_s` |

Keine andere Schwelle. Keine Nachjustierung auf Konkordanz.

### 2.2 S2 — `feed_gaps.jsonl` Schema (append-only)

Pfad Cluster: `/data/audit/feed_gaps.jsonl`  
Lokal Default: `{RAAS_DATA_ROOT}/audit/feed_gaps.jsonl`  
Env: `PAPER_FEED_GAPS_PATH`

Jede Zeile (Hash-Kette analog `paper_edges.jsonl`):

| Feld | Typ | Pflicht | Bedeutung |
|------|-----|---------|-----------|
| `event_id` | str | ja | UUID |
| `source` | enum | ja | `tick_spacing` \| `socket` \| `restart_marker` |
| `symbol` | str | ja | z. B. `ETHUSDT` |
| `gap_start_ts` | ISO-8601 UTC | ja* | Lückenbeginn (`t_prev` bzw. Disconnect) |
| `gap_end_ts` | ISO-8601 UTC | ja* | Lückenende (`t_tick` bzw. Reconnect) |
| `gap_duration_s` | float | ja* | `gap_end − gap_start` |
| `gap_dt_threshold_s` | float | ja | Erfassungsschwelle (30) |
| `in_exit_window` | bool | ja* | Überschneidung mit Exit-Fenster (s.u.) |
| `exit_window_start` | ISO-8601 \| null | ja | `hold_deadline` wenn Position offen, sonst null |
| `exit_window_end` | ISO-8601 \| null | ja | bei Schreiben: `exit_ts` wenn RT schon geschlossen, sonst null (nachträglich nicht rewrite — Treffer-Zählung bei Auswertung aus Edges) |
| `round_trip_id` | str \| null | ja | Link: `entry_signal_id` / Edge-`edge_id`-Vorläufer; null wenn flat |
| `fsm_state` | str | ja | FSM zum Event |
| `position_open` | bool | ja | |
| `prev_hash` / `hash` | str | ja | Kette |
| Charter | bools | ja | `live_execution=false`, `order_send=false`, `not_investment_advice=true`, `diagnostic_only=true` |

\* Bei `restart_marker`: `gap_start_ts` = Restart-Zeit, `gap_end_ts`/`gap_duration_s`/`in_exit_window` dürfen null/false sein (Marker, keine Lücke).

**Auswertung `in_exit_window` (normativ bei Konkordanz-Skript):**  
Für jedes Gap-Event und jeden abgeschlossenen RT (`hold_expired`, freeze-k):

```text
Fenster = [hold_deadline_ts, exit_tick_ts]
hit     ⇔  [gap_start_ts, gap_end_ts] ∩ Fenster ≠ ∅
```

`in_exit_window` auf der Schreibzeile ist **Hinweis** (bekanntes Fenster zum Schreibzeitpunkt);
maßgeblich für H2/H_inv ist die Auswertung gegen Edges.

### 2.3 Exit-Fenster

```text
hold_deadline_ts = entry_tick_ts + hold_seconds_target
Fenster          = [hold_deadline_ts, exit_tick_ts]   # nur hold_expired
```

Früh-Gaps (schließen vor `hold_deadline_ts`) zählen **nicht**.

### 2.4 Zählgrößen

```text
n_gap_exit_window_hits_tick   =
  # RTs (freeze-k, hold_expired) mit ≥1 tick_spacing-Gap ∩ Fenster

n_gap_exit_window_hits_socket =
  # RTs mit ≥1 socket-Gap ∩ Fenster

n_hold_delta_exceeded         =
  # Edges reason_code == hold_delta_exceeded
```

Ein RT mit mehreren Gaps im Fenster zählt **einmal** (pro Quelle).  
Rohzähler `n_gaps_total_{source}` sind deskriptiv.

### 2.5 S3 — Edge-Cases (vorab)

| Fall | Regel |
|------|-------|
| **Pod-Restart während Gap** | Persistiere `last_tick_ts` (Feed-Gap-State). Nach Restart: bei nächstem Tick Δt &gt; 30 s → `tick_spacing`-Gap mit `gap_start=last_tick_ts`. Zusätzlich `restart_marker`-Zeile. Ohne Persistenz wäre der Gap unsichtbar — verboten. |
| **Mehrere Gaps im Exit-Fenster** | Roh: mehrere JSONL-Zeilen. Hit-Zähler: **ein** RT-Hit pro Quelle. |
| **Force-Exit** (`exit_reason=force_exit`) | Kein B2-Sample; Fenster für Konkordanz **leer** / RT ausgeschlossen. `exit_ts &lt; hold_deadline` möglich → kein Fenster-Hit. |
| **Eligible trotz Gap** | `t_prev` weit vor Deadline, `t_exit` knapp danach: Gap groß, delta ≤ 30 → eligible. Erlaubt; erhöht `n_gap_…_tick` ohne `n_hold_delta_exceeded` — **kein** Invarianten-Bruch. |
| **Socket still, keine Tick-Lücke** | Reconnect schnell; H2 kann DISCORDANT werden (informativ). |
| **Tick-Lücke, kein Socket-Event** | Server sendet nicht / Client merkt Abbruch nicht — H2 DISCORDANT (informativ). |

---

## 3. Hypothesen & Auswertungsregel

**Fenster W:** 72–96 h ab Dual-Start (Tick-Gap-Writer **und** Socket-Listener aktiv; UTC im Ergebnisdok).

### H0 — Messbarkeit

In W: Gap-JSONL existiert (ggf. nur Marker) **und** ≥ 1 freeze-k RT in Edges.  
Sonst: Studie nicht aussagekräftig.

**WORM-Zweig (retrospektiv):** siehe **§9 Amendment FGDC-A1** — nicht im Original-Freeze
(Commit `b1f92b99`, Hash unten); gilt erst ab Amendment-Zeitstempel.

### H1 — §8.1 Feed-Qualitäts-Erwartung

| Ausgang | Kriterium |
|---------|-----------|
| **CONFIRMED** | `n_hold_delta_exceeded ≥ 1` |
| **NOT_CONFIRMED** | `== 0` und ≥ 20 freeze-k Edges in W |
| **INCONCLUSIVE** | `== 0` und &lt; 20 Edges |

### H_inv — Tick↔Delta-Invariante (einseitig)

```text
n_hold_delta_exceeded  ≤  n_gap_exit_window_hits_tick
```

| Ausgang | Kriterium |
|---------|-----------|
| **HOLD** | Ungleichung erfüllt |
| **BROKEN** | `n_hold_delta_exceeded > n_gap_exit_window_hits_tick` → Instrument-/Persistenzfehler |

Kein Betragsstrich. „I2 ≫ I1“ ist kein Interpretationspfad — es ist ein Bug.

### H2 — Socket↔Tick-Konkordanz (echte Unabhängigkeit)

```text
Δ_conc = | n_gap_exit_window_hits_socket − n_gap_exit_window_hits_tick |
```

| Ausgang | Kriterium |
|---------|-----------|
| **CONCORDANT** | `Δ_conc ≤ 1` |
| **DISCORDANT** | `Δ_conc ≥ 2` |

**S4 — Warum ±1 (nicht ±0 / ±2):** Bei kleinem n (wenige Exit-Fenster-Hits in 3–4 Tagen) erzeugt **ein** Grenz-RT (Deadline knapp in/außerhalb der Lücke) oder **ein** Restart-/Reconnect-Timing-Versatz bereits Δ=1. ±0 wäre überstreng und würde Ops-Rauschen als Falsifikation werten. ±2 würde echte Schicht-Diskrepanz (mehrere stille Server-Lücken oder ungemeldete Disconnects) verschlucken. ±1 = ein Ereignis Toleranz bei kleinem n; ab Δ≥2 strukturelles Auseinanderfallen.

**DISCORDANT-Interpretation (vorab):**

| Muster | Verdacht |
|--------|----------|
| Socket ≫ Tick | Abbruch gemeldet, Reconnect vor spürbarer Tick-Lücke / Schwelle |
| Tick ≫ Socket | Server sendet nicht; Client-Socket bleibt „verbunden“ |

---

## 4. Persistenz-Disziplin (drittes Vorkommen)

| Anti-Pattern | Gegenmaßnahme |
|--------------|---------------|
| `coverage_gate.json` überschrieben | kein Rewrite der Gap-Historie |
| Image imperativ ohne Herkunft | Dual-Start + Image-Tag im Ergebnisdok |
| Prometheus-only | Reset/Retention → Abgleich zerfällt |
| Pre-Reg §3 in-place während Fenster W | **Amendment** append-only (`original_pre_reg_hash`, `amendment_id`) — §9 |

**Normativ:** Primärspeicher = append-only JSONL. Prometheus nur Ops
(`feed_gap_events_total{source=…}`, tick-rate). Auswertung liest **nur** JSONL.
`last_tick_ts` persistieren (State-Datei neben Gaps).

---

## 5. Implementierungs-Checkliste (nach Freigabe)

| # | Inhalt |
|---|--------|
| 1 | Tick-Spacing-Detektor (Δt &gt; 30 s), gleiche Schwelle wie Exit-FSM |
| 2 | Socket Disconnect/Reconnect → `source=socket` |
| 3 | `feed_gaps.jsonl` Writer + `last_tick_ts`-State + `restart_marker` |
| 4 | Konkordanz-Skript: H0 / H1 / H_inv / H2 |
| 5 | Prometheus Ops-only |
| 6 | Smoke: künstliche Pause &gt; 30 s; Socket-Event ohne Netz; Invariante; Schema |

---

## 6. Charter & Anti-HARKing

- Paper-only · Single-Symbol ETHUSDT in W  
- `k=4966` und `gap_dt=30` unverändert  
- Strang B weiter geblockt bis `n_eligible_at_freeze_k ≥ 50`  
- Kein Retuning nach DISCORDANT / BROKEN — nur neues Amendment (§9)

---

## 7. Ergebnisdok

Nach W: `docs/PAPER_FEED_GAP_DELTA_CONCORDANCE_ERGEBNIS.md` (append-only anlegen).  
H0 / H1 / H_inv / H2 + Dual-Start UTC + Image-Tag.

---

## 8. Freigabe-Checkliste

- [x] §0: Unabhängigkeit = Socket vs Tick — nicht Tick vs Delta  
- [x] H_inv einseitig; H2 ±1 begründet (S4)  
- [x] S1 Schwelle = 30 s = §7 / I3  
- [x] S2 Schema inkl. `round_trip_id` / Fensterfelder  
- [x] S3 Restart / Multi-Gap / Force-Exit  
- [x] JSONL primär; Prometheus Ops  
- [x] Reviewer-Freigabe → Implementierung

---

## Siehe auch

- [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) §8.1  
- [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md)  
- `prototypes/raas_paper_trading/paper_edge_sample.py`

---

## 9. Amendments (append-only)

Sealed Pre-Reg-Hash (Commit `b1f92b99`, FREIGABE 2026-08-29, **unverändert**):

```text
original_pre_reg_hash = 0b2ea75d2b18e90b52dcaa158fcd5bcead6c36d0d7ff73ba3aafc40401901950
```

Register (JSONL): [`PAPER_FEED_GAP_DELTA_CONCORDANCE_AMENDMENTS.jsonl`](PAPER_FEED_GAP_DELTA_CONCORDANCE_AMENDMENTS.jsonl)

### 9.1 FGDC-A1 — WORM-H0 Abdeckung + Restart-Unbeobachtbar (2026-08-30)

| Feld | Wert |
|------|------|
| `amendment_id` | `FGDC-A1` |
| `created_at` | `2026-08-30T05:28:16.414774+00:00` |
| `original_pre_reg_hash` | `0b2ea75d2b18e90b52dcaa158fcd5bcead6c36d0d7ff73ba3aafc40401901950` |
| `prev_amendment_hash` | `0000000000000000000000000000000000000000000000000000000000000000` |
| `amendment_hash` | `5f2c47d7bf7a91430fca50baeaf3689630ef29e8abdb5f11c4d87f76385f4d41` |

**Begründung:** Review-Befund vor Audit-Lauf Fenster W: (1) WORM-Retrospektive
zählte **Intervalle** statt **Zeit** — ein 3-s-Tick-Paar konnte `null_gaps_proven`
auslösen; (2) Pod-Restart erzeugte große WORM-Δt ohne `tick_spacing` — weder
`null_gaps_proven` noch `writer_failed`, sondern **unbeobachtbar** via
`restart_marker`; (3) Schwelle **vor** erstem Audit-Lauf festgelegt (Anti-HARKing,
Analogie k-Freeze). Audit noch **nicht** gelaufen zum Amendment-Zeitpunkt.

**Normativ ab FGDC-A1 (§3 H0 WORM-Zweig):**

| Regel | Wert |
|-------|------|
| `MIN_OBSERVABLE_FRACTION` | **0.80** (80 % der Fensterzeit beobachtbar) |
| Dual-Start W (Default Audit) | `2026-08-29T13:17:46+00:00` |
| `null_gaps_proven` | `coverage_fraction ≥ 0.80` **und** kein beobachtbarer Δt &gt; `gap_dt` ohne `tick_spacing` |
| `INSUFFICIENT_COVERAGE` | `coverage_fraction < 0.80` — ehrlicher Ausgang, **kein** gerettetes „belegt" |
| `writer_failed` | beobachtbarer Δt &gt; `gap_dt` ohne deckende `tick_spacing`-Zeile |
| Unbeobachtbar | WORM-Intervall überspannt `restart_marker` — aus beiden Zweigen ausgeschlossen |

**H0 (Konkordanz-Skript):** `h0_measurable` via Gap-JSONL **oder** WORM-Zweig nur
wenn `null_gaps_proven`; bei `INSUFFICIENT_COVERAGE` → `h0_branch=insufficient_coverage`,
H0 nicht erfüllt (sofern keine Gap-JSONL).

**Klassifikation:** Methodische Schärfung vor Ergebnisdok — **kein** Retuning nach
Datenblick (Audit ungelaufen).
