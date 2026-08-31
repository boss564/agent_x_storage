# Paper Position Sizing (Strang B) — Pre-Reg

**Status:** FROZEN (2026-08-31) — Design-Abgleich §0.2 **DECIDED**  
**Erstellt:** 2026-08-31  
**Strang:** Kelly-Boundary-Diagnostik (B0–B8) · **kein** Order-Send · **kein** Signal  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · `order_send=false` · `not_investment_advice=true`  
**Parent:** [`POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) · [`POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) · [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) · [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md)  
**Außerhalb:** Kein Code in **diesem** Dokument — aber **Messkorrekturen** (§1.1, §2.3, §4) sind vor dem ersten B2-Lauf zu implementieren; danach wären sie Tuning.

---

## 0. Zweck (eine Zeile)

Die **Messmethode** für Kelly-Boundary-Diagnostik (p, b, f*, Schranke) und die **defensiven Ausführungs-Invarianten** (Z3, Exit, Order-Typ) werden **vor dem ersten Auswertungslauf** eingefroren — analog `PAPER_HOLD_SECONDS=4966` vor Deploy. Ergebnisse (f* ≤ 0, LIMIT_EXCEEDED, …) sind **Daten**, keine Tuning-Hebel.

### 0.1 Abgrenzung — was dies NICHT ist

| Nicht | Warum |
|-------|--------|
| Implementierung / PR | Code existiert als Entwurf; Freigabe folgt dieser Pre-Reg |
| Trading-Signal / Allokation | Ausgabe = Belastungsgrenze (`max_notional_before_limit_breach_eur`), keine Empfehlung |
| Paper-WORM-Erweiterung | [`POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) §4.1 — Kelly-Felder **verboten** in `paper_trades.worm.jsonl` |
| Liveness-`run_marker` | Inline-Gate; Lebendigkeit = Aufrufer (Regime-Zyklus), siehe [`AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) |
| Nachjustierung nach f* | HARKing — siehe §6 |

### 0.2 Design-Entscheidungen (DECIDED 2026-08-31)

| # | Frage | Entscheidung | Begründung |
|---|-------|--------------|------------|
| D1 | Phase-Schwellen Z3-P1 (`0.70` / `−0.30`) | **Unverändert** | Konservativismus ist Z3-Invariante: `impact_score ≥ 0.70` isoliert strukturelle Schocks; `sentiment < −0.30` vermeidet Falsch-Auslösungen bei leicht negativer Wortwahl |
| D2 | Post-Only + Maker vs. A1-Epoche | **Ein Timestamp** `PAPER_SIZING_A1_EPOCH_TS` | Taker (7,5 bps) → Maker ändert `pnl_netto` fundamental; zwei Marken würden Replay unnötig verkomplizieren. Ab Deploy synchron: Ledger Option A, `post_only_limit`, Maker-Gebührenbasis |
| D3 | K1 (0,25) vs. γ-Map (`HIGH_VOL` 0,40) | **Map behalten, K1 durchsetzen** | Audit/Telemetrie zeigt Regime-Vorschlag (`γ × kelly_raw`); K1 ist Hard-Guardrail auf `f*_point`. Map nicht vereinfachen |

---

## 1. Estimand & Epochengrenze

p und b beschreiben **nicht** das Entry-Signal. Sie beschreiben die Verteilung der **k-Schritt-Renditen**, die die **Exit-Regel Option B** erzeugt.

| Größe | Definition (eingefroren) |
|-------|---------------------------|
| **Round-Trip** | BUY → Hold k → SELL mit netto `realized_pnl_eur` (§1.1) |
| **k** | `PAPER_HOLD_SECONDS` (Freeze §4) |
| **Rendite pro Trip** | `profit_fraction = realized_pnl_eur / entry_notional_eur` (Notional **ohne** Gebühr — Nenner unverändert; Zähler netto) |
| **p** | Anteil Trips mit `profit_fraction > 0` im Fenster |
| **b** | `mean(profit_fraction \| win) / abs(mean(profit_fraction \| loss))` — nur wenn §2.3 Mindestbesatz erfüllt |
| **f\*** | Fraktionaler Kelly-Anteil (§2) — **Punktschätzung + Bootstrap-Intervall**, nicht eine Zahl allein |

