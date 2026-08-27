# RaaS — Paper-Trading Setup v0

**Status:** MAP v0 (2026-08-27) · additiv · bindend unter Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · **`live_execution=false` strikt** · kein Order-Send  
**Nicht:** Echtgeld, Searcher-/Bundle-Send, Broker-API-Keys mit Trade-Recht, Anlageberatung  
**Basis:** `docs/RaaS_P9_MAPPING_v1.md` · v2 · v3 · `docs/AGENT_X_CHARTER.md` ·
Tag `v1.0-raas-baseline`

v0–v3 Maps und P₁…P₉-**Funktionen bleiben unverändert**. Dieses Dokument beschreibt
einen **Betriebsmodus** (Paper) für einen Einreicher — keine Multi-Schwarm-Policy,
kein P-Remap.

---

## 1. Produkt (eine Zeile)

**Live-Marktdaten einlesen → virtuelles Konto mit realistischen Gebühren führen →
Signale und Kennzahlen in WORM loggen — niemals eine Order absenden.**

---

## 2. Abgrenzung (Wahrheit vor Optik)

| Artefakt | Was es ist | Was es **nicht** ist |
|----------|------------|----------------------|
| Diese Map | RaaS-Paper-Modus (Intent → Bau) | Freigabe für Live-Trading |
| `scripts/paper_trading_agent_x.py` | Agent-X-**Core** CHI/Konsensus-Replay | RaaS-P9 Paper mit Binance-WS + 1.000 €-Konto |
| `scripts/ingest_public_distributions.py` | Gebundene Kline-/MEV-**Sondierung** | Dauerhafter WebSocket-Feed für Paper |
| P₃ in v1 | Execution-**Pressure / Risiko**-Simulation | Order-Router |
| B2B Exporter | Gutachten-Output | Trade-Bestätigung |

Bestehende P₁/P₃/P₆/P₉-Implementierung wird **nicht** umgebaut; Paper hängt als
Adapter/Logger an Intake und Gate, mit hartem Cut vor jedem Send-Pfad.

---

## 3. Drei Schritte (Bewertungs-Matrix)

| Schritt | Rolle (Lesart) | Soll | Ist (2026-08-27) | Gate |
|---------|----------------|------|------------------|------|
| **1** Marktdaten | P₁-nah (Ingest) | Echte Live-Feeds: Binance Spot WS und/oder Pyth (read-only) | Sondierung REST/Klines vorhanden; **kein** RaaS-WS-Dauerfeed | `PAPER_FEED_PASS` — Heartbeat, Sequenz, kein Trade-Endpoint |
| **2** Virtuelles Konto | P₃-nah (Pressure/Fees) | Start **1.000 €** · Gebühren/Slippage-Modell aus öffentlichen Tarifen · kein Custodial | Fehlt im RaaS-Pfad | `PAPER_LEDGER_PASS` — Δ-Buchungen, Gebühren ≠ 0-Annahme |
| **3** Signal-Log | P₆/P₉ (Gate/Archiv) | Jedes Signal → Gate-Kontext + WORM; **kein** Order-Send | Portal-WORM + B2B-Exporter; Paper-Trade-Log-Format **neu** | `PAPER_WORM_PASS` · Assert `live_execution=false` auf jeder Zeile |

**Charter-Zeile (bindend auf jeder Paper-Zeile / jedem Envelope):**

```text
live_execution=false · not_investment_advice=true · order_send=forbidden
```

Ein Adapter, der `order_send` oder Exchange-`POST …/order` andeutet, ist Map-Verstoß.

---

## 4. Virtuelles Ledger (Schritt 2 — Spezifikation)

| Feld | Festlegung |
|------|------------|
| `starting_balance_eur` | `1000.00` (Decimal) |
| `currency` | EUR-äquivalent (Marktdaten ggf. USDC/USDT → FX-Hinweis dokumentieren) |
| `fee_model` | Spot taker/maker aus öffentlicher Fee-Tabelle (Snapshot + Datum im Manifest) |
| `slippage_model` | konservativ; Parameter im Manifest gehasht (Freeze vor Testphase) |
| `positions` | nur simuliert; keine Wallet-Keys |
| BHO-Analog | Buchungen Zero-Sum im Paper-Ledger: Cash + Position_Mark + Fees_Paid = Start + PnL |

Fail-Closed: fehlende Fee-Tabelle → kein Paper-Fill (nur Signal loggen).

---

## 5. Paper-Trade-Log (WORM-Format)

Append-only JSONL unter:

```text
{data_root}/{tenant_id}/paper/runs/{run_id}/paper_trades.worm.jsonl
```

**Pflichtfelder je Zeile:**

| Feld | Inhalt |
|------|--------|
| `ts` | ISO-8601 UTC |
| `tenant_id` | Einreicher (submitter-only) |
| `run_id` | Paper-Run |
| `signal_id` | korreliert zu Gate/Stress |
| `action` | `SIGNAL` \| `SIM_FILL` \| `SIM_SKIP` \| `HEARTBEAT` — **nie** `ORDER_SENT` |
| `live_execution` | immer `false` |
| `mark_price` / `qty` / `fee_eur` / `cash_eur` / `equity_eur` | Decimal-Strings |
| `m7_latency_ms` | Gate-/Feed-Latenzprobe (wenn verfügbar) |
| `hash` / `prev_hash` | WORM-Kette (wie Portal-Audit) |

**Aggregat-Snapshot (täglich oder run-end, ebenfalls WORM):**

