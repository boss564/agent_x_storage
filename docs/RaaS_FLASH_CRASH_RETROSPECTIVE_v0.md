# RaaS — Flash-Crash Retrospective Screen v0 (Option 5)

**Status:** MAP v0 (2026-08-27) · additiv · **wissenschaftlicher Screen**  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · kein Order-Send  
**Baseline:** Tag `v1.0-raas-baseline`  
**Nicht:** Konfigurations-Tuning, Live-Trading, Trainingslabels aus Klines, Track-Record

---

## 1. Offene Hypothese (vorab, nicht vorweggenommen)

> Wie hätte die **Risiko-Schicht** des Fail-Closed-Gates (`evaluate_gate`: P3/P8/Z3-Cascade/M7/BHO)
> bei vergangenen Volatilitäts-Spikes reagiert — gemessen als Envelope-Trefferquote
> (Precision/Recall) gegen **vorab eingefrorene** Observed-Break-Definitionen?

Antwort ist **nicht** vor dem Lauf aufschreibbar. Ergebnisse = Screen, kein Pitch.

---

## 2. Was getestet wird / was nicht

| Ja | Nein |
|----|------|
| Retrospektives Replay: Klines → Features → `GateInput` → `evaluate_gate` | Ändern von Gate-Schwellen (`EXEC_RISK_BLOCK`, `CASCADE_BLOCK`) ohne Amendment |
| Primärmetrik: `score_envelope_hits` (P/R, FP/FN) | Profit Factor als Erfolgskriterium |
| D-Suite + WORM-Zeile mit `live_execution=false` | `ORDER_SENT` / Broker-Keys |
| Risiko-Schicht isolieren (`human_gate_open=True` **nur** Analyse) | Freigabe für Live oder Human-Latch umgehen im Betrieb |
| Public Binance Spot 1m (read-only Cache) | Klines als Trainingslabels für ein Modell |

**Hinweis „Z3“:** Im Gate ist `check_z3_cascade` ein **Score-Gate** auf `cascade_risk`
(≥ 0.75), nicht der HTTP-BHO-Prover (`services/z3_solver`). Der Screen nennt das
explizit `Z3_CASCADE` / Score-Pfad.

---

## 3. Vorab eingefrorene Definitionen (v0 — Amendment nur mit neuem Hash)

### 3.1 Observed break (Markt)

Pro Bar `i` (1m), `condition_id = "{symbol}:{open_time}"`:

```text
observed_break = (bar_drop_pct >= 2.0) OR (roll_dd_60_pct >= 5.0)
```

| Größe | Definition |
|-------|------------|
| `bar_drop_pct` | `100 * max(0, (close[i-1] - close[i]) / close[i-1])` |
| `roll_dd_60_pct` | Drawdown vom High der letzten 60 Closes bis `close[i]` in % |

### 3.2 Predicted break (Gate-Risiko-Schicht)

Features aus derselben Bar (kausal: nur Preise bis inkl. `i`, kein Lookahead auf `i+1`):

```text
exec_risk    = min(1.0, bar_drop_pct / 3.0)      # 3% Drop → 1.0
cascade_risk = min(1.0, roll_dd_60_pct / 8.0)    # 8% DD → 1.0
latency_spike = None   # M7 in v0 nicht aus Klines gemappt
bho_delta = 0.0
human_gate_open = True  # NUR Retrospective: isoliert Risiko-Schicht
```

```text
predicted_break = (evaluate_gate(...).decision == "BLOCKED")
                  AND ("HUMAN_GATE_CLOSED" not in reasons)
```

Mit `human_gate_open=True` ist `HUMAN_GATE_CLOSED` ohnehin aus; BLOCKED = P3/P8/Z3/M7/BHO/Signal.

Gate-Schwellen unverändert: `EXEC_RISK_BLOCK=0.80`, `CASCADE_BLOCK=0.75`
→ Exec-Trip ab ~2.4% Bar-Drop; Cascade-Trip ab ~6.0% Roll-DD.

### 3.3 Metriken