Exit-Regel ist **Stichprobendesign**. Änderung von k, Gap-Toleranz oder Eligibility **vor** N≥50 ändert den Estimand — verboten ohne neue Spec-Version.

### 1.1 Amendment A1 — netto Trip-PnL (Messkorrektur, kein HARKing)

**Befund (Ist `ledger.py`):** Cash ist korrekt (`sim_buy` belastet `cost = notional + fee`), aber `avg_entry` wird aus **notional** gebildet, `sim_sell` zieht nur die **Exit-Gebühr** ab. Die Einstiegsgebühr (~7,5 bps taker) fehlt in der Trip-PnL.

```text
sim_buy:  cost = notional + fee_eur
          avg_entry ← (… + notional) / new_qty     # fee fehlt im Einstand
sim_sell: pnl = (p − avg_entry) × q − fee_exit   # nur Exit-Gebühr
```

Bei σ_k ≈ 75 bps liegen grob **~4 %** der Trips im Band (−7,5 bps, 0] — zählen als Gewinn, obwohl netto Verlust. **p ist systematisch nach oben verzerrt**; `kelly_raw` reagiert auf p am empfindlichsten. Mehr Round-Trips heilen das nicht (systematische Verzerrung, keine Streuung).

| Option | Fix | Bewertung |
|--------|-----|-----------|
| **A (festgelegt)** | `avg_entry` aus **`cost`** (notional + entry_fee) pro BUY-Zeile | Einstand = volle Anschaffungskosten; `realized_pnl_eur` netto ohne B2-Sonderformel |
| B | B2: `profit_fraction = (realized_pnl_eur − entry_fee_eur) / entry_notional_eur` | Ledger unverändert; zwei PnL-Definitionen (Cash vs. Kelly) |

**Freeze:** Option **A** vor erstem eligible Trip / erstem B2-Lauf. Klassifikation: **Messkorrektur** (wie Trade-Tick → 1s-Bar), nicht Performance-Tuning.

**Nach A1 (Live-Ledger):** `profit_fraction = realized_pnl_eur / entry_notional_eur` mit netto-Zähler.

#### Epochengrenze — ein Estimand im 50er-Fenster

A1 erzeugt eine **PnL-Basis-Grenze**. Bereits vorhandene eligible Trips (~12 Stand ENTWURF) tragen `realized_pnl_eur` nach der **alten** Rechnung (Einstiegsgebühr fehlt); alles nach A1-Deploy rechnet netto. Beide im selben Fenster = zwei Estimands — analog k=433 vs k=4966.

| Weg | Folge |
|-----|--------|
| Neu zählen | ~12 Trips verwerfen, ~10 h Sammelzeit verloren |
| **Rückrechnen (festgelegt)** | Trips behalten; Gate rückt nicht |

**Festgelegt vor erstem B2-Auswertungslauf:** Trips **vor** A1-Deploy werden aus dem WORM **netto nachgerechnet** — `pnl_netto = realized_pnl_eur − entry_fee_eur` (BUY-Fill `"fee_eur"`, Paarung über `signal_id` zum SELL). Trips **danach** entstehen bereits netto (Option A im Ledger). **Beide sind derselbe Estimand.** Die Korrektur ist **exakt** (Subtraktion vorhandener Werte), keine Schätzung — anders als verworfener Positions-Exit, wo ein Preis hätte erfunden werden müssen.

Wer erst beide Varianten rechnet und die bessere f* wählt, verletzt H9–H11. Keine nachträgliche Wahl.

**Epochenmarke (D2 — gebündelt):**

```text
PAPER_SIZING_A1_EPOCH_TS = <ISO 8601 UTC beim Deploy>
```

