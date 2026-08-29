# Paper Exit & Round-Trip — Voraussetzung für B2 / Strang B

**Status:** **DECIDED — Option B (feste Haltedauer)** (2026-08-28)  
**Scope:** Live-Shadow Paper-Pfad (`LivePaperBridge` → `PaperTradingRunner`) · `live_execution=false`  
**Blockiert:** Strang B (`POSITION_SIZING_ENABLED=true`), B2 Kelly-Historie, Gate „≥50 abgeschlossene Round-Trips“

---

## 1. Befund (Live-Shadow Cluster)

| Beobachtung | Detail |
|-------------|--------|
| WORM `SIM_FILL` | v. a. `side: BUY` (z. B. 39×), **0× SELL** |
| `sim_sell` | implementiert in [`ledger.py`](../prototypes/raas_paper_trading/ledger.py) — **kein Aufrufer** im Live-Feed-Pfad mit Exit-Bedingung |
| `PaperTradingRunner.on_tick` | SELL nur bei `predicted_break` **und** `break_price_below` gesetzt |
| `LivePaperBridge.from_env` | setzt **`break_price_below=None`** → `_predict_break()` immer `false` |
| Ergebnis | Nur Tick 1 → `sim_buy`; Position wird nie geschlossen → `realized_pnl_eur` bleibt 0 |

**Nebeneffekt (Restarts):** Ledger ist **in-memory** pro Pod-Lebensdauer. Nach Container-Neustart: erneut Tick-1-BUY → weitere BUY-Zeilen in der WORM, ohne Round-Trip. Monitoring (`READY 1/1`, wachsende WORM) sieht „aktiv“ aus, obwohl keine abgeschlossenen Trades entstehen.

---

## 2. Warum das B2 / Kelly blockiert

B2 (`TradeStatisticAggregator`) zählt nur **abgeschlossene** Trades:

- `load_from_ledger`: nur `side == "SELL"` mit `realized_pnl_eur` / Notional → p, b
- `min_trades=50` → **50 Round-Trips**, nicht 50 BUY-Ticks oder 670k SIGNAL-Zeilen

Ohne Exit-Policy:

- Kelly-Historie bleibt leer → dauerhaft `INSUFFICIENT_HISTORY`
- Ledger-Wiring allein (WORM → `PaperLedger`) ändert nichts, solange keine SELL-Zeilen existieren

**Wichtig:** p und b sind keine Eigenschaften des Signals — sie beschreiben die **Verteilung der k-Schritt-Renditen**, die die **Exit-Regel** erzeugt. Die Exit-Regel ist das **Stichprobendesign** von B2.

---

## 3. Gate-Definition (revidiert)

| Alt (ungültig) | Neu (messbar) |
|----------------|---------------|
| „≥50 Fills“ / WORM-Zeilen | **Abgeschlossene Round-Trips ≥ N** (Default **N=50**) |
| Implizit: irgendwann SELL | Explizit: `SIM_FILL` mit `side=SELL` **und** `realized_pnl_eur` gesetzt (Replay in `PaperLedger`) |

**Prüfbefehl (Cluster):**

```bash
kubectl exec -n trading regime-swarm-0 -- sh -c \
  'grep "\"side\": \"SELL\"" /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl | wc -l'
```

Strang B erst freigeben, wenn dieser Zähler **≥ N** **und** Exit-Policy (Option B) im Code aktiv ist.

---

## 4. Exit-Entscheidung: **Option B — feste Haltedauer**

### 4.1 Warum nicht A / C / D

| Option | Was p und b dann messen | Verwerfung |
|--------|-------------------------|------------|
| **A — Preis-Break** | Stop-Höhe: Verluste gekappt, Gewinne laufen → **b systematisch überhöht**, p gedrückt | Exit korreliert mit Preispfad |
| **C — Regime-Signal** | A7 selbst — Rückkopplung Detektor ↔ Sizing; in ruhigen Phasen null Exits | Gate hängt an Regime; nicht pfadunabhängig |
| **D — Flat je Zyklus (30s)** | Kostenstruktur (s. u.) — erwartete Bewegung ≪ Round-Trip-Kosten | Gate füllt sich schnell, misst Mikrostruktur statt Strategie |
| **B — feste Dauer k** | **k-Schritt-Rendite nach Einstieg** — Exit **pfadunabhängig** | **Gewählt** — Exit unabhängig vom Preispfad |

Nur bei B ist der Ausstieg unabhängig vom Preispfad. Das ist die Bedingung dafür, dass die Verteilung das Signal abbildet und nicht die Ausstiegsregel.