| Metrik | Rolle |
|--------|-------|
| Precision / Recall / TP / FP / FN | **primär** (`envelope_break_hit_rate`) |
| `n_bars`, `n_observed_breaks`, `n_predicted_breaks` | deskriptiv |
| Anteil BLOCKED-Reasons (P3/P8/Z3/…) | diagnostisch |
| Profit / PnL | **verboten** in diesem Screen |

---

## 4. Daten

| Parameter | v0-Soll |
|-----------|---------|
| Symbol | `ETHUSDC` (Fallback `ETHUSDT` wie Public-Ingest) |
| Interval | `1m` |
| Fenster | Default **180 Tage**; Smoke darf Cache/`--days 14` |
| Quelle | `scripts/ingest_public_distributions.fetch_binance_klines` → `exports/open_data/_cache/` |
| Lücken | fehlende Tage = dokumentiert im Fetch-Log; kein Imputieren von Breaks |

Ist-Stand vor erstem Voll-Lauf: Public-Ingest-Cache oft ~14 Tage — Vollfenster braucht
Netz-Fetch. Smoke mit vorhandenem Cache ist **kein** 6–12-Monats-Claim.

---

## 5. Artefakte

| Pfad | Inhalt |
|------|--------|
| `scripts/raas_flash_crash_retrospective.py` | Screen-Runner |
| `logs/worm/flash_crash_retrospective.jsonl` | WORM-Zeile(n) |
| `exports/reports/flash_crash_retrospective_latest.json` | Maschinen-Ergebnis (gitignored) |
| `exports/reports/flash_crash_retrospective_latest.md` | Kurzreport (gitignored) |

Verdict-String: `RAAS_FLASH_CRASH_RETRO_PASS` nur wenn Lauf + Charter-Stamps ok —
**nicht** weil P/R „gut“ aussieht.

---

## 5.1 Screen-Ergebnisse (fixiert, kein Tuning)

`definition_hash` = `bbae3cb16d893e6380665843415c430aedf9946a084010e94b88dca7a0ccb01b`
(Symbol `ETHUSDC`, Interval `1m`, MAP §3 unverändert.)

| Fenster | Bars | Observed | Predicted | Precision | Recall | TP / FP / FN |
|---------|------|----------|-----------|-----------|--------|--------------|
| 14d | 20 160 | 2 | 1 | 1.0 | 0.50 | 1 / 0 / 1 |
| **180d** | **259 200** | **21** | **3** | **1.0** | **≈0.143** | **3 / 0 / 18** |

**Einordnung (wissenschaftlicher Befund, nicht Optimierungsziel):**

- Precision 1.0 / FP=0 → Risiko-Schicht blockt in diesem Screen nur echte Observed-Breaks (konservativ).
- Recall-Verfall 0.50 → ≈0.143 → **FN-Gürtel** zwischen Observed-Schwelle (Drop ≥2 % / DD ≥5 %) und Gate-Trip (~2.4 % Exec / ~6 % Cascade): moderate Breaks ohne P3/P8-Trip.
- 180d Trips (diagnostisch): `P3_EXEC_RISK=1`, `P8_CASCADE_RISK=2`.
- Kein Nachjustieren der Schwellen nach dem Blick auf die Zahlen (MAP §6).

Reproduzierbar: `make raas-flash-crash-retro` · `make raas-flash-crash-retro-180`.

---

## 6. Nicht jetzt

| Arbeit | Status |
|--------|--------|
| Schwellen nach erstem Blick „nachziehen“ | **verboten** ohne MAP-Amendment + neuer `definition_hash` |
| 30-Tage-Paper-Live-Fenster | orthogonal, weiter gesperrt bis Fee-Manifest |
| Core-`agent_x_backtest.py` Flash-Crash (CHI) | andere Semantik — optional später Cross-Check |
| Order-Send | verboten |

---

## 7. Verweise

| Artefakt | Rolle |
|----------|-------|
| `services/fail_closed_gate/gate_core.py` | `evaluate_gate` |
| `prototypes/raas_paper_trading/envelope_score.py` | P/R |
| `docs/PAPER_TRADING_SETUP_v0.md` | Paper-Primärmetrik |
| `docs/RaaS_BUS_EXPANSION_v0.md` §4.3 | Public data ≠ Trainingslabels |
| Tag `v1.0-raas-baseline` | Fixpunkt |