Ab diesem Zeitpunkt **gleichzeitig** gültig (keine zweite Marke):

| Komponente | Änderung |
|------------|----------|
| Ledger | Option A — `avg_entry` aus `cost` |
| Execution | `PAPER_ORDER_EXECUTION=post_only_limit` (§3.3) |
| Gebühren | Maker-Schedule statt Taker 7,5 bps |

Analog `NEWS_SCHEDULER_EPOCH_TS` / `OPTION_B_EXIT_EPOCH_TS`. B2 wendet WORM-Rückrechnung nur auf SELL-Zeilen mit `ts < PAPER_SIZING_A1_EPOCH_TS` (netto Fee-Subtraktion §1.1); Trips danach entstehen unter dem gebündelten Estimand.

---

## 2. Fraktionales Kelly-Sizing (f*)

### 2.1 Kelly-Formel (eingefroren)

Klassischer Kelly auf Einheits-Rendite b (Gewinn/Verlust-Verhältnis):

```text
kelly_raw = (p · b − (1 − p)) / b
f*_raw    = max(0, γ · kelly_raw)
f*_point  = min(f*_raw, kelly_fraction_cap)     # globale Obergrenze §2.2
```

| Parameter | Wert | Rolle |
|-----------|------|-------|
| `window_size` N | **50** | Rollierendes Fenster der letzten N eligible Renditen |
| `min_trades` N_min | **50** (= N) | `< 50` → `INSUFFICIENT_HISTORY`, **kein** Kelly, **kein** Fallback-p |
| `risk_limit_fraction` | **0.02** (2 %) | `max_notional_before_limit_breach_eur = capital_eur × 0.02` |
| `gamma_default` | **0.25** | Fallback wenn Regime unbekannt |
| Kapitalquelle | `PaperLedger` mark-to-market | Kein fixes Startkapital |

### 2.2 Risiko-Invariante — Quarter-Kelly-Obergrenze

**Freeze K1:** Unabhängig vom Regime gilt:

```text
kelly_fraction_cap = 0.25
f*_point = min(max(0, γ · kelly_raw), 0.25)
```

Damit ist die Positionsgröße **nie mehr als 25 % des vollen Kelly** (`kelly_raw`), auch wenn γ in der Regime-Map höher steht (z. B. `HIGH_VOL_TREND` γ=0.40). Die Map bleibt unverändert (D3): sie steuert die **Skalierung unterhalb** der Kappe und dokumentiert Regime-Dynamik in der Telemetrie.

**Audit (D3):** Zusätzlich zu `kelly_fraction_computed` (= `f*_point`) Pflichtfeld `kelly_fraction_gamma_uncapped = max(0, γ · kelly_raw)` — zeigt, was der Klassifikator vorgeschlagen hätte, bevor K1 greift.

**B4 (Diagnose):** `computed_hypothetical_notional_eur = f*_point × capital_eur`

### 2.3 Mindestbesatz Gewinne **und** Verluste (b-Wächter)

`b ≤ 0` fängt fehlende Gewinne. **Fehlende Verluste** nicht:

- leere Verlustmenge → `mean(loss)` undefiniert;
- **ein** kleiner Verlust → `b` explodiert → `kelly_raw → 1`, f* → Kappe aus **einer** Beobachtung.

**Freeze (konjunktiv zu §2.1):**

```text
min_wins  = min_losses = 5
n_wins  = |{ profit_fraction > 0 }|  ≥  5
n_loss  = |{ profit_fraction < 0 }|  ≥  5
```

Sonst `INSUFFICIENT_HISTORY` — auch wenn `stats_count = 50` und `b > 0`.

### 2.4 Unsicherheit bei N=50 — Bootstrap (Pflicht)

Bei n=50 ist f* eine **Punktschätzung** ohne Fehlerbalken:

```text
SE(p) ≈ √(p(1−p)/50) ≈ 0.071   bei p ≈ 0.5
Vorzeichenwechsel kelly_raw bei p = 1/(1+b)  →  p = 0.5 für b = 1
```

