# CherryStudio-Import — Inventar

- **Root:** `imports/cherrystudio/`
- **Dateien:** 24,156
- **Volumen:** 461.8MiB (484,269,867 Bytes)
- **Markdown:** 173 Dateien / 25,852 Zeilen
- **Python:** 21,803 Dateien / 9,799,539 Zeilen
- **Davon ohne `.venv`:** Markdown 94 / 16,511 Zeilen · Python 483 / 104,931 Zeilen
  (`choral_text/.venv` ist ein mitimportiertes virtuelles Environment und verzerrt die Rohzahlen.)

## Top-Level-Ordner

| Ordner | Dateien | Größe |
|--------|---------|-------|
| `choral_text` | 22,825 | 459.3MiB |
| `agent_vault` | 1,011 | 666.1KiB |
| `audio_output` | 195 | 329.9KiB |
| `craft-procurement-engine` | 79 | 1.2MiB |
| `astrocore` | 30 | 171.8KiB |
| `.` | 15 | 240.8KiB |
| `memory` | 1 | 511B |

## Dateitypen (Top 20)

| Ext | Anzahl |
|-----|--------|
| `py` | 21,803 |
| `json` | 1,313 |
| `txt` | 419 |
| `js` | 386 |
| `md` | 173 |
| `toml` | 24 |
| `yaml` | 19 |
| `yml` | 7 |
| `sh` | 6 |
| `pyc` | 5 |
| `ts` | 1 |

## Fokus-Ordner

- `astrocore/`: vorhanden — 30 Dateien, 171.8KiB
- `craft-procurement-engine/`: vorhanden — 79 Dateien, 1.2MiB
- `choral_text/`: vorhanden — 22,825 Dateien, 459.3MiB
- `agent_vault/`: vorhanden — 1,011 Dateien, 666.1KiB
- `.claude/`: vorhanden — 0 Dateien, 0B

## Größte Markdown-Dateien

- `choral_text/diffsinger_onnx_proof/DiffSinger/docs/ConfigurationSchemas.md` — 2,274 Zeilen
- `choral_text/diffsinger_pytorch/docs/ConfigurationSchemas.md` — 2,274 Zeilen
- `choral_text/PROJEKT_LOG.md` — 1,384 Zeilen
- `choral_text/diffsinger_onnx_proof/DiffSinger/docs/BestPractices.md` — 651 Zeilen
- `choral_text/diffsinger_pytorch/docs/BestPractices.md` — 651 Zeilen
- `audio_output/claude_md/CLAUDE.md` — 645 Zeilen
- `choral_text/CLAUDE.md` — 611 Zeilen
- `choral_text/.venv/lib/python3.14/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/theme.md` — 437 Zeilen
- `choral_text/TIEFENANALYSE_THIXONAUT_CORE.md` — 357 Zeilen
- `choral_text/.venv/lib/python3.14/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/performance.md` — 356 Zeilen
- `choral_text/.venv/lib/python3.14/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/server-asgi.md` — 349 Zeilen
- `choral_text/.venv/lib/python3.14/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/best-practices.md` — 339 Zeilen
- `craft-procurement-engine/CLAUDE.md` — 319 Zeilen
- `choral_text/.venv/lib/python3.14/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/data-display.md` — 297 Zeilen
- `audio_output/claude_md/CLAUDE2.md` — 293 Zeilen

## Größte Python-Dateien (ohne `.venv`)

- `craft-procurement-engine/test_smoke.py` — 1,812 Zeilen
- `choral_text/trading.py` — 1,730 Zeilen
- `choral_text/choral_text_agent.py` — 1,329 Zeilen
- `craft-procurement-engine/core/consensus.py` — 1,173 Zeilen
- `choral_text/agents/meta_orchestrator.py` — 1,070 Zeilen
- `craft-procurement-engine/api/main.py` — 1,023 Zeilen

Die Rohliste `CHERRYSTUDIO_PY_LINES.txt` enthält zusätzlich das `.venv` (Kubernetes/Torch/Plotly-Generates).

## Abschluss Stufe 2 (2026-08-30)

Inventar geschlossen: Agenten kategorisiert, Liquidations-Pipeline mit Hook abgeglichen (Spec §11), Craft-Konsens als Referenz. Cluster-Quelle bleibt `worm`.

### `choral_text/agents/` — 30 Module (+ `__init__`)

