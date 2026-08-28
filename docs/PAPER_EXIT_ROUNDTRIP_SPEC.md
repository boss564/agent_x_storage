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

1. σ aus vorhandener WORM messen (670k+ `SIGNAL`-Zeilen reichen).
2. k so wählen, dass erwartete |Δ| über k **≥ 3× Kostenboden** (~0.6 % absolut).
3. **`PAPER_HOLD_SECONDS` (oder `PAPER_HOLD_TICKS`) in dieser Spec einfrieren** — dokumentiert mit Messdatum und σ-Schätzer.
4. Erst danach Exit-Code aktivieren und Round-Trips sammeln.

**Faustformel (Überschlag, auf eigenen Daten zu verifizieren):**

```text
E[|r_k|] ≥ 3 × 0.002   # 3 × 20 bps
k ≈ (0.006 / σ_per_tick)^2  in Ticks   (random-walk-Näherung, grob)
```

Überschlag Live-ETH: **~1 Stunde** Haltedauer — **nicht** übernehmen ohne Kalibrierung auf dem eigenen WORM.

**Anti-HARKing:** k darf **nicht** nachträglich an f* angepasst werden. Änderung nur via neuer Spec-Version + neues Pre-Reg-Freeze.

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
| **#26 (Kalibrierung)** | Skript: σ aus WORM → empfohlenes `PAPER_HOLD_SECONDS`; Freeze-Wert in Spec §4.3 eintragen |
| **#27 (Exit)** | `PaperTradingRunner`: Zeit-Exit nach `hold_seconds`; 1-Position-Regel; WORM-Felder `entry_ts` / `exit_reason: TIME_HOLD` |
| **#28 (Wiring)** | `load_ledger_from_worm(worm_path)` → `PaperLedger` für B0-Hook |
| **#29 (Strang B)** | `POSITION_SIZING_ENABLED=true`, Runbook §10, Metriken |

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

| Feld | Wert |
|------|------|
| `PAPER_HOLD_SECONDS` | **TBD** — nach Skript-Lauf auf Live-WORM |
| σ-Schätzer | TBD |
| Messdatum / WORM-Pfad | TBD |
| Freigegeben von | TBD |

---

## Siehe auch

- [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) — B2, `INSUFFICIENT_HISTORY`
- [`docs/POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) — γ-Map, Strang B
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Betrieb