**Freeze — Bootstrap (analog Prefilter-σ-Robustheit):**

| Parameter | Wert |
|-----------|------|
| `bootstrap_B` | **1000** |
| Resampling | Mit Replacement über die **50** eligible `profit_fraction`-Werte |
| Pro Draw | p, b, `kelly_raw`, f* neu rechnen (gleiche Formeln §2.1, Kappe §2.2) |
| Ausgabe | `f*_point` (Punktschätzung) **+** `f*_p05`, `f*_p50`, `f*_p95` |

Audit-Pflichtfelder (zusätzlich zu Parent §4.2): `kelly_fraction_computed` (= `f*_point`), `kelly_fraction_gamma_uncapped`, `kelly_fraction_p05`, `kelly_fraction_p95`, `bootstrap_B`, `kelly_fraction_cap`, `gamma`, `gamma_source`.

### 2.5 Sizing-Gate (B6) — mit Intervall

| Schritt | Formel |
|---------|--------|
| Schranke | `max_notional_before_limit_breach_eur = capital_eur × 0.02` |
| Einheiten | `max_units_before_limit_breach = max_notional / price_eur` |

| Entscheidung | Bedingung |
|--------------|-----------|
| `INSUFFICIENT_HISTORY` | `stats_count < 50` · `n_wins < 5` · `n_losses < 5` · `b ≤ 0` · `b` undefiniert |
| `LIMIT_OK` | **`f*_p05 > 0`** **und** `f*_point × capital_eur ≤ max_notional_before_limit_breach_eur` |
| `LIMIT_EXCEEDED` | `f*_p05 > 0` **und** hypothetische Notional (Punktschätzung) **>** Schranke |
| *(sonst)* | `f*_p05 ≤ 0` → kein `LIMIT_OK`/`LIMIT_EXCEEDED` — Kelly-Vorzeichen unsicher; Status diagnostisch (`kelly_sign_uncertain: true`) |

`LIMIT_OK` nur, wenn die **untere Bootstrap-Grenze** über null liegt — sonst beruht die Schranke auf Rauschen.

Kein Exchange-Send in allen Fällen (`order_send=false`).

### 2.6 A7-Trigger (wann B0 rechnen darf)

| # | Bedingung |
|---|-----------|
| T0 | `POSITION_SIZING_ENABLED=true` (nach Gate N, §7) |
| T1 | Regime-Zyklus abgeschlossen (`classified_regime` vorhanden) |
| T2 | **`regime_flag >= 1`** (kein Sizing in STABLE-only-Phasen) |
| T3 | B2 `stats_count >= 50` (sonst hard block) |
| T4 | Z3 Phase-Gates **nicht** tripped (§3.1) |
| T5 | Daily-Loss-Gate **nicht** tripped (§3.2) |

---

## 3. Z3 Risk Gates & Defensive Execution

Strang B bleibt diagnostisch (`order_send=false`). §3 definiert **formale Block-Invarianten**, die **vor** jedem B0-Lauf und **vor** jedem Paper-Entry geprüft werden — unabhängig davon, ob `live_execution` später freigegeben wird. Verletzung = `BLOCKED` im Audit, kein Kelly-Output, kein neuer Entry.

### 3.1 PhaseSource-Kopplung (News-Sentiment & Price-Gap)

Quellen: Host-Adapter (Fenster W), **nicht** Cluster-Cron:

| Quelle | JSONL | Cron | Marker |
|--------|-------|------|--------|
| News-Sentiment | `data/phase_signals/news_sentiment.jsonl` | `:06` `# AGENTX_NEWS_PHASE` | `kind=run_marker` |
| Price-Gap | `data/phase_signals/price_gap.jsonl` | `:07` `# AGENTX_GAP_PHASE` | `kind=run_marker` |

Handoff-Regel: [`astrocore/sources/handoff.py`](../astrocore/sources/handoff.py) — PhaseSources schreiben **nur** unter `phase_signals/`; Rückschreiben auf Detector-JSONL = `order_send_forbidden`.