### 4.2 Kostenschwelle (schließt D aus)

Aus dem Repo ([`ledger.py`](../prototypes/raas_paper_trading/ledger.py), [`slippage.py`](../prototypes/raas_paper_trading/slippage.py)):

| Komponente | Wert |
|------------|------|
| `taker_bps` (je Seite) | 7.5 bps |
| Round-Trip Fees | **15 bps** |
| `SYNTHETIC_SPREAD_BPS` (halb je Seite) | 5 bps → **10 bps** Round-Trip |
| **Round-Trip-Boden** | **≈ 20 bps (0.20 %)** |

Bei 30-Sekunden-Flats liegt die typische ETH-Bewegung unter diesem Boden → struktureller Verlust pro Runde, f* → 0. Option D würde das Gate zuverlässig füllen, ohne etwas Strategierelevantes zu messen (inverse HARKing: Schwelle wird grün, weil sie nichts Prüft).

### 4.3 Kalibrierung von k (Pre-Reg, vor ersten Round-Trips)

**Reihenfolge verbindlich:**

1. σ aus vorhandener WORM messen (Skript: `scripts/calibrate_paper_hold.py`).
2. k so wählen, dass **E[|r_k|]** ≥ 3× Kostenboden (~0.6 %) — siehe Formel unten (**nicht** σ_k ≥ 0.6 %).
3. **`PAPER_HOLD_SECONDS` in §7 einfrieren** — inkl. WORM-sha256, Zeilenzahl, Zeitraum, dt-Verteilung, σ-Teilfenster.
4. Erst danach Exit-Code aktivieren und Round-Trips sammeln.

**Skript-Entscheidungen (verbindlich):**

| # | Regel | Begründung |
|---|-------|------------|
| 1 | Nur Tick-`SIGNAL` (`aggregate is not True`, `signal_id ≠ aggregate`) | `runner.py` schreibt auch Aggregate mit wiederholtem `mark_price` → verzerrt σ |
| 2 | **Preisbasis = 1s last-price Bars** (`--bar-seconds 1`); nicht Roh-Trade-Ticks | Trade-Prints (p50≈12 ms) blähen σ durch Mikrostruktur auf → **zu kurzes k** (gefährliche Richtung). Messkorrektur ≠ HARKing |
| 3 | Renditen **zeitnormiert** `ln(p_i/p_{i-1})/√Δt`; Δt > `gap_dt_s` (Default 30s) **ausschließen**; dt-p50/p95/p99/max ausgeben | Feed-Lücken sind keine Marktbewegung; Gap→zu hohes σ→**zu kurzes k** |
| 4 | Ziel: E[|r_k|] ≥ 0.6 % ⇒ σ_k ≥ 0.6 % / √(2/π) ≈ **0.7516 %** | E[|r|] ≠ σ; Gleichsetzen unterschätzt Horizont um ~20 % |
| 5 | σ über Teilfenster (min/med/max) ausweisen; **σ_1d = σ_√s·√86400** dokumentieren | Vola clustert; √k-Skalierung unterstellt i.i.d. — Spannweite + Tages-σ als Plausibilität |

**Formel (Implementierung):**

```text
# p_i = last mid/mark in UTC-second i  (1s last-price bar)
r̃_i = ln(p_i / p_{i-1}) / √Δt_i     # nur wenn 0 < Δt_i ≤ gap_dt_s
σ_√s = std(r̃)                        # pro √Sekunde
E[|r_k|] = σ_k · √(2/π),  σ_k = σ_√s · √k
Forderung: E[|r_k|] ≥ 3 × 0.002 = 0.006
         ⇒ σ_k ≥ 0.006 / √(2/π) ≈ 0.007516
         ⇒ k ≥ (0.007516 / σ_√s)²   Sekunden
```

```bash
# Cluster-WORM (Pfad-Schema unverändert):
kubectl cp trading/regime-swarm-0:/data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl \
  ./data/worm/ethusdt/paper_trades.worm.jsonl
# Verbindlich für Freeze (§7): 1s-Bars
PYTHONPATH=. python3 scripts/calibrate_paper_hold.py \
  --worm ./data/worm/ethusdt/paper_trades.worm.jsonl --bar-seconds 1 --print-freeze
# Kurzform:
make raas-paper-hold-calibrate-1s WORM=./data/worm/ethusdt/paper_trades.worm.jsonl
```