| Datei | Funktion | Agent X |
|-------|----------|---------|
| `coupling_analyst.py` | Class A/B PLV + Class C Rayleigh, `:CouplingResult` | **übernommen** (Hook/AstroCore) |
| `symbolics_agent.py` | PhaseSources, `analyze_class_c_coupling` | **Referenz** — Logik im Hook, nicht den Neo4j-Writer |
| `feed_health_agent.py` | Silence/Rate auf Neo4j-Feeds (`:FeedHealth`) | **Pattern** — Cron prüft WORM/W_xv, nicht diese Feeds |
| `event_normalizer.py` | Einheitliches Lending-Event-Schema | **Referenz** für künftige Aave-Events |
| `execution_agent.py` | Funding-Phase Risk Guard (`t mod 8h`) | **Referenz** — nicht in den Daemon verdrahten |
| `pool_state_agent.py` | Aave/DEX Pool-Zustand in Neo4j | später, wenn On-Chain-Feed existiert |
| `health_factor_agent.py` | Aave V3 Health Factor | DeFi-Risiko, nicht B2G |
| `price_impulse_agent.py` | Uniswap-Swap Impuls | später (`:SwapEvent`, nicht Hook-Class-C) |
| `flash_loan_analyst.py` | Flash-Loan-Klassifikation | DeFi |
| `strategy_signal_agent.py` | Signale aus Analysen | Trading — nicht RaaS |
| `circuit_breaker.py` | Drawdown-Killswitch | Wave-24 hat eigenen Breaker |
| `mev_guard.py` | Jito/Sandwich | Wave-24 MEV |
| `risk_parity.py` | ATR-Allokation | Trading |
| `yield_harvester.py` | Kamino USDC | Trading |
| `accounting.py` | Paper-Ledger | BHO/GoBD in B2G bereits eigener Stack |
| `solana_executor.py` | Vault-TXs localnet | nicht |
| `sentiment_agent.py` | Sentiment Fast-Trigger | nicht |
| `orchestrator_agent.py` / `meta_orchestrator.py` | Pipeline-Dirigent / Intent-Router | Wave-7/31 decken das |
| `meta_learner.py` | Graph-Mining, HP-Tuning | nicht Stufe 2 |
| `memory_agent.py` | Vektor-Gedächtnis | nicht |
| `knowledge_organizer.py` | Persönlicher Wissensgraph | nicht |
| `codebase_agent.py` | Code-Index Neo4j | nicht |
| `quality_agent.py` | Projekt-Reifegrad | nicht |
| `backup_agent.py` / `health_agent.py` | Volume-Backup / Disk | Wave-7 Backup/Health |
| `deployment_agent.py` / `documentation_agent.py` | venv-Katalog / READMEs | nicht |
| `education_agent.py` / `media_agent.py` | Lernmaterial / Audio-Katalog | Audio — irrelevant |

**Übernahme jetzt:** keiner dieser Agenten als Pod-Sidecar. Nutzbar sind Schema + Statistik (`coupling_analyst`, Listener, Dual-Schema). Aave/DEX-Listener-Dateien sind **nicht** im Import (Log zeigt LangGraph-Pfade).

### `PROJEKT_LOG.md` → Spec

Relevante Pipeline steht in `docs/ASTROCORE_INTEGRATION_HOOK_SPEC.md` §11. `.env` aus dem Log **nicht** übernehmen (Infura-Key im Klartext — rotieren, nicht zitieren).

### `craft-procurement-engine/core/consensus.py`

**Referenz, kein Merge.** 4 Validatoren / 3/4-Schwelle (GoBD, Fraud/Benford, Plausibility, Geofence+IoT) — dieselbe Idee wie CLAUDE.md Agent-X-Core, in B2G aber verteilt (`gobd_integrity_checker.py`, `price_plausibility_analyzer.py`, PoPW/Geofence). Craft hat keinen GAEB-Parser. Tests: `test_pipeline_simulation.py`. Bei Bedarf Wrapper, nicht Datei-Kopie.

### Nicht-Audio-Prompts

Kein zweites Agent-Template in `agents/`. Nicht-Audio-Markdown (ohne DiffSinger/venv): `AGENT_0_3_TEMPLATE_v3.md` (Audio), `PROJEKT_LOG.md`, `CLAUDE.md`/`CLAUDE2.md`, `PHASENKOPPLUNG.md`, `SYMBOLKARTE.md`, `TIEFENANALYSE_THIXONAUT_CORE.md`, Craft-ADR. Mix-Logs unter `audio_output/` bleiben irrelevant.

## Rohlisten

- `docs/CHERRYSTUDIO_FILE_TYPES.txt`
- `docs/CHERRYSTUDIO_FILES_WITH_SIZES.txt`
- `docs/CHERRYSTUDIO_MD_LINES.txt`
- `docs/CHERRYSTUDIO_PY_LINES.txt`