**Lookback (eingefroren):** 24 h für News-Sentiment, **1 h** für Price-Gap (Preis-Anomalien sind kurzlebig).

| Gate-ID | Quelle | Trip-Bedingung | B0-Aktion | Audit-Feld |
|---------|--------|----------------|-----------|------------|
| **Z3-P1** | `news_sentiment` | Zeile mit `impact_score ≥ 0.70` **und** `sentiment < −0.30` im 24h-Lookback | Skip B0; kein neuer Paper-Entry | `phase_gate: NEWS_DEFENSIVE` |
| **Z3-P2** | `price_gap` | Zeile mit `signal_type == COVERAGE_GAP` im 1h-Lookback | Skip B0; kein neuer Paper-Entry | `phase_gate: GAP_DEFENSIVE` |
| **Z3-P0** | beide | `run_marker` fehlt **und** Cron soll aktiv sein | Skip B0 (Adapter tot); **kein** Auto-Entry | `phase_gate: PHASE_SOURCE_STALE` |

**Nicht tripped:** leerer Lookback bei vorhandenem `run_marker` (`status=empty`) — kein News-/Gap-Fenster, kein Defensiv-Modus.

**Begründung Schwellen (D1):** Für ein Z3-Risk-Gate ist Konservativismus eine Invariante. `impact_score ≥ 0.70` trennt makro/strukturelle Schocks vom Hintergrundrauschen; `sentiment < −0.30` verhindert Auslösung bei leicht negativer Wortwahl.

PhaseSources sind **defensive Kontext-Gates**, keine Sizing-Trigger. Sie dürfen f* **nicht** erhöhen — nur blockieren.

### 3.2 Daily Loss Limit

| Parameter | Wert |
|-----------|------|
| `daily_loss_limit_fraction` | **−0.02** (−2 % Tages-PnL) |
| Basis | `capital_eur` zu UTC-Mitternacht (Mark-to-Market Snapshot) |
| PnL | `daily_pnl_eur = realized_today + unrealized_now − realized_at_midnight` |

| Gate-ID | Trip-Bedingung | Aktion |
|---------|----------------|--------|
| **Z3-D1** | `daily_pnl_eur / capital_midnight_eur ≤ −0.02` | Hard block: kein B0-Kelly, kein neuer Paper-Entry bis nächster UTC-Tag |

Reset: automatisch um **00:00 UTC** (neuer `capital_midnight_eur`). Kein manuelles Override ohne `HUMAN_FORCE_EXIT`-Klasse und Audit-Zeile.

Audit-Pflicht: `daily_pnl_eur`, `daily_pnl_fraction`, `daily_loss_gate_tripped: true|false`.

### 3.3 Order-Typ — Post-Only Limit (Standard)

| Parameter | Wert |
|-----------|------|
| `PAPER_ORDER_EXECUTION` | **`post_only_limit`** (eingefroren) |
| Verboten | Market-Orders, IOC/FOK, Taker-Fills ohne Limit-Preis |

**Paper-Simulation:** Fills nur, wenn Limit-Preis innerhalb des synthetischen Spreads liegt; sonst **kein Fill** (Order bleibt offen bis nächster Tick — kein Taker-Fallback). Gebührenmodell wechselt auf **maker**-Schedule (nicht taker 7,5 bps). **Deploy gebündelt** mit Ledger A1 unter `PAPER_SIZING_A1_EPOCH_TS` (D2) — keine separate Epochenmarke.

| Gate-ID | Verhalten |
|---------|-----------|
| **Z3-O1** | Jeder `SIM_FILL` trägt `execution_mode: post_only_limit`; Fill ohne dieses Flag = Audit-Verstoß |

Strang B (Kelly) bleibt von Order-Typ **entkoppelt** (misst k-Schritt-Renditen), aber p/b **müssen** netto nach dem eingefrorenen Gebührenmodell sein — A1 + maker/post-only sind konsistent zu halten.

