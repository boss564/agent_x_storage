# Position Sizing Sub-Schwarm (B0–B8) — Design-Review v0

**Status:** REVIEW (2026-08-28) · **keine Implementierung** bis Charter-Abschnitt freigegeben  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · `order_send=false`  
**Parent:** Regime-Schwarm A1–A9 · [`prototypes/raas_paper_trading/regime_swarm/`](../prototypes/raas_paper_trading/regime_swarm/)  
**Basis:** [`docs/RaaS_P9_MAPPING_v1.md`](RaaS_P9_MAPPING_v1.md) · [`docs/RaaS_REGIME_DRIFT_PREREG.md`](RaaS_REGIME_DRIFT_PREREG.md)

---

## 1. Zweck (eine Zeile)

Unter gegebenen Paper-Ledger-Daten und Trade-Historie **berechnen**, ob eine *hypothetische* Kelly-Notional die **2‑%-Kapital-Schranke** reißen würde — und die **Schranke** protokollieren, nicht eine Positionsempfehlung.

Analog A0/A2.5: kein „so handeln“, sondern „ab hier trägt der Zyklus / das Limit nicht mehr“.

---

## 2. Charter-Dreieck (Ebene 1 vs. Ebene 2)

| Feld | Ebene | Verhalten heute |
|------|-------|-----------------|
| `live_execution` | **2** | `PaperWormLog` / Ledger: `raise` bei `ORDER_SENT` oder `true` |
| `order_send` | **2** | strukturell `false` auf jeder Paper-Zeile; Ledger `order_send_count==0` |
| `not_investment_advice` | **1** | Literal `true` auf jeder Zeile — **prüft den Inhalt nicht** |

Quelle Schuld-D1: [`RaaS_P9_MAPPING_v1.md:50`](RaaS_P9_MAPPING_v1.md) — Deklaration in der Map; Durchsetzung wie `live_execution` erst beim Intake (Wave-39 / `DSuiteEnforcer` D1 scannt nur Free-Text in definierten Keys, nicht numerische Mengenfelder).

**Konsequenz:** Der B-Schwarm wäre das **erste Subsystem**, das numerische Größen in die Audit-Kette schreibt. Solange `not_investment_advice` ein Literal bleibt, muss **jede Ausgabezeile** so formuliert sein, dass die Deklaration **inhaltlich haltbar** ist — nicht nur technisch gestempelt.

---

## 3. Entscheidung: Ausgabe-Vokabular (Charter-kritisch)

Gleiche Mathematik (Kelly-f*, γ, p, b, 2‑%-Limit). Unterschied ist **was exportiert wird**:

| Ausgabe | Frage | Charter |
|---------|-------|---------|
| `advisory_position_size` / `recommended_units` | „Wie viel soll ich setzen?“ | **Kollidiert** mit `not_investment_advice: true` |
| `max_notional_before_limit_breach_eur` | „Bei welcher Notional (EUR) reißt die 2‑%-Schranke?“ | **Konsistent** — Belastungsgrenze |
| `max_units_before_limit_breach` | Einheiten **abgeleitet aus der Schranke** (`schranke_eur / preis`), nicht aus Kelly | **Konsistent**, wenn als Bruchbedingung labelbar |
| `computed_hypothetical_notional_eur` | Kelly-Implikat (nur Diagnose / Vergleich) | **Erlaubt** in B8-Audit, **nicht** als primäres WORM-Feld |

B6 benennt intern `Sizing-Gate` — gilt für die **gesamte Export-Schicht**, nicht nur den Gate-Namen:

- **PASS:** hypothetische Notional ≤ Schranke → `sizing_gate_decision: LIMIT_OK`
- **BLOCK:** hypothetische Notional > Schranke → `sizing_gate_decision: LIMIT_EXCEEDED`, `order_send: false` (unverändert)
- **INSUFFICIENT_HISTORY:** kein Kelly-Output als Empfehlung — **Hard-Block**, kein Fallback-p

---

## 4. Was steht in welcher Zeile (Nachweis `not_investment_advice`)

### 4.1 Paper-WORM (`paper_trades.worm.jsonl`) — **unverändert**

Weiterhin nur Feed-/Signal-Pfad (`SIGNAL`, `HEARTBEAT`, `mark_price`). **Keine** B-Schwarm-Felder.  
Begründung: diese Datei ist Preis-Telemetrie; Sizing ist ein separater diagnostischer Pfad.

### 4.2 Sizing-Audit (`/data/audit/position_sizing.jsonl`) — **neu, append-only**

Hash-Kette wie Regime-Audit. Jede Zeile trägt Charter-Stempel; Inhalt muss zur Deklaration passen.

**Pflichtfelder (v0):**