**Konservierung:** Jeder Freeze-Eintrag in §7 trägt `worm_sha256`, `n_worm_lines`, `ts_first→ts_last`, **`price_basis`**. Ohne Hash ist „σ aus dem WORM“ nicht rekonstruierbar.

**Anti-HARKing (Freeze-Satz):** Die Kalibrierung stellt sicher, dass die **Messung möglich** ist (Horizont räumt den Kostenboden), **nicht** dass sie günstig ausfällt. Kommt f* nach 50 Round-Trips ≤ 0 heraus, ist das ein Ergebnis — Signal ohne Kante nach Kosten. k danach nachjustieren, bis f* positiv wirkt, ist HARKing. Änderung von k nur via neuer Spec-Version + neues Pre-Reg-Freeze. **Messkorrektur der Preisbasis** (Trade-Tick → 1s-Bar) vor erstem Round-Trip-Lauf ist **kein** HARKing — siehe §7 Amendment 2026-08-29.

### 4.4 Positions-Disziplin (Unabhängigkeit für B2)

| Regel | Begründung |
|-------|------------|
| **Max. 1 offene Position** | Kein neuer BUY, solange `position_qty > 0` |
| **Keine überlappenden Round-Trips** | Überlappende Trades sind nicht unabhängig; B2 darf sie nicht als 50 i.i.d. Ziehungen behandeln |
| Nach SELL | Erst dann nächster Entry (optional: Cooldown in v2) |

### 4.5 Laufzeit bis Gate N=50

Bei Freeze-`PAPER_HOLD_SECONDS=4966` (~82,8 min) und einer Position zur Zeit: **~50 × 4966 s ≈ 69 h** (~2,9 Tage) bis 50 abgeschlossene Round-Trips (ohne Überlappung; zzgl. Entry-Lücken).

---

## 5. Implementierung (nächste PRs)