### 3.4 Z3-Prüfreihenfolge (B0 Pre-Flight)

```text
Z3-P0 (Marker) → Z3-P1/P2 (Phase) → Z3-D1 (Daily Loss) → T0–T5 (§2.6) → B1…B8
```

Erster Trip = `BLOCKED` mit `z3_gate_reason`; kein partieller Kelly.

---

## 4. Haltedauer & Exit-Invarianten

Strang B zählt **nur** Trips, die Option B (feste Haltedauer) **regelkonform** abschließen. Parent-Freeze: [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md).

### 4.1 Exit-Parameter (referenziert, unveränderbar bis neues Freeze)

| Parameter | Wert | Quelle |
|-----------|------|--------|
| `PAPER_EXIT_MODE` | `time_hold` (Option B) | Parent §4 |
| `PAPER_HOLD_SECONDS` (k) | **`4966`** | Parent §7 Freeze 2026-08-29 (1s-Bar Amendment) |
| `price_basis` | `last_price_bar` (bar=1s) | Parent §7 |
| `PAPER_EXIT_GAP_DT_S` | **30** | Implementation Pre-Reg |
| `PAPER_EXIT_MAX_WAIT_S` | **24830** | Alarm only — kein Auto-Force-Exit |
| `PAPER_MAX_OPEN_POSITIONS` | **1** | Parent §4.4 |

**Superseded:** k=433 (Trade-Tick-Basis) — **nicht** für B2-Eligibility.

**Epochenmarke Option B:** `OPTION_B_EXIT_EPOCH_TS = 2026-08-29T08:30:22.486000+00:00` — Replay ab erstem eligible Entry, nicht SELL-ts.

### 4.2 B2-Eligibility (drei Bedingungen, konjunktiv)

Ein abgeschlossener Trip zählt für p/b/f* **nur**, wenn:

1. `hold_seconds_target == PAPER_HOLD_SECONDS` (**4966**)
2. `exit_reason == hold_expired` (kein `force_exit`, kein Break-Exit)
3. `|hold_seconds_actual − hold_seconds_target| ≤ PAPER_EXIT_GAP_DT_S` (**30** s)

Gemischte k oder gap-gestreckte Holds = **anderer Estimand** → ausgeschlossen.

### 4.3 `hold_expired` vs. `force_exit`

| `exit_reason` | Bedeutung | B2-eligible? | Auslöser |
|---------------|-----------|--------------|----------|
| **`hold_expired`** | Timer k erreicht, Fill im Gap-Fenster | **Ja** | Option-B-Daemon |
| **`force_exit`** | Menschlicher Not-Aus | **Nein** | Nur `HUMAN_FORCE_EXIT` (Env/API) — **nie** Regime/A7/Daemon |

Weitere Gründe (`graceful_shutdown`, `POSITION_ABANDONED`) sind **kein** `exit_reason` für Strang B — siehe Parent E6–E8. `POSITION_ABANDONED` zählt nicht gegen n_eligible.

### 4.4 Gap- und Restart-Invarianten (Exit-Pfad)

| ID | Invariante |
|----|------------|
| I3 | Exit-Tick mit Δt > 30 s → **kein** Exit; warten |
| I3b | Wait > 24830 s → `EXIT_WAIT_TIMEOUT`-Alarm; **kein** Auto-Force-Close |
| E3/E4 | Graceful Shutdown → State persistieren; Timer wall-clock weiter |
| E7 | Pod-Restart → Rekonstruktion aus `paper_position.json`; Hold **ohne Reset** |

---

## 5. Freeze-Tabelle (Referenz)

Alle Werte **vor** erstem Strang-B-Auswertungslauf gültig. Änderung nur via neue Pre-Reg-Version + dokumentierter Messkorrektur (kein Performance-Tuning).

### 5.1 Gate N (Freigabe Strang B)

