# Choral-Text — Prompt- & Agenten-Katalog

**Quelle:** `imports/cherrystudio/choral_text/` (Spiegel von `/Volumes/THX_CORE_16TB/cherrystudio_projekte/choral_text/`)  
**Stand der Sichtung:** 2026-08-30 · reine Lese-Analyse · keine Cluster-Änderung  
**Ausgeschlossen:** `.py`, `.venv`, `.git`, Drittanbieter-Samples (AKWF, VSCO2, DiffSinger), JSON/YAML-Patches

---

## 1. Ordner-Scan

| Kategorie | Dateien | Rolle |
|-----------|---------|--------|
| Projekt-Prompts / Runbooks (Root) | 8 | Katalogisiert unten |
| Session-/Mix-Logs | 2 | Hilfsdokumentation |
| Drittanbieter-Docs | ~13 | Ignoriert (DiffSinger, AKWF, VSCO2, pytest-cache) |

**Root-Markdown (vollständig gelesen):**

| Datei | Typ |
|-------|-----|
| `CLAUDE.md` | System-Prompt / Plattform-Vertrag (16 Domänen, 131 Agenten) |
| `CLAUDE2.md` | Mix-Assistent Agent 1 (Audio, nicht Trading) |
| `AGENT_0_3_TEMPLATE_v3.md` | Einziges explizites `Du bist Agent …`-Template |
| `START_HIER.md` | Operator-Runbook (Trading-CLI, Daemons, Neo4j) |
| `README.md` | Architektur 20-Agenten-Schwarm |
| `PROJEKT_LOG.md` | Chronik (u. a. AstroCore, Liquidation, Risk-Guard) |
| `TIEFENANALYSE_THIXONAUT_CORE.md` | Mess-Audit + Regex-Invariante |
| `PROJEKT_UEBERBLICK.md` | Auto-Inventar 1597 Projekte (kein Prompt) |

**Befund:** Es gibt **kein** `AGENT_*_TEMPLATE` für Trading. Die Trading-/Risk-Logik steckt in `CLAUDE.md` (Vertrag) und `PROJEKT_LOG.md` (Sessions), nicht in ausformulierten System-Prompts. Das einzige Copy-Paste-Template mit `Du bist Agent …` ist musikalisch (`AGENT_0_3_TEMPLATE_v3.md`).

---

## 2. Inhalts-Katalog nach funktionaler Rolle

### Strategie & Trading-Logik

| Quelle | Inhalt | Für Agent-X |
|--------|--------|-------------|
| `START_HIER.md` / `README.md` | Pipeline: rank → scan → rebalance → backtest; Paper-Ledger; Wilder-ATR; Sentiment-Fenster P30D; Fake-Signal-Guard (<15 Bars) | Bereits teilweise in Core/Backtest. Nicht 1:1 übernehmen (RRR bewusst entfernt). |
| `PROJEKT_LOG.md` (01.08.) | Drei unabhängige Rayleigh-R-Quellen: Binance `!forceOrder`, Aave V3 `LiquidationCall`, Uniswap V3 Swaps; BTC-Difficulty-Phase `(height % 2016)/2016` | Passt zu Fenster W / Stufe 3 (echte Edges, keine simulierten Liquidationen). |
| `PROJEKT_LOG.md` (30.07.) | 5 PhaseSources (`swe:sun/moon`, `eth:slot`, `perp:funding_8h`); PLV vs. Surrogat-Δ; Class-C Rayleigh | Direkte Vorarbeit für `ASTROCORE_PHASE_SOURCES` nach Fenster W. Host-Adapter `news_sentiment` / `price_gap` sind die lokalen Fortsetzungen. |
| `CLAUDE.md` Trading-Domäne | Agenten 20–28, Ollama, `:Coin`/`:PriceMove`/`:News` ohne Relationships | Warnung: Property-Match statt Graph-Kanten — nicht ins aktuelle Schema zurückkopieren. |

### Risiko & Risk-Gates