| PR | Inhalt |
|----|--------|
| **Option B Spec** | DECIDED — diese Datei §4 |
| **Kalibrierung** | `hold_calibration.py` + Freeze §7 (`PAPER_HOLD_SECONDS=4966`, 1s-Bars) |
| **Exit Pre-Reg** | [`PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) — I1–I6, Automat, Smoke |
| **Exit Code** | nach Freigabe der Pre-Reg: `feature/exit-implementation` (merged #29) |
| **Wiring** | `load_ledger_from_worm` → `PaperLedger` für B0-Hook |
| **Strang B** | `POSITION_SIZING_ENABLED=true`, Runbook §10, Metriken |

**Env (Entwurf, nach Freeze):**

```yaml
PAPER_EXIT_MODE: "time_hold"          # Option B
PAPER_HOLD_SECONDS: "4966"            # FROZEN §7 — 2026-08-29 (1s-Bar Amendment)
PAPER_EXIT_MAX_WAIT_S: "24830"        # 5 × 4966
PAPER_MAX_OPEN_POSITIONS: "1"
```

**Nicht:** Strang B nur per Env aktivieren.

---

## 6. Monitoring-Hinweise

```bash
# Vorheriger Container (nach Restart):
kubectl logs -n trading regime-swarm-0 --previous | grep cycle_complete

# Round-Trip-Fortschritt:
kubectl exec -n trading regime-swarm-0 -- sh -c \
  'echo -n SELL:; grep -c "\"side\": \"SELL\"" /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl'

# Cash/Position eingefroren (sim_buy → None):
kubectl exec -n trading regime-swarm-0 -- sh -c \
  'tail -3 /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl' | grep -E 'SIM_SKIP|SIM_FILL|cash_eur'
```

---

## 7. Kalibrierungs-Log (§4.3 Freeze)

**Status:** **FROZEN** 2026-08-29 (Amendment A1) — `make raas-paper-hold-calibrate-1s` · Preisbasis **1s last-price Bars**.

| Feld | Wert |
|------|------|
| `PAPER_HOLD_SECONDS` | **`4966`** (aus `recommended_hold_seconds=4966.50`, gerundet) |
| price_basis | **`last_price_bar` (bar=1s)** — verbindlich |
| n_price_points (1s-Bars) | `7859` |
| σ_per_√s (time-norm) | `0.00010671` |
| **σ_1d (= σ_√s·√86400)** | **`0.031365` (3.14%)** — ETH-üblich (3–5%) |
| target E[|r_k|] / σ_k | `0.0060` / `0.007520` |
| σ Teilfenster [min, med, max] | `[0.00004437, 0.00006342, 0.00020734]` |
| Hold aus Sub-Min / Sub-Max (Diagnose) | `28720 s` / `1315 s` — **nicht** Freeze-Wert; Span zeigt Vola-Clustering |
| n_tick_signals / n_returns / gaps_excl | `471254` / `7715` / `143` |
| WORM path (Cluster) | `/data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl` |
| WORM path (Kalibrierungs-Kopie) | `data/worm/ethusdt/paper_trades.worm.jsonl` |
| WORM sha256 | `9be6fdfd25d8399d1c15693fd7729c34e2f5024ccdeb7b22cf4578d2ba1615e8` |
| n_worm_lines | `942508` |
| ts range (UTC) | `2026-08-28T16:01:46+00:00` → `2026-08-29T07:00:38+00:00` |
| bar-dt p50/p95/p99/max (s) | `1.000` / `4.000` / `304.000` / `1258.000` (p99 inkl. Lücken; Returns nur Δt≤30s) |
| gap_dt_threshold_s | `30.0` |
| Messdatum (UTC) | `2026-08-29T08:15:24.390694+00:00` |
| Skript | `scripts/calibrate_paper_hold.py --bar-seconds 1` |
| Freigegeben von | §7 Amendment A1 — Messkorrektur Preisbasis (nicht Performance) |
| Anti-HARKing | Kalibrierung = Messbarkeit (Kostenboden), **nicht** günstiges f*. Änderung von `4966` nur via neuer Spec-Version + neues Pre-Reg-Freeze. |

**Freeze-Regel:** Punktwert aus Vollsample-σ_√s auf **1s-Bars** (`4966 s` ≈ **82,8 min**). Teilfenster-Span dokumentiert Instabilität der Vola; er ersetzt den Freeze nicht und darf nicht ex-post für f*-Optimierung genutzt werden.

### 7.1 Amendment A1 — Preisbasis Trade-Tick → 1s-Bar (2026-08-29)

| | |
|--|--|
| **Warum** | Originaler Freeze (§7.0) verwendete Roh-Trade-Ticks (p50≈12 ms). Mikrostruktur bläht σ künstlich auf (Faktor ~3.4 in σ / ~11 in k). |
| **Was geändert** | Zeitbasis = **1s last-price Bars**; Formel/Ziel E[|r_k|]≥0.6 % unverändert; **derselbe** WORM-sha256. |
| **Was nicht** | Keine Anpassung von k an f*/PnL/Edges. Kein Deploy mit k=433. |
| **Klassifikation** | **Messkorrektur** (wissenschaftliche Redlichkeit) — **kein** HARKing. |

#### 7.0 Superseded — Trade-Tick-Freeze (historisch, nicht deployen)

| Feld | Wert (superseded) |
|------|-------------------|
| `PAPER_HOLD_SECONDS` | ~~`433`~~ (aus `recommended_hold_seconds=432.55`) |
| price_basis | `trade_tick` (fehlerhaft für σ) |
| σ_per_√s / σ_1d | `0.00036157` / **10.63%** (Mikrostruktur-aufgebläht) |
| n_returns / gaps_excl | `48481` / `143` |
| dt p50/p95/p99/max (s) | `0.012` / `1.353` / `3.316` / `1258.249` |
| Messdatum (UTC) | `2026-08-29T07:00:45.801934+00:00` |
| Status | **SUPERSEDED** durch Amendment A1 — nur Archiv |

### 7.2 Abschlussnachweis — Vorhersage bestätigt (2026-08-29)

Vor dem Deploy stand die Plausibilitätsrechnung; nach A1 bestätigt die Messung dieselbe Größenordnung:

```text
Ziel-σ_k ≈ 0.75 %   (E[|r_k|] ≥ 0.6 % ⇒ σ_k = 0.6%/√(2/π))
k = 4966 s
σ_1s = 0.0075 / √4966 ≈ 0.0106 %
σ_1d = 0.0106 % × √86400 ≈ 0.0106 × 293.9 ≈ 3.1 % / Tag
```

| | Trade-Tick-Freeze (§7.0) | 1s-Bar-Freeze (A1) |
|--|-------------------------|---------------------|
| k | 433 s (~7,2 min) | **4966 s (~82,8 min)** |
| σ_1d | ~10,6 % | **~3,14 %** (gemessen) / ~3,1 % (Rückrechnung) |
| Faktor Zeit | 1× | ~11,5× |
| Faktor σ | aufgebläht ~3,4× | ETH-üblich (3–5 %) |

**Beleg Tick-Abstände (Trade-Stream):** p50≈12 ms → Mikrostruktur, nicht Markt-σ.  
**Beleg Lücken-Filter Kalibrierung:** Δt>30 s ausgeschlossen (143 Gaps); die Aufblähung kam trotzdem aus Trade-Bounce.  
**Klassifikation:** Vorhersage vor Messung → Zahl bestätigt → belastbarster Teil des Strangs; `4966` ist nicht „gegriffen“.

Live-Pfad schließt Lücken **nicht** (Exit wartet auf nächsten gültigen Tick). Deshalb §8: Haltedauer messbar, dirty Holds aus B2 ausschließbar.

---

## 8. B2-Sample-Disziplin (Freeze-k only)

**Estimand:** Verteilung der **k-Schritt-Rendite** bei eingefrorenem `PAPER_HOLD_SECONDS` (aktuell **4966**).

| Regel | Inhalt |
|-------|--------|
| **Gleicher k** | Nur Edges mit `hold_seconds_target == 4966`. Keine Mischung mit superseded 433 (oder anderen Horizonten). |
| **Sauberer Hold** | `|hold_seconds_actual − hold_seconds_target| ≤ gap_dt` (Default **30 s**). Späterer Exit nach Feed-Lücke → anderer Horizont → **ausschließen**. |
| **Exit-Grund** | Nur `exit_reason=hold_expired`. `force_exit` zählt nicht in die k-Stichprobe. |
| **Zähler** | `n_eligible_at_freeze_k` aus `paper_edges.jsonl` — **nicht** `grep SELL` auf dem WORM. |
| **Felder** | Jede Kante trägt `hold_seconds_actual`, `hold_seconds_target`, `hold_seconds_delta` (ab Deploy nach diesem Absatz). |

```bash
# Gate-Fortschritt (N_min=50):
PYTHONPATH=. python3 scripts/count_paper_edges_at_freeze.py \
  --edges ./data/audit/paper_edges.jsonl --freeze-k 4966
```

Round-Trip 1 (Live 2026-08-29): `target=4966`, `actual=4967.563`, `delta≈1.56 s` → **eligible**.

### 8.1 Pre-Reg Standby (vor Mehrheits-Sample) — 2026-08-29

**30-s-Schwelle (quantitativ, nicht gegriffen):**

```text
σ_1s ≈ 0.0106 %   (aus Freeze A1 / Ziel-σ_k)
σ_30s = 0.0106 % × √30 ≈ 5.8 bps
Zielbewegung bei k=4966:  ≈ 75 bps  (σ_k)
Ausführungsrauschen ≈ 8 % des Zielsignals
≪ Kostenboden 20 bps  → p,b nicht nennenswert verzerrt
```

**Erwartung Feed-Qualität (vor den Daten festgehalten):** Über 3–4 Tage Live-Feed **ohne** Lückenbehandlung im Exit-Pfad sollten **einige** Round-Trips am Delta scheitern (ineligible). Eine Ablehnungsquote grob zwischen wenigen Prozent und ~¼ wäre erwartbar. **`50/50 eligible` am Ende wäre nicht die gute Nachricht** — eher Hinweis, dass das Delta nicht auslöst, als dass drei Tage lang keine Unterbrechung war.

**Zwei Ablesungen des Zählers:**

| Ablesung | Bedeutung |
|----------|-----------|
| `n_eligible_at_freeze_k` | Gate für Strang B (N≥50) |
| `n_ineligible` / `by_reason` | Feed-/Hold-Qualität (sonst nirgends gemessen) |

Wall-Clock-Hold aus persistiertem `entry_tick_ts` (kein separates `hold_until`): Frist abgeleitet; Timer-Reset nach Restart wäre als Delta sichtbar.

**Feed-Gap Pre-Reg (FREIGABE):** Tick-Spacing vs. Delta ist **Invariante** (`n_delta ≤ n_tick_hits`), keine Kreuzvalidierung. Echte Unabhängigkeit: WebSocket-Disconnect (`source=socket`) ↔ Tick-Lücke (`source=tick_spacing`), Konkordanz ±1. Siehe [`PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md`](PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md).

---

## Siehe auch

- [`docs/PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md`](PAPER_FEED_GAP_DELTA_CONCORDANCE_PREREG.md) — Feed-Gap Invariante + Socket↔Tick (FREIGABE)
- [`docs/PAPER_EXIT_IMPLEMENTATION_PREREG.md`](PAPER_EXIT_IMPLEMENTATION_PREREG.md) — Implementierungs-Pre-Reg (I1–I6, Zustandsautomat, Smoke)
- [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) — B2, `INSUFFICIENT_HISTORY`
- [`docs/POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) — γ-Map, Strang B
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Betrieb