| Parameter | Wert |
|-----------|------|
| **Gate Strang B** | **n_eligible_at_freeze_k ≥ 50** |
| Zähler | Nur §4.2-eligible Trips — **nicht** `grep SELL`, nicht WORM-Zeilen |

Zeitliche Erwartung (Planung): k=4966 s (~82,8 min), max. 1 offene Position → **≈ 69 h** bis Gate — zzgl. Entry-Lücken. Vorlauf, kein Pass/Fail der Methodik.

### 5.2 γ-Regime-Map (eingefroren v0)

| `classified_regime` | `regime_flag` | γ (Map) | Effektiv f* (mit K1) |
|---------------------|---------------|---------|----------------------|
| `STABLE` | 0 | 0.25 | min(0.25·kelly_raw, 0.25) |
| `STABLE_SIDEWAYS` | 0 | 0.10 | min(0.10·kelly_raw, 0.25) |
| `LOW_LEVEL_DRIFT` | 1 | 0.20 | min(0.20·kelly_raw, 0.25) |
| `DRIFT_IID_UNRELIABLE` | 1 | **0.00** | 0 (Safe Mode) |
| `HIGH_VOL_TREND` | 2 | 0.40 | **min(0.40·kelly_raw, 0.25)** → K1 bindet |
| `HIGH_VOL_TREND_BEARISH` | 2 | 0.35 | min(0.35·kelly_raw, 0.25) |
| *unbekannt / fehlend* | — | 0.25 | min(0.25·kelly_raw, 0.25) |

γ skaliert nur `computed_hypothetical_notional_eur` (Diagnose). Export bleibt **Schranke**, nie Empfehlung.

---

## 6. Anti-HARKing / Freeze-Gates

| ID | Gate | Regel |
|----|------|-------|
| H1 | **k-Freeze** | `PAPER_HOLD_SECONDS=4966` unveränderbar bis neuer WORM-Snapshot + neues Parent-Freeze |
| H2 | **N-Freeze** | `min_trades = window_size = 50` — kein N=30 mit `confidence: LOW` während Gate-Phase |
| H3 | **Kein Fallback-p** | Bei `< 50` eligible: **kein** p=0.5, b=1.0, kein Kelly |
| H4 | **Eligibility-Freeze** | Zähler nur B2-eligible (§4.2) — nicht SELL-Gesamtzahl |
| H5 | **γ-Freeze** | Map §5.2 — nicht nach erstem positivem f* drehen |
| H6 | **Schwellen-Freeze** | `risk_limit_fraction=0.02`, `daily_loss_limit_fraction=−0.02` — nicht an Raten anpassen |
| H7 | **Ergebnis ist Ergebnis** | f* ≤ 0 nach 50 Trips = Befund, kein k-Tuning |
| H8 | **Charter** | Keine `advisory_position_size` / Empfehlungsfelder im Audit |
| H9 | **Netto-PnL (A1)** | Ledger: `avg_entry` aus `cost`; WORM-Vorläufe: Rückrechnung §1.1 — **vor** erstem B2-Lauf |
| H10 | **Bootstrap-Freeze** | B=1000, Perzentile p05/p50/p95 — nicht nach erstem `LIMIT_OK` drehen |
| H11 | **b-Mindestbesatz** | min_wins=min_losses=5 — nicht nachträglich auf 3 senken |
| H12 | **K1-Cap** | `kelly_fraction_cap=0.25` — nicht nach positivem f* anheben |
| H13 | **Z3-Freeze** | Phase-Schwellen §3.1, Daily-Loss §3.2, Post-Only §3.3 — nicht nach erstem Block tunen |
| H14 | **Phase-Gate** | PhaseSources blockieren nur — dürfen f* nicht erhöhen |

**Erlaubte Messkorrekturen (kein HARKing):** Preisbasis Trade-Tick → 1s-Bar (Parent §7) · **A1 netto Trip-PnL** (§1.1) · **maker/post-only Gebührenbasis** (§3.3) — alles **vor** erstem B2-Lauf.

---