| Kennzahl | Rolle | Zielhaltung (Testphase) |
|----------|-------|-------------------------|
| **Envelope-Trefferquote** | **primär** | Anteil eingetretener Bruchbedingungen, die vorhergesagt waren; Anteil vorhergesagter, die eintraten (Precision/Recall der Safety-Aussage) |
| Max Drawdown | Diagnostik | Ledger-Plausibilität; Schwelle vor Start festschreiben — **kein** Freigabe-Kriterium |
| Profit Factor | **nur Diagnostik** | prüft, ob die Simulation überhaupt plausibel läuft; **keine** Zielkennzahl, **kein** Pitch-/Track-Record-Claim |
| M7-Latenz p50/p99 | Diagnostik | gegen Live-Z3-/Gate-Baseline; kein Fake |
| Fill-Rate (sim) | deskriptiv | — |
| `order_send_count` | Hard-Gate | **muss 0 bleiben** |

**Primärfrage der Testphase:** Stimmt der Safety Envelope unter Live-Marktdaten?
(Vorhergesagte Brüche ↔ eingetretene Brüche.) Nicht: „Soll die Strategie live laufen?“

Ein 30-Tage-Fenster macht einen Ertrags-Pitch **nicht** zulässig — es belegt nur länger
die Envelope-Trefferquote. `not_investment_advice=true` bleibt; Profit Factor darf in
Reports nur als `diagnostic_only=true` erscheinen.

---

## 6. Testphase (30 Tage)

| Regel | Inhalt |
|-------|--------|
| Dauer | 30 Tage am Stück **nach** Feed+Ledger+WORM-Gates grün |
| Auslöser Start | schriftlich: Manifest (Fee/Slippage/Symbol) gehasht · Tag/Commit notiert |
| Abbruch | `order_send_count>0` · `live_execution≠false` · Feed-Lücke > SLA · Ledger Δ≠0 |
| Ergebnis | WORM-Export + optional B2B-Gutachten — **primär Envelope-Trefferquote**; Ertragskennzahlen nur diagnostisch, kein Live-Performance-/Empfehlungs-Claim |
| Multi-Schwarm | außerhalb Scope; ein `tenant_id` (v3 §4.1 Verzeichnis-Schuld) |

---

## 7. Architektur-Skizze (kein Code in dieser Map)

```text
Binance WS / Pyth (read-only)
        │
        ▼
  Paper Feed Adapter ──► P1-Intake-Felder (Marktdaten, kein Trade)
        │
        ▼
  Paper Ledger (1.000 €, Fees) ──► SIM_FILL / SIM_SKIP only
        │
        ▼
  Gate / M7 / Z3 (wie RaaS) · live_execution=false
        │
        ▼
  WORM paper_trades + optional B2B Exporter
        ✕
  Exchange Order API  (FORBIDDEN)
```

---

## 8. Nicht jetzt / Auslöser

| Arbeit | Status |
|--------|--------|
| Diese Map | ✅ |
| WS-Feed-Adapter + Ledger + Paper-WORM | ✅ Smoke (`make raas-paper-trading-smoke`) · Live-WS optional · 30-Tage gesperrt |
| Paper-Report aus WORM (`exports/reports/`) | ✅ `make raas-paper-report` — **keine Sample-Fills**; Audit muss existieren |
| Option 5 Flash-Crash-Retrospective | ✅ MAP `docs/RaaS_FLASH_CRASH_RETROSPECTIVE_v0.md` · `make raas-flash-crash-retro` (14d Smoke) / `--days 180` |
| 30-Tage-Lauf | **gesperrt** bis Fee/Slippage-Manifest gehasht + Startsignal |
| Order-Send / API-Keys mit Trade-Scope | **verboten** |
| v3 Multi-Schwarm / M1 Prefilter | orthogonal; Paper nutzt M1 wenn Prefilter an (je Mandant) |
| Core-`paper_trading_agent_x.py` ersetzen | **nein** — eigener RaaS-Pfad |

**Report (P9 output-only):**

```bash
# Voraussetzung: Audit aus Smoke
make raas-paper-trading-smoke
# Markdown aus realem WORM (kein Fake bei fehlendem Log)
PYTHONPATH=. python3 services/exporter/agent_x_raas_exporter.py \
  --mode paper_trading --format markdown
# optional: --open  ·  --format all (md+json+pdf)
```

Quelle: `logs/worm/paper_trading_audit.jsonl` → `exports/reports/paper_trades_latest.md`.
Primärmetrik = Envelope Hit-Rate; Profit Factor nur als `diagnostic_only`.
B2B-Gutachten-Pfad (`--mode b2b`) bleibt unverändert.

**Auslöser Bau:** explizites Startsignal · Fee-/Slippage-Manifest · Symbol-Liste ·
Abbruch-Schwellen vorab.

---

## 9. Verweise

| Dokument / Artefakt | Rolle |
|---------------------|-------|
| `docs/RaaS_P9_MAPPING_v1.md` | Strategie · Envelope · Advice-Schuld |
| `docs/RaaS_P9_MAPPING_v3.md` | Multi-Schwarm · M1 · Envelope-Isolation |
| `docs/RaaS_BUS_EXPANSION_v0.md` §4.3 | Public-Ingest / Referenz A (kein Live-Trade) |
| `services/exporter/` | B2B-Gutachten + Paper-Report (`--mode paper_trading`) |
| `logs/worm/paper_trading_audit.jsonl` | Paper-WORM (Quelle für Report) |
| `exports/reports/paper_trades_latest.md` | Shadow-Trade-Report (gitignored under `exports/`) |
| `scripts/paper_trading_agent_x.py` | Core-Paper (CHI) — **nicht** diese Map |
| Tag `v1.0-raas-baseline` | Fixierte RaaS-Baseline vor Paper-Bau |
