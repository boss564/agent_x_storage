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
| 2 | Renditen **zeitnormiert** `ln(p_i/p_{i-1})/√Δt`; Δt > `gap_dt_s` (Default 30s) **ausschließen**; dt-p50/p95/p99/max ausgeben | Feed-Lücken sind keine Marktbewegung; Gap→zu hohes σ→**zu kurzes k** (gefährliche Richtung) |
| 3 | Ziel: E[|r_k|] ≥ 0.6 % ⇒ σ_k ≥ 0.6 % / √(2/π) ≈ **0.7516 %** | E[|r|] ≠ σ; Gleichsetzen unterschätzt Horizont um ~20 % |
| 4 | σ über Teilfenster (min/med/max) ausweisen | Vola clustert; √k-Skalierung unterstellt i.i.d. — Spannweite zeigt Stabilität |

**Formel (Implementierung):**

```text
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
PYTHONPATH=. python3 scripts/calibrate_paper_hold.py \
  --worm ./data/worm/ethusdt/paper_trades.worm.jsonl --print-freeze
```

**Konservierung:** Jeder Freeze-Eintrag in §7 trägt `worm_sha256`, `n_worm_lines`, `ts_first→ts_last`. Ohne Hash ist „σ aus dem WORM“ nicht rekonstruierbar.

**Anti-HARKing (Freeze-Satz):** Die Kalibrierung stellt sicher, dass die **Messung möglich** ist (Horizont räumt den Kostenboden), **nicht** dass sie günstig ausfällt. Kommt f* nach 50 Round-Trips ≤ 0 heraus, ist das ein Ergebnis — Signal ohne Kante nach Kosten. k danach nachjustieren, bis f* positiv wirkt, ist HARKing. Änderung von k nur via neuer Spec-Version + neues Pre-Reg-Freeze.

### 4.4 Positions-Disziplin (Unabhängigkeit für B2)

| Regel | Begründung |
|-------|------------|
| **Max. 1 offene Position** | Kein neuer BUY, solange `position_qty > 0` |
| **Keine überlappenden Round-Trips** | Überlappende Trades sind nicht unabhängig; B2 darf sie nicht als 50 i.i.d. Ziehungen behandeln |
| Nach SELL | Erst dann nächster Entry (optional: Cooldown in v2) |

### 4.5 Laufzeit bis Gate N=50

Bei ~1 h Haltedauer und einer Position zur Zeit: **~50 h ≈ 2 Tage** bis 50 abgeschlossene Round-Trips (ohne Überlappung).

---

## 5. Implementierung (nächste PRs)

| PR | Inhalt |
|----|--------|
| **Option B Spec** | DECIDED — diese Datei §4 |
| **Kalibrierung** | `hold_calibration.py` + `calibrate_paper_hold.py` → Vorschlag `PAPER_HOLD_SECONDS`; Freeze erst nach Live-WORM-Lauf in §7 |
| **Exit** | `PaperTradingRunner`: Zeit-Exit nach `hold_seconds`; 1-Position-Regel; WORM-Felder `entry_ts` / `exit_reason: TIME_HOLD` |
| **Wiring** | `load_ledger_from_worm(worm_path)` → `PaperLedger` für B0-Hook |
| **Strang B** | `POSITION_SIZING_ENABLED=true`, Runbook §10, Metriken |

**Env (Entwurf, nach Freeze):**

```yaml
PAPER_EXIT_MODE: "time_hold"          # Option B
PAPER_HOLD_SECONDS: "<frozen>"        # aus §4.3 Kalibrierung
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

**Status:** Skript bereit (`make raas-paper-hold-calibrate-smoke`); **Freeze-Werte TBD** bis Live-WORM-Lauf mit `--print-freeze`.

| Feld | Wert |
|------|------|
| `PAPER_HOLD_SECONDS` | **TBD** — nach `calibrate_paper_hold.py --print-freeze` auf Live-WORM |
| σ_per_√s (time-norm) | TBD |
| target E[|r_k|] / σ_k | `0.0060` / `≈0.007516` |
| σ Teilfenster [min, med, max] | TBD |
| n_tick_signals / n_returns / gaps_excl | TBD |
| WORM path | `/data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl` |
| WORM sha256 | TBD |
| n_worm_lines | TBD |
| ts range (UTC) | TBD |
| dt p50/p95/p99/max (s) | TBD |
| gap_dt_threshold_s | `30` (Default) |
| Messdatum | TBD |
| Freigegeben von | TBD |
| Anti-HARKing | Kalibrierung = Messbarkeit (Kostenboden), **nicht** günstiges f*; f*≤0 nach N Round-Trips ist Ergebnis, kein Anlass k nachzuziehen |

---

## Siehe auch

- [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) — B2, `INSUFFICIENT_HISTORY`
- [`docs/POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) — γ-Map, Strang B
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Betrieb