## 7. Gate n ≥ 50 (Freigabe Strang B)

### 7.1 Primär-Gate

```text
n_eligible_at_freeze_k ≥ 50
```

wobei jeder Zählerstand die drei Eligibility-Bedingungen (§4.2) erfüllt.

### 7.2 Was das Gate **nicht** ist

| Ungültig | Gültig |
|----------|--------|
| ≥ 50 WORM-Zeilen | ≥ 50 **eligible** Round-Trips |
| ≥ 50 BUY-Ticks | ≥ 50 SELL mit `hold_expired` @ k=4966 |
| ≥ 50 SIGNAL-Events | ≥ 50 unabhängige k-Schritt-Renditen |

### 7.3 Nach Gate-Pass

Erst dann:

- `POSITION_SIZING_ENABLED=true` (Runbook / Helm — **nicht** allein per Env ohne Gate-Nachweis)
- B0–B8-Läufe schreiben **`/data/audit/position_sizing_audit.jsonl`**
- Auswertung f*, LIMIT_OK/LIMIT_EXCEEDED unter **dieser** Pre-Reg — keine Parameteränderung ohne Amendment

---

## 8. Claims (falsifizierbar, nach Daten)

| ID | Claim |
|----|--------|
| C1 | Bei n≥50 eligible + §2.3 rendert B2 `p`, `b` ohne Fallback |
| C2 | f*_p05 ≤ 0 → kein `LIMIT_OK` (Vorzeichen unsicher) |
| C3 | `LIMIT_EXCEEDED` nur wenn f*_p05 > 0 **und** f*_point × capital > 2 % |
| C4 | Kein Kelly-Feld in `paper_trades.worm.jsonl` |
| C5 | Nach A1: Trip mit Brutto-Verlust (−7,5 bps netto) zählt nicht als Gewinn |
| C6 | f*_point ≤ 0.25 immer (K1) |
| C7 | Z3-D1 tripped → kein B0-Output in dem Zyklus |
| C8 | Jeder eligible Trip hat `exit_reason=hold_expired` |

---

## 9. Freigabe-Checkliste (vor VALIDIERT)

- [ ] **A1** netto Trip-PnL: Ledger-Deploy + `PAPER_SIZING_A1_EPOCH_TS`; WORM-Rückrechnung §1.1
- [ ] **§2.3** min_wins=min_losses=5 in B2
- [ ] **§2.4** Bootstrap B=1000 + f*_p05/p95 im Audit-Schema
- [ ] **§2.2** K1 `kelly_fraction_cap=0.25` in B3
- [ ] **§3** Z3 Pre-Flight (Phase, Daily Loss, Post-Only) in B0
- [ ] **§3.3** maker/post-only Gebührenmodell konsistent mit A1
- [ ] Parent-Freeze k=4966 + 1s-Bar unverändert
- [ ] Gate-Zähler `n_eligible_at_freeze_k` definiert (nicht SELL-grep)
- [ ] γ-Map §5.2 eingefroren
- [ ] H1–H14 im Runbook zitiert
- [ ] News-24h-Gate + Paper-Exit-Gate abgeschlossen (Vorbedingung Beobachtung)
- [ ] **Kein** Strang-B-Enable vor n≥50

**Nach VALIDIERT:** Ergebnisse dokumentieren; Parameteränderung nur via **PAPER_SIZING_PREREG v2** + neues Freeze.

---

## Siehe auch

- [`docs/AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) — Inline-Gate vs. zeitgesteuert · PhaseSource-Instanzen 5–6
- [`docs/PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) — I6 Anti-HARKing k · E6 Force-Exit
- [`docs/NEWS_FEED_STRUCTURE_PREREG.md`](NEWS_FEED_STRUCTURE_PREREG.md) — Muster: Methodik vor Messung
- [`docs/NEWS_AGENT.md`](NEWS_AGENT.md) — PhaseSource-Cron :06/:07
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — PVC-sichere Rollbacks (operational 2026-08-31)
