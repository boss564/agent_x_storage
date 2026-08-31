# TUI Dashboard — Scope-Note (ENTWURF)
**Status:** ENTWURF — kein Code vor Review
**Erstellt:** 2026-08-31
**Strang:** Einzelstrang, passives Diagnose-Tool. Kein Subsystem.
**Charter:** `diagnostic_only` · `live_execution=false` · `order_send=false`
**Außerhalb:** Paper-Trading-Logik, Daemon, Helm, Order-Pfad bleiben unberührt.
---
## §0 Abgrenzung — was dies NICHT ist
- Kein Prognose- oder Analyse-Tool. Es deutet keine Daten.
- Kein Handels-Assistent. Es empfiehlt nichts.
- Kein Eingriff in Daemon, Helm, Fenster W, Order-Pfad.
- Kein neuer Daten-Producer. Es schreibt keine `.jsonl`.
- Kein Subsystem — ein einzelnes, lokales Host-TUI.
---
## §1 Zweck
Reduktion der manuellen Statusarbeit: Edges zählen, Liveness-Alter
berechnen, FSM-State ablesen — alles Schritte, die derzeit von Hand
gemacht werden. Das TUI spiegelt den Zustand der bestehenden
`.jsonl`-Dateien in Echtzeit (tail/streaming), ohne sie zu verändern.
---
## §2 Quellen (read-only)
| Quelle | Inhalt |
|--------|--------|
| `paper_edges.jsonl` | Fenster-W-Edges (eligible, profit_fraction) |
| `feed_gaps.jsonl` | Feed-Gap-Events + Heartbeats |
| `news_scores.jsonl` | News-Run-Marker, marker_liveness |
| FSM-State (WORM / State-File) | Position HOLDING/IDLE, entry_ts |
| Host-Cron run_marker | Cron-Liveness je Schedule |
Exakte Pfade werden bei Umsetzung gegen das Deployment bestätigt.
Alle Quellen werden **ge-tail-t** (nur neue Zeilen ab letzter Position),
nicht vollständig ins RAM geladen (OOM-Lehre aus der 1,06-GB-WORM).
---
## §3 Panels — exakt vier
| # | Panel | Quelle | Anzeige |
|---|-------|--------|---------|
| P1 | Fenster-W-Zähler | `paper_edges.jsonl` | `n/50` eligible, Fortschrittsbalken % |
| P2 | Host-Cron-Matrix | run_marker + Timestamps | LED grün/rot je `:00/:05/:06/:07` |
| P3 | Liveness-Countdown | News-Gate-Timestamp | Restzeit bis `01.09 09:00Z` |
| P4 | Position-Tracker | FSM-State | `HOLDING`/`IDLE` + verstrichene Haltedauer Δt |
Ein fünftes Panel braucht einen neuen gemessenen Anlass.
---
## §4 Invarianten
- **I1 read-only:** liest Quellen via tail/streaming, schreibt NICHTS
  außer auf den eigenen Terminal-Screen.
- **I2 kein Eingriff:** kein schreibender State-Zugriff, keine Order,
  keine Daemon/Helm/Fenster-W-Berührung.
- **I3 streaming:** keine ganze Datei ins RAM; nur tail ab letzter Position.
- **I4 Charter:** `diagnostic_only` · `live_execution=false` · `order_send=false`.
- **I5 Spiegel, kein Analyst:** zeigt nur, was in den Daten steht.
  Keine Prognose, kein „should", keine Handelsempfehlung, keine Deutung.
**I5 ist die tragende Invariante.** Sie verhindert, dass das TUI zu dem
wird, was als 9-Agenten-Geheimdienst abgelehnt wurde.
---
## §5 Was es NICHT tut (Anti-Scope-Creep)
- Keine Prognose / kein „Regime sieht X aus"
- Keine Handelsempfehlung / kein „Position sollte Y"
- Keine Order, kein State-Write
- Keine Alerts/Notifications nach außen (nur Terminal-Anzeige)
- Keine historischen Analysen / kein Backtesting-Display
- Keine neuen Datenquellen über §2 hinaus
- Keine Deutung der `shadow_gate_decision` oder Kelly-Werte
---
## §6 Smoke (auf Fixtures, keine Live-Daten)
| # | Test | Erwartet |
|---|------|----------|
| S1 | `paper_edges.jsonl`-Fixture mit N eligible | Zähler zeigt `N/50`, Balken korrekt |
| S2 | run_marker-Fixture (frisch + stale) | LED grün bzw. rot |
| S3 | Countdown-Fixture (Gate in Zukunft) | Restzeit korrekt |
| S4 | FSM-Fixture HOLDING mit entry_ts | `HOLDING` + Δt korrekt |
| S5 | Lauf gegen Fixture | Quell-Dateien bit-identisch unverändert |
| S6 | Fehlende/leere Quelle | Kein Crash, Panel zeigt „—" |
Gate: S1–S6 grün.
---
## §7 Gate-Neutralität
Das TUI berührt kein Gate (G0–G4, News-24h, n≥50). Es ist rein
beobachtend. Es darf während des Wartens auf G1 gebaut werden,
verdrängt aber nicht den G1-Review.
---
## §8 Review-Checkliste vor Umsetzung
- [ ] §2-Quellen bestätigt (keine weiteren)
- [ ] Vier Panels, kein fünftes
- [ ] I1–I5 akzeptiert, I5 als tragend
- [ ] §5 „Was es NICHT tut" akzeptiert
- [ ] S1–S6 als einziges Smoke-Gate
- [ ] Kein Code vor Status FREIGABE