| Quelle | Gate / Invariante | Für Agent-X |
|--------|-------------------|-------------|
| `START_HIER.md` | CircuitBreaker **−8 % Drawdown** → `:KillswitchEvent` | Analog Wave-8 CircuitBreaker / Paper-Hold — Schwelle nicht nachjustieren ohne Pre-Reg. |
| `PROJEKT_LOG.md` | **DEFENSIVE_LIMIT:** Funding-Phase im Risk-Window (`t mod 8h ≈ 0`) **und** signifikante Kopplung → doppelte Slice-Anzahl, **keine** Direct-Market-Orders | Nach Fenster W als Execution-Guard, nicht vorher in den Cluster-Hook. |
| `CLAUDE.md` | `cost_guard` Tagesbudget $2; `/admin_shutdown` Killswitch; Guardian 6 Checks | Ops-Muster (Budget, Admin-Kill, Health-Takt). Discord/Telegram **nicht** verdrahten (News-Agent bewusst isoliert). |
| `CLAUDE.md` RAG | 4-Layer State: Neo4j-Fakten → Sub-Agent-Berechnung → LLM-Interpretation (nie rekursiv) → Antwort mit Provenance | Entspricht Wave-38/39: LLM sieht keine Roh-Mutation; Gatekeeper vor Execution. |
| `TIEFENANALYSE_THIXONAUT_CORE.md` | Wortgrenze `_L`: `astro` ≠ Gastronomie; trailing `\b` verschluckt deutsche Flexion | Bereits im News-Agent (`\beth\b`). Gleiche Regel für Ticker/Cashtags. |
| `CLAUDE2.md` | Mono-Verlust ≤ −1 dB; Hadamard(s,s) verboten | Audio-Invariante, **kein** Trading-Reuse. Muster: „identische Inputs = Nullung“ analog Conservation/BHO. |

### Agenten-Orchestrierung

| Quelle | Mechanik | Für Agent-X |
|--------|----------|-------------|
| `CLAUDE.md` Supervisor | Keyword (268, 0 ms) → Domain; LLM-Fallback nur bei Unsicherheit; MUSIC/RAG **nicht** keyword-geroutet | Host-Crons analog: Marker-Identität, kein `grep` auf Modulnamen. Cluster-Cron `:14` bleibt unberührt. |
| `README.md` / `CLAUDE.md` KM | MetaOrchestrator Agent 99; 12–13 Regex-Intents; Delegation an 19 Spezialisten; **BaseAgent:** observe → act → execute → learn | Intent-Routing ohne LLM für Ops/Query. Nicht DeepSeek in die Stufe-2-Satelliten. |
| `AGENT_0_3_TEMPLATE_v3.md` | Handoff: Agent 0 liefert Instrument (fix), Agent 3 darf nur Einsatz/Register ändern; Pflicht-Abgrenzung gegen Vorgänger; Frozen Constants | **Vertrag**, nicht der Musik-Inhalt. Code: `astrocore/sources/handoff.py` — `order_send_forbidden` bei Write-Back auf Detector-JSONL; Ziel nur unter `phase_signals/`. Cluster liest erst nach Fenster W. |
| `PROJEKT_LOG.md` | Intent #13 `COUPLING_ANALYSIS` → CouplingAnalyst via Tool-Registry; Fallback: Liste der PhaseSources | Nach Registration: `news_sentiment` + `price_gap` als Quellen listen, nicht still ignorieren. |

### Hilfskripte & Dokumentation

| Datei | Zweck | Agent-X |
|-------|-------|---------|
| `PROJEKT_UEBERBLICK.md` | QualityAgent-Dump (1597 Projekte, 68 % Reifegrad D) | Kein Prompt. Zeigt, dass Auto-Inventar ohne Filter Lärm ist. |
| `barry_adamson_noir/noir_mix_LOG.md` | Mix-Session, MD5, Crest | Audio. |
| `pysynth/proofs/cs80/verification_log.md` | Smallest-proof (Determinismus, Peak, Klicks) | Muster „erst isoliert verifizieren, dann einbinden“ — analog Fixture-Tests vor Cron. |
| Drittanbieter-READMEs | DiffSinger / AKWF / VSCO2 | Kein Agent-X-Bezug. |

---

## 3. Haupt-Templates (Steckbriefe)

### `CLAUDE.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | Verbindlicher System-Prompt für die 16-Domänen-Plattform (LangGraph + Mercury extern). |
| **KI-Rolle** | Supervisor/Router: Keyword zuerst, LLM nur Fallback; DEKRA lokal (DSGVO); Trading/Eurorack/Web/… als getrennte Subgraphen. |
| **Anwendungsfall Agent-X** | Ops-Vertrag: ein Config-Punkt, Graceful Degradation, Provenance-Schichten, Health-Guardian. **Nicht** übernehmen: DeepSeek in News, Discord-Alarm als Default, Property-Match-Trading-Schema. |

