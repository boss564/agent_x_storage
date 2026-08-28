# Paper Exit & Round-Trip — Voraussetzung für B2 / Strang B

**Status:** DECISION REQUIRED (2026-08-28)  
**Scope:** Live-Shadow Paper-Pfad (`LivePaperBridge` → `PaperTradingRunner`) · `live_execution=false`  
**Blockiert:** Strang B (`POSITION_SIZING_ENABLED=true`), B2 Kelly-Historie, Gate „≥50 abgeschlossene Trades“

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

Strang B erst freigeben, wenn dieser Zähler **≥ N** **und** Exit-Policy im Code aktiv ist (nicht nur historisch zufällig).

---

## 4. Exit-Optionen (Entscheidung offen)

Gleiche Mechanik existiert teilweise in `PaperTradingRunner` — muss für Live-Shadow **explizit** konfiguriert werden:

| Option | Mechanismus | Pros | Cons |
|--------|-------------|------|------|
| **A — Preis-Break** | `break_price_below` via Env/ConfigMap | Bereits in `runner.py:57–60`, `108–111` | Braucht sinnvolle Schwelle; bei Sideways selten SELL |
| **B — Max-Haltedauer** | Nach N Ticks / Δt → `sim_sell` | Regelmäßige Round-Trips für B2 | Künstliches Exit; Parameter Pre-Reg |
| **C — Regime-Signal** | A7 `regime_flag` / Klassenwechsel → Close | Kopplung an Schwarm | Komplexer; Amendment-Charter beachten |
| **D — Flat am Zyklusende** | Daemon-Cycle-Hook: Position flatten (paper) | Deterministisch pro 30s-Zyklus | Viele kleine Round-Trips; Fee-Drift |

**DECISION REQUIRED:** Eine Option (oder Kombination) wählen und in Config dokumentieren, bevor Strang B.

---

## 5. Implementierungs-Reihenfolge (nach Exit-Entscheidung)

| PR | Inhalt |
|----|--------|
| **#25 (Exit)** | Exit-Policy im Live-Pfad + Tests; ggf. Ledger-Persistenz über Restarts |
| **#26 (Wiring)** | `load_ledger_from_worm(worm_path)` → `PaperLedger` für B0-Hook |
| **#27 (Strang B)** | `POSITION_SIZING_ENABLED=true`, Runbook §10, Metriken |

**Nicht:** Strang B nur per Env aktivieren — führt zu `INSUFFICIENT_HISTORY` oder irreführenden `sizing_*`-Zählern ohne echte Kelly-Basis.

---

## 6. Monitoring-Hinweise

```bash
# Vorheriger Container (nach Restart):
kubectl logs -n trading regime-swarm-0 --previous | grep cycle_complete

# Cash/Position eingefroren (sim_buy → None):
kubectl exec -n trading regime-swarm-0 -- sh -c \
  'tail -3 /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl' | grep -E 'SIM_SKIP|SIM_FILL|cash_eur'
```

---

## Siehe auch

- [`docs/POSITION_SIZING_SUBSWARM.md`](POSITION_SIZING_SUBSWARM.md) — B2, `INSUFFICIENT_HISTORY`
- [`docs/POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) — γ-Map, Strang B
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md) — Betrieb
