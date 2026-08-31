# TUI Dashboard — Scope-Note (ENTWURF)

**Status:** ENTWURF (2026-08-31) — **kein Code vor FREIGABE**  
**Erstellt:** 2026-08-31  
**Strang:** Einzelstrang, passives Diagnose-TUI (Host)  
**Charter:** `diagnostic_only` · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Parent:** [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md) · [`AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) · [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md)  
**Außerhalb:** Fenster-W-Daemon, Helm, `POSITION_SIZING_ENABLED`, Shadow Evaluator (Strang B.1), Order-Pfad

---

## §0 Abgrenzung — was dies NICHT ist

- Kein Prognose- oder Analyse-Tool — **I5**: es deutet keine Daten.
- Kein Handels-Assistent — keine Empfehlung, kein „should".
- Kein 9-Agenten-Geheimdienst — kein Scope-Creep über vier Panels hinaus.
- Kein Eingriff in Daemon, Helm, Fenster W, Order-Pfad.
- Kein neuer Daten-Producer — schreibt keine `.jsonl`.
- Kein Subsystem — ein lokales Host-TUI.

**Gemessener Bedarf:** Edges zählen, Cron-Liveness, G1-Countdown, FSM-State werden heute manuell abgelesen. Das TUI spiegelt bestehende Dateien — es entscheidet nicht.

---

## §1 Zweck

Reduktion der manuellen Statusarbeit via **tail/streaming** (I3): nur neue Zeilen ab letzter Offset-Position, keine Voll-Datei ins RAM (OOM-Lehre 1,06-GB-WORM).

---

## §2 Quellen (read-only, nur Panel-relevant)

| Panel | Quelle | Pfad (Host-Default) |
|-------|--------|---------------------|
| P1 | Fenster-W-Edges | `{RAAS_DATA_ROOT}/audit/paper_edges.jsonl` · Env: `PAPER_EDGES_PATH` |
| P2 `:00` | News run_marker | `data/news_scores.jsonl` · `source_type=run_marker` |
| P2 `:05` | Gap-Detector run_marker | `data/gap_reports.jsonl` · `kind=run_marker` |
| P2 `:06` | News-Phase run_marker | `data/phase_signals/news_sentiment.jsonl` · `kind=run_marker` |
| P2 `:07` | Gap-Phase run_marker | `data/phase_signals/price_gap.jsonl` · `kind=run_marker` |
| P3 | G1 Gate + Liveness | `NEWS_SCHEDULER_EPOCH_TS`, Gate-Close aus [`NEWS_24H_SCHEDULER_GATE.md`](NEWS_24H_SCHEDULER_GATE.md); `marker_liveness` aus News-`run_marker` |
| P4 | FSM-State | `{RAAS_DATA_ROOT}/state/paper_position.json` · Env: `PAPER_POSITION_STATE_PATH` |

`RAAS_DATA_ROOT` default: `data/raas`. **Nicht** Panel-Quelle: `feed_gaps.jsonl`, WORM-Vollscan, Shadow-`shadow_eval.jsonl`.

LEDs (P2) aus **echten run_marker-Daten** + Alter — nicht aus Cron-Annahmen.

---

## §3 Panels — exakt vier

| # | Panel | Anzeige |
|---|-------|---------|
| **P1** | Fenster-W-Zähler | `n_eligible / 50` · Fortschrittsbalken · B2-Filter: `freeze_k`, `exit_reason=hold_expired`, `\|Δhold\| ≤ max_delta_s` ([`paper_edge_sample.py`](../prototypes/raas_paper_trading/paper_edge_sample.py)) |
| **P2** | Host-Cron-Matrix | LED grün/rot je `:00/:05/:06/:07` · grün iff letzter Marker `age ≤ max_age` · alle vier Slots: `NEWS_MARKER_MAX_AGE_H` (Default **2 h**, aus [`liveness.py`](../services/news_agent/liveness.py)) |
| **P3** | Liveness-Countdown | Restzeit bis **2026-09-01 09:00 UTC** · `n_markers_post_epoch` · `marker_liveness.status` (Anzeige, kein Gate-Urteil vor Close) · *Hard-Date nur G1-Fenster; nach Gate-Close Env oder Scope-Amendment* |
| **P4** | Position-Tracker | `IDLE` / `HOLDING` / … · bei offener Position: wall-clock `Δt` seit `entry_tick_ts` |

Ein fünftes Panel braucht einen **neuen gemessenen Anlass** und Scope-Amendment.

---

## §4 Invarianten

| ID | Invariante |
|----|------------|
| **I1** | Read-only auf Quellen; Schreiben nur auf Terminal (Render). |
| **I2** | Kein schreibender State-Zugriff, keine Order, kein Daemon/Helm/Fenster-W-Eingriff. |
| **I3** | Tail/streaming — keine ganze JSONL ins RAM. |
| **I4** | Charter auf jeder Ausgabe: `diagnostic_only`, `live_execution=false`, `order_send=false`, `not_investment_advice=true`. |
| **I5** | **Spiegel, kein Analyst** — nur Felder aus den Quellen. Keine Prognose, kein „should", keine Handelsempfehlung, keine Regime-Deutung. |

**I5 ist tragend.** Deutung = abgelehnter Geheimdienst-Strang.

---

## §5 Was es NICHT tut

- Keine Prognose / kein „Regime sieht X aus"
- Keine Handelsempfehlung / kein „Position sollte Y"
- Keine Order, kein State-Write, kein `kubectl`
- Keine Alerts nach außen (nur Terminal)
- Keine Kelly/`shadow_gate_decision`-Anzeige (Strang B.1 separat)
- Kein fünftes Panel ohne Amendment
- Kein Live-Lauf Shadow Evaluator; kein `SHADOW_EVAL_G1_PASS`-Bypass

---

## §6 Smoke (Fixtures only, kein Live-Gate nötig)

| # | Test | Erwartet |
|---|------|----------|
| **S1** | Fixture `paper_edges.jsonl` (mixed eligible) | P1 = `count_eligible` / 50 |
| **S2** | run_marker frisch + stale je Slot | P2 LED grün / rot |
| **S3** | Zeitpunkt vor Gate-Close | P3 Countdown + `n_markers` korrekt |
| **S4** | Fixture `paper_position.json` HOLDING | P4 State + `Δt` |
| **S5** | Render-Output | Keine Labels `should`, `recommend`, `bullish`, `bearish` |
| **S6** | Lauf gegen Fixture-Kopie | Quell-Dateien bit-identisch (I1) |
| **S7** | Fehlende/leere Quelle | Kein Crash, Panel zeigt „—" |

Gate: S1–S7 grün vor erstem Live-Pfad-Lauf.

---

## §7 Gate-Neutralität & Priorität

- Berührt **kein** Gate (G0–G4, News-24h, n≥50, Shadow G1-Guard).
- **Parallel** zu G1-Standby — **darf G1-Review (01.09 09:00 UTC) nicht verdrängen**.
- P0 bleibt: G1 PASS → Shadow Evaluator erster Live-Lauf.

---

## §8 Review-Checkliste vor Umsetzung

- [ ] Vier Panels, kein fünftes
- [ ] I1–I5 akzeptiert (I5 tragend)
- [ ] §2-Quellen/Pfade gegen Host-Deployment bestätigt
- [ ] P2 an run_marker, nicht Cron-Annahme
- [ ] §5 Anti-Scope akzeptiert
- [ ] S1–S7 als Smoke-Gate
- [ ] Kein Code vor FREIGABE

---

## Siehe auch

- [`docs/NEWS_AGENT.md`](NEWS_AGENT.md) — Cron `:00`–`:07`
- [`docs/SHADOW_EVALUATOR_PREREG.md`](SHADOW_EVALUATOR_PREREG.md) — Strang B.1 (separat)