### `CLAUDE2.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | Mix-Assistent (Agent 1) + Output-Konvention; Original-`CLAUDE.md` bleibt unangetastet. |
| **KI-Rolle** | „Du mixst, du masterst nicht.“ Peak −5 dBFS, kein Limiter; gelernte Bug-Muster als harte Regeln. |
| **Anwendungsfall Agent-X** | Nur das **Invarianten-Muster** (additive Datei statt die Plattform-CLAUDE zu überschreiben). Inhaltlich Audio — kein Trading. |

### `AGENT_0_3_TEMPLATE_v3.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | Verhindert klangliche/strukturelle Identität aufeinanderfolgender Stücke. |
| **KI-Rolle** | Agent 0 = Instrument Builder (neues Syntheseprinzip, deterministic, smallest-proof). Agent 3 = Composer (6 Parameter **vor** MIDI; Frozen Constants; Differenzierungs-Statement Pflicht). |
| **Anwendungsfall Agent-X** | Handoff-Protokoll: Detector (`:05`) schreibt `gap_reports.jsonl`, PhaseSource (`:07`) liest nur; Skalen 10/16 eingefroren. Pflicht-Abgrenzung = keine zweite PhaseSource mit gleichem Marker-Prefix. |

### `START_HIER.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | Ein-Seiten-Runbook: Pfade, CLI, Daemons, Neo4j-Labels, 14 Bugfixes. |
| **KI-Rolle** | Operator, kein LLM-System-Prompt. |
| **Anwendungsfall Agent-X** | Vorlage für Host-Cron-Übersicht (Minute / Marker / JSONL). Killswitch −8 %, Fake-Signal-Guard, Sentiment P30D als dokumentierte Schwellen. |

### `README.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | 20-Agenten-Schwarm, 4 Ebenen, Design-Entscheidungen. |
| **KI-Rolle** | Architektur-Kontext für MetaOrchestrator. |
| **Anwendungsfall Agent-X** | observe→act→execute→learn als gemeinsame Agent-Schale; Regex-Intents statt LLM-Router für Satelliten. |

### `PROJEKT_LOG.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | Session-Chronik (Liquidation-Pipeline, AstroCore, MetaOrchestrator). |
| **KI-Rolle** | Spezifikation in Prosa (Agent B1/A1, CouplingAnalyst 20, ExecutionEngine). |
| **Anwendungsfall Agent-X** | Primärquelle für PhaseSource-Klassen, Surrogat-Reporting (Roh-PLV vs. Δ), DEFENSIVE_LIMIT. Backtest-Lektion: simulierte Liquidationen haben keinen Edge. |

### `TIEFENANALYSE_THIXONAUT_CORE.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | Revision-2-Audit: Zahlen korrigieren, Symbolics-False-Positives, ehrliches Erledigt/Offen. |
| **KI-Rolle** | Auditor: Messung vor Behauptung; `os.walk` vs. `find`; Wortgrenzen. |
| **Anwendungsfall Agent-X** | Anti-HARKing / Probe-Regeln. Word-bound bereits im News-Agent. Symbolics-Zähler-Fix (`nodes_created` statt `if result`) analog Liveness-Marker ≠ leere Trefferliste. |

### `PROJEKT_UEBERBLICK.md`

| Feld | Inhalt |
|-------|--------|
| **Zweck** | QualityAgent-Output, kein System-Prompt. |
| **KI-Rolle** | — |
| **Anwendungsfall Agent-X** | Negativbeispiel: Inventar ohne Ausschluss von `site-packages` / Cache. |

---

## 4. Was Agent-X **nicht** aus choral_text ziehen sollte

- Musik-Prompts (`AGENT_0_3`, `CLAUDE2`, Mix-Logs) als Trading-Logik.
- DeepSeek / Discord / Telegram als Default für Stufe-2-Satelliten.
- Trading-Neo4j ohne Relationships (`n.coin = c.symbol`).
- Cluster-Registration der PhaseSources vor Abschluss von Fenster W (50–70 Edges).
- Marker-Namen, die einander als Prefix enthalten (`# AGENTX_PRICE_GAP` vs. hypothetisches `# AGENTX_PRICE_GAP_PHASE` — deshalb `# AGENTX_GAP_PHASE`).

---

## 5. Direkt wiederverwendbare Prompts (Priorität)

Siehe Chat-Zusammenfassung: fünf Verträge, die sich 1:1 in Agent-X-Regeln übersetzen, ohne den Cluster zu patchen.