```json
{
  "schema": "raas_position_sizing_v0",
  "action": "SIZING_BOUNDARY",
  "cycle_id": "SIZE-8823",
  "ts": "2026-08-28T14:32:11.123Z",
  "symbol": "ETHUSDT",
  "capital_eur": 1000.0,
  "capital_source": "paper_ledger.cash_eur+mark_to_market",
  "price_eur": 2500.0,
  "stats_window_n": 50,
  "stats_count": 12,
  "status": "INSUFFICIENT_HISTORY",
  "p": null,
  "b": null,
  "gamma": 0.25,
  "kelly_fraction_computed": null,
  "computed_hypothetical_notional_eur": null,
  "risk_limit_fraction": 0.02,
  "max_notional_before_limit_breach_eur": 20.0,
  "max_units_before_limit_breach": 0.008,
  "sizing_gate_decision": "INSUFFICIENT_HISTORY",
  "order_send": false,
  "live_execution": false,
  "not_investment_advice": true,
  "diagnostic_only": true,
  "scope": "DEFENSIVE_CAUSAL_GROUNDING"
}
```

**Beispiel LIMIT_EXCEEDED (Kelly rechnerisch über Schranke, kein Send):**

```json
{
  "action": "SIZING_BOUNDARY",
  "status": "COMPLETE",
  "stats_count": 50,
  "p": 0.6,
  "b": 1.5,
  "kelly_fraction_computed": 0.15,
  "computed_hypothetical_notional_eur": 150.0,
  "max_notional_before_limit_breach_eur": 20.0,
  "max_units_before_limit_breach": 0.008,
  "sizing_gate_decision": "LIMIT_EXCEEDED",
  "order_send": false,
  "not_investment_advice": true,
  "diagnostic_only": true
}
```

### 4.3 Warum das `not_investment_advice: true` **haltbar** ist

| Kriterium | Erfüllung |
|-----------|-----------|
| Keine Imperative | Kein „buy/sell/allocate“; D1-Free-Text-Scan (`DSuiteEnforcer`) bleibt grün |
| Semantik | Zeile beantwortet **Belastungsgrenze** („Limit bricht bei X EUR Notional“), nicht Allokation |
| Vergleichswert | `computed_hypothetical_notional_eur` ist explizit **Hypothese unter Kelly-Annahmen**, nicht Handlungsoutput |
| Parallel A0 | A0 meldet „BLOCK bei Y % Preisbewegung“ — ebenfalls Grenzzustand, keine Empfehlung |
| Execution | `order_send` und `live_execution` bleiben strukturell false; B6 blockiert nur die *hypothetische* Größe im Audit |

**Verboten** in Sizing-Audit (Review-Gate vor Merge):

- `advisory_position_size`, `recommended_units`, `target_allocation`, `should_trade`
- Freitext mit `_ADVICE_RE`-Treffern in scanbaren Keys (`recommendation`, `rationale`, …)

### 4.4 Regime-Cycle-Report (optionaler Querverweis)

Im Daemon-Report (`regime_drift_latest.json`) höchstens ein ** eingebetteter Block**:

```json
"sizing_envelope": {
  "linked": true,
  "sizing_gate_decision": "LIMIT_OK",
  "max_notional_before_limit_breach_eur": 20.0
}
```

Keine Einheiten-Empfehlung auf Top-Level.

---

## 5. Neun Agenten (B0–B8)

| ID | Agent | Sub-Schwarm | Verantwortung (charter-aligned) |
|----|-------|-------------|----------------------------------|
| **B0** | Orchestrator | Meta-Control | Pipeline B1→B8; γ; bei `INSUFFICIENT_HISTORY` / `LIMIT_EXCEEDED` → Block-Status |
| **B1** | Kapital-Manager | Daten | `PaperLedger` Saldo (cash + mark-to-market), **kein** fixes Startkapital |
| **B2** | Statistik-Aggregator | Daten | p, b aus letzten N Trades; **< N_min → Status INSUFFICIENT_HISTORY** |
| **B3** | Kelly-Rechner | Core | f* = γ·(p·b−(1−p))/b; nur wenn B2 COMPLETE |
| **B4** | Notional-Rechner | Core | `hypothetical_notional_eur = f* · capital_eur` (Diagnose) |
| **B5** | Risiko-Prüfer | Gate | Vergleich **Notional EUR** vs. `capital_eur · risk_limit` |
| **B6** | Sizing-Gate-Adapter | Gate | LIMIT_OK / LIMIT_EXCEEDED / INSUFFICIENT_HISTORY; **kein** Exchange-Z3 |
| **B7** | Shadow-Replay | Test | Offline auf archivierten WORMs / Replay — **nicht** zweiter Live-Thread |
| **B8** | Audit-Agent | Compliance | Nur §4.2-Schema; Hash-Kette; CRITICAL bei LIMIT_EXCEEDED |

**Z3-Hinweis:** Bestehender Z3-Service (`/prove_bho_invariant`) = BHO Zero-Sum, **nicht** Sizing. B6 ist deterministischer Sizing-Gate (wie A0), optional später formalisierbar.

---

## 6. Sizing-Mechanik (festgelegt im Review)

### 6.1 Einheiten (B5-Fix — verbindlich)

```text
capital_eur          ← B1 (EUR)
price_eur            ← letzter SIGNAL / Mark (EUR)
kelly_fraction f*    ← B3 (dimensionslos, Anteil am Kapital)
hypothetical_notional_eur = f* × capital_eur     ← B4 (EUR)
max_notional_before_limit_breach_eur = capital_eur × risk_limit_fraction   ← Schranke (EUR)
max_units_before_limit_breach = max_notional_before_limit_breach_eur / price_eur

FALSCH (v0 Spec verworfen):
  risk_fraction = position_units / capital_eur   # Einheiten/EUR — numerisch wirkungslos
```

### 6.2 Risiko-Limit

- **Auf Notional (EUR)**, nicht auf f* allein.
- Default `risk_limit_fraction = 0.02` (2 % des Kapitals pro Trade-Notional).
- f* begrenzt die Formel; die Schranke begrenzt das, was im Zweifel wehtun würde.

### 6.3 Historie (B2)

| Parameter | Wert Review | Verhalten |
|-----------|-------------|-----------|
| `window_size` N | 50 | Ziel-Fenster |
| `min_trades` N_min | **50** (gleich N) | `< N_min` **abgeschlossene Round-Trips** (SELL) → `INSUFFICIENT_HISTORY`, **kein** Kelly, **kein** p=0.5/b=1.0-Fallback |

Begründung: Default-p=0.5 sieht aus wie Messung; bei dünnen Paper-WORMs wäre das der Normalfall.

**Voraussetzung Paper-Pfad:** Live-Shadow ohne Exit-Policy erzeugt nur BUY — B2 bleibt leer. Siehe [`PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md).

### 6.4 Kapital (B1)

- Quelle: **`PaperLedger`** (`cash_eur` + offene Position mark-to-market).
- Fixes Startkapital verworfen (f* würde zeitinvariant, Rückkopplung unsichtbar).

---

## 7. Workflow

```text
B1 capital_eur
  → B2 p,b oder INSUFFICIENT_HISTORY → STOP (B6/B8)
  → B3 f* (nur wenn COMPLETE)
  → B4 hypothetical_notional_eur
  → B5 compare vs max_notional_before_limit_breach_eur
  → B6 sizing_gate_decision
  → B7 (offline/replay only)
  → B8 audit JSONL §4.2
```

Integration Regime (optional, Flag `POSITION_SIZING_ENABLED=false`):

```text
A7 classified_regime → (optional γ-Map) → B0 → sizing_envelope an A8-Context
A8 bleibt advisory_only; liest Schranke, schlägt keine Stückzahl vor
```

---

## 8. Offene Entscheidungen (vor PR)

| # | Thema | Optionen | Owner |
|---|-------|----------|-------|
| 1 | **γ Default + Regime-Map** | z. B. LOW_DRIFT→0.15, TREND→0.25, HIGH_VOL→0.10 | Produkt |
| 2 | **Trigger** | Jeder Daemon-Zyklus vs. nur wenn A7 `regime_flag≥1` | Mess-Design |
| 3 | **N_min < N** | Striktes N_min=50 vs. gestuftes N_min=30 mit `confidence: LOW` | Statistik |
| 4 | **D1 Ebene 2** | Numerische Allowlist + Verbotsliste im `DSuiteEnforcer` | Wave-39 / Intake |

Items 1–2 blockieren PR nicht für v0, wenn Default γ=0.25 und Trigger=„jeder Zyklus“ dokumentiert werden.

---

## 9. Prometheus / Beobachtung (nach Implementierung)

| Metrik | Bedeutung |
|--------|-----------|
| `sizing_gate_block_total{reason}` | LIMIT_EXCEEDED / INSUFFICIENT_HISTORY |
| `max_notional_before_limit_breach_eur` | Gauge (Schranke) |
| Korrelation | `swarm_ticks_last_cycle` ↓ + `drift_counter` ↑ → Feed-Artefakt (Regime-Runbook) |

---

## 10. Nächster Schritt

1. **Review-Freigabe** dieses Abschnitts §4 (WORM/Audit-Zeile) + §6 (Einheiten).  
2. **PR v0:** `prototypes/raas_paper_trading/position_sizing/` — B0–B8, Unit/Smoke, kein Helm.  
3. **Kein** Schreiben in `paper_trades.worm.jsonl` mit Mengenfeldern.  
4. Shadow-Live: Sizing-Audit + Gate-Counter 1–2 Tage parallel zum Regime-Schwarm.

**Implementierung (PR v0):** `prototypes/raas_paper_trading/position_sizing/` · Smoke: `make raas-position-sizing-smoke` · Flag: `POSITION_SIZING_ENABLED=false` (Default).

---

## Siehe auch

- [`docs/POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) — Strang C: γ-Map & A7-Trigger (Review)
- [`docs/REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md`](REGIME_SWARM_LIVE_SHADOW_RUNBOOK.md)
- [`services/fail_closed_gate/d_suite_enforcer.py`](../services/fail_closed_gate/d_suite_enforcer.py) — D1
- [`prototypes/raas_paper_trading/ledger.py`](../prototypes/raas_paper_trading/ledger.py) — B1-Quelle
