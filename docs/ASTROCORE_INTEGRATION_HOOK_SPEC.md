# AstroCore Integration Hook — Read-Only Spec

**Status:** **Approved v0.3** (2026-08-30) — Dual-Schema-Adapter (`ts`/`phase` + `timestamp`/`funding_phase`)  
**Scope:** CherryStudio-Import → Agent X RaaS/Wirtschaft, **ohne Cluster- oder Neo4j-Mutation**  
**Quellen:** `imports/cherrystudio/astrocore/`, `astrocore/emergence_evaluator.py`, `agents_b2g/wirtschaft/emergence_adapter.py`

---

## Approved Decisions (ADR)

Architekturentscheidungen — vor P1 implementiert, gemeinsam abgestimmt:

| # | Thema | Entscheidung | Begründung |
|---|--------|--------------|------------|
| **D1** | Liquidations-Feed fehlt | **Fallback mit Warnung**, kein Hard-Fail | Hook liefert immer ein Envelope; `data_provenance: "synthetic"` + `warnings[]` wenn Neo4j leer/unreachable und kein WORM-Feed. Quelle: `generate_synthetic_liquidations()` aus `test_liquidation_coupling.py`. Hart abbrechen nur bei `--strict` (CI). **`--strict` verlangt beides:** echte Events im Lookback **und** `NEO4J_USER_READ` (least-privilege Login). Ohne Reader-User ist `--strict` kein Produktions-Tor. **Verdict-Cap (D1b):** `cap_verdict_for_provenance()` — synthetische Inputs dürfen **niemals** `CLUSTER_DETECTED`/`COUPLED`/`CONFIRMED`/`SIGNIFIKANT`/`EMERGENCE_PASSED` tragen; höchstens `SYNTHETIC_ONLY`. Positive Statistik ohne Live-Daten ist wirkungslos, nicht nur dokumentiert. |
| **D2** | Neo4j Query-Performance | **Pflicht-Zeitfenster + LIMIT**, kein Vollscan | Default `lookback_days=7` (`ASTROCORE_NEO4J_LOOKBACK_DAYS`). Jede Liquidations-/Gas-Query: `WHERE coalesce(timestamp, ts) >= $since_ts` **und** `LIMIT $limit` (default 10_000). Preflight-Aggregat ebenfalls zeitgebunden. Unbounded `MATCH` ist **verboten**. |
| **D3** | Funding-Period (`perp:funding_8h`) | **Hardcoded 28800 s + Override**, PhaseSource-Lookup später | Default `FUNDING_PERIOD_S=28800.0` in Hook-Config. Override via Env `ASTROCORE_FUNDING_PERIOD_S` oder CLI `--funding-period-s`. Auslesen aus `:PhaseSource.period_sec` erst **P4+**, wenn Live-Feed die Periode bestätigt. |
| **D4** | Dual-Schema LiquidationEvent | **Query-Adapter, kein Listener-Patch** | CherryStudio-Listener schreibt `ts`/`phase`/`usd_value`; AstroCore-Seed schreibt `timestamp`/`funding_phase`/`amount_usd`. Hook liest beide via `coalesce` + `normalize_liquidation_record()`. Kanonisch für Analyse: `ts`, `phase`, `amount_usd`. `is_clustered` fehlt → `False`. `None`-Check (nicht `or`), damit `ts=0.0` erhalten bleibt. |

---

## 1. Ziele & harte Grenzen

| Erlaubt | Verboten |
|---------|----------|
| Read-only Neo4j (`MATCH`/`RETURN`/`OPTIONAL MATCH`) | `CREATE`, `MERGE`, `SET`, `DELETE`, `DETACH DELETE` |
| JSONL/WORM/Pod-Log lesen (kubectl exec, lokaler Mirror) | Seed-Skripte gegen Live-DB (`seed_*.py`, `astrocore_setup.py` ohne `--check`) |
| `astrocore_coupling.coupling_analysis()` rein in-memory | Schreiben nach `output/` im Produktions-Pfad ohne Opt-in |
| `test_liquidation_coupling.analyze_liquidation_events()` auf Arrays | Paper-Runner / Helm / ConfigMap ändern |
| Hook-Ausgabe als JSON an stdout / EventBus / WORM-Audit | Kuramoto-Output → Trading-Entscheidung ohne Wave-39-Gate |

**Cluster-Stand 2026-08-30:** W_xv + Feed-Gap Writer leben (2. Heartbeat 07:14:05Z). Integration darf diesen Lauf **nicht** unterbrechen.

---

## 2. Schreib-Audit (Import-Ordner)

Explizite Mutationen — **nicht** im Hook-Pfad ausführen:

| Skript | Schreibt nach | Operationen |
|--------|---------------|-------------|
| `seed_liquidations.py` | Neo4j | `CREATE INDEX`, `DETACH DELETE`, `CREATE (:LiquidationEvent)` |
| `seed_gas_prices.py` | Neo4j | `CREATE INDEX`, `DETACH DELETE`, `CREATE (:GasPriceEvent)` |
| `astrocore_setup.py` | Neo4j | Constraints, `MERGE (:AstroProject)`, `MERGE (:PhaseSource)` |
| `test_liquidation_coupling.py` | Lokal | Nur `output/liquidation_coupling_demo.json` (synthetische Demo) |
| `astrocore_coupling.py` | Lokal | Optional `output/coupling_*.json` via CLI `-o` |
| `astrocore_sun.py` | Lokal | JSON-Positionsdatei |

**Sicher read-only:**

- `test_liquidation_coupling.py` — Kernfunktion `analyze_liquidation_events(event_timestamps)` hat **keine** DB/I/O-Abhängigkeit.
- `astrocore_coupling.py` — `coupling_analysis()`, `sample_phases()`, `plv_n()`, `rayleigh_p()`.
- `seed_liquidations.py --check` / `astrocore_setup.py --check` — nur `MATCH`/`count`.

---

## 3. Neo4j — Read-Only Queries

> **Schema-Korrektur:** Es gibt **kein** `(:Liquidation)-[:AT]->(:Slot)`. Seeds nutzen flache Event-Knoten mit vorab berechneter Phase.

### 3.1 LiquidationEvents (Class C auf `perp:funding_8h`)

> **D2:** `$since_ts` ist **Pflicht** (Default: now − 7 Tage). `$limit` Default 10_000. Reader wirft `ValueError`, wenn `since_ts` fehlt oder `lookback_days > 90` ohne explizites Opt-in.
>
> **D4:** Zwei Property-Sätze. CherryStudio-Listener (`liquidation_listener.py`): `ts`, `phase`, `usd_value`, Index auf `l.ts`. AstroCore-Seed (`seed_liquidations.py`): `timestamp`, `funding_phase`, `amount_usd`, Index auf `l.timestamp`. Der Hook patched den Listener **nicht**.

```cypher
// LiquidationReader — zeitgebunden, capped (D2), dual-schema (D4)
MATCH (l:LiquidationEvent)
WHERE coalesce(l.timestamp, l.ts) >= $since_ts
RETURN l.timestamp AS timestamp,
       l.ts AS ts,
       l.funding_phase AS funding_phase,
       l.phase AS phase,
       l.amount_usd AS amount_usd,
       l.usd_value AS usd_value,
       l.symbol AS symbol,
       l.is_clustered AS is_clustered
ORDER BY coalesce(l.timestamp, l.ts) ASC
LIMIT $limit
```

```cypher
// Preflight-Aggregat — gleiches Zeitfenster (D2), dual-schema (D4)
MATCH (l:LiquidationEvent)
WHERE coalesce(l.timestamp, l.ts) >= $since_ts
RETURN count(l) AS n,
       min(coalesce(l.timestamp, l.ts)) AS ts_min,
       max(coalesce(l.timestamp, l.ts)) AS ts_max
```

Python-Normalisierung (`normalize_liquidation_record`): kanonisch `ts` (= `coalesce(timestamp, ts)`), `phase` (= `coalesce(funding_phase, phase)`), `amount_usd` (= `coalesce(amount_usd, usd_value)`), `is_clustered` default `False`. Records ohne Zeitstempel werden verworfen. `fetch_liquidation_timestamps()` liest das kanonische Feld `ts`.

### 3.2 GasPriceEvents (Class C auf `eth:slot_in_epoch`)

```cypher
MATCH (g:GasPriceEvent)
WHERE g.block_number >= $block_from
RETURN g.block_number AS block,
       g.slot_phase AS phase,
       g.base_fee_gwei AS base_fee_gwei,
       g.is_epoch_boundary AS is_epoch_boundary
ORDER BY g.block_number ASC
LIMIT $limit
```

### 3.3 PhaseSources (Metadaten, read-only)

```cypher
MATCH (p:AstroProject {name: 'AstroCore'})-[:HAS_SOURCE]->(q:PhaseSource)
RETURN q.id AS id, q.name AS name, q.source_class AS source_class,
       q.period_sec AS period_sec
ORDER BY q.id
```

### 3.4 Driver-Wrapper (Python, read-only)

Implementiert in `agents_b2g/astrocore_hook/neo4j_reader.py` (nicht mehr geplant):

```python
# Dual-schema Cypher: siehe §3.1 (LIQUIDATION_QUERY / LIQUIDATION_AGGREGATE_QUERY)

def fetch_liquidation_timestamps(driver, since_ts: float, limit: int = 10_000) -> list[float]:
    if since_ts is None:
        raise ValueError("since_ts required (D2: no unbounded scan)")
    rows = fetch_liquidation_events(driver, since_ts=since_ts, limit=limit)
    return [row["ts"] for row in rows]  # canonical after normalize_liquidation_record()
```

Tests: `scripts/test_astrocore_neo4j_reader.py` (Cherry-Schema, Seed-Schema, `ts=0.0`, Read-Only-Gate).

Neo4j 5.x: **zwei Schichten** — (1) Client-Regex `assert_read_only_cypher` (frühe, klare Fehlermeldung); (2) **serverseitig** `session(default_access_mode=READ_ACCESS)` + `execute_read`, und vor P4 ein eigener Benutzer mit Rolle `reader` (`NEO4J_USER_READ` / `NEO4J_URI_READ`). Die Zusicherung darf nicht davon abhängen, dass jede Query durch die Sperrliste läuft.

**Index-Voraussetzung:** `:LiquidationEvent(timestamp)` **oder** `:LiquidationEvent(ts)` — je nach Writer. Seed legt `timestamp` an; Listener legt `ts` an. Production sollte beide haben, solange Dual-Schema gilt. Bei `n=0` im Fenster → D1-Fallback.

---

## 4. PhaseSource → RaaS Data-Stream Mapping

| PhaseSource ID | Klasse | RaaS / Live-Quelle (read-only) | Phase-Berechnung |
|----------------|--------|--------------------------------|------------------|
| `swe:sun` | A (Ephemeris) | Kein RaaS-Stream — `swisseph` lokal | `astrocore_coupling._phase_source_sun` |
| `swe:moon` | A | Wie oben | `_phase_source_moon` |
| `eth:slot_in_epoch` | A | Optional: ETH RPC `eth_blockNumber` (read) oder Paper-`cross_venue_slots.jsonl` Slot-Grenzen | `(slot mod 32) / 32` |
| `perp:funding_8h` | A | ETHUSDT Perp Funding-Zeiten (Exchange-API / WORM-Metadaten) — **noch nicht im Paper-WORM** | `(t mod P) / P` mit **P=28800 s (D3)**, Override via Env/CLI |
| `test:coupled_to_sun` | Synthetic | Nur Offline-Validierung | — |
| `test:sine_a` / `test:sine_b` | Synthetic | Unit-Tests / CI | — |

### 4.1 Bereits verfügbare RaaS-Streams (Cluster, read-only)

| Pfad (Pod) | Nutzen für AstroCore |
|------------|----------------------|
| `/data/audit/cross_venue_gaps.jsonl` | Observer-Liveness (W_xv), **nicht** Class-C-Events |
| `/data/audit/cross_venue_slots.jsonl` | Slot-Zeitraster (`slot_start_ts`, `slot_s`) → Carrier für Timing-Analysen |
| `/data/audit/feed_gaps.jsonl` | Feed-Integrität (W), `tick_spacing`/`socket` als Punktprozess-Kandidaten |
| `/data/worm/.../paper_trades.worm.jsonl` | Trade-/Signal-Zeitstempel → Class-C-Events (Preis-/Signal-Cluster) |

**Gap (D1):** Echte Liquidations-Feeds sind im RaaS-Paper-Stack **noch nicht** verdrahtet. Ingest-Reihenfolge:

1. Neo4j READ (zeitgebunden, D2) — wenn `n ≥ 50` Events im Fenster  
2. WORM/RaaS-Export (Phase P2) — wenn vorhanden  
3. **Fallback:** `generate_synthetic_liquidations()` — immer verfügbar, Envelope trägt `data_provenance: "synthetic"` und Warning `"liquidation_feed_missing_using_synthetic"`

Hard-Fail (`verdict: UNAVAILABLE`) nur mit `--strict` (Tests/CI ohne Mock).

---

## 5. Hook-Architektur

```
┌─────────────────────┐     read-only      ┌──────────────────────────┐
│ RaaS WORM / Audit   │ ─────────────────► │ astrocore_hook/ingest    │
│ Neo4j (READ sess.)  │ ─────────────────► │  → event_timestamps[]    │
└─────────────────────┘                    └────────────┬─────────────┘
                                                        │
                        ┌───────────────────────────────┼───────────────────────────────┐
                        ▼                               ▼                               ▼
              analyze_liquidation_events()    coupling_analysis()              KuramotoEvaluator
              (Class C, funding carrier)      (Class A ↔ A, PLV/R)            (Wirtschaft logs)
                        │                               │                               │
                        └───────────────────────────────┴───────────────────────────────┘
                                                        ▼
                                              AstroCoreHookEnvelope (JSON)
                                                        │
                        ┌───────────────────────────────┴───────────────────────────────┐
                        ▼                                                               ▼
              EventBus / WORM audit (diagnostic_only)                    wirtschaft/emergence_adapter
              (kein order_send)                                          (bestehendes Muster)
```

### 5.1 Modul-Vorschlag (noch nicht implementiert)

```
agents_b2g/astrocore_hook/
  __init__.py
  neo4j_reader.py      # READ-only Cypher
  raas_ingest.py       # JSONL tail / kubectl mirror
  class_c.py           # Wrapper um analyze_liquidation_events
  class_a_coupling.py  # Wrapper um coupling_analysis
  envelope.py          # AstroCoreHookEnvelope pydantic/dataclass
  runner.py            # CLI: python -m agents_b2g.astrocore_hook.runner --mode class_c|coupling
```

Import-Pfad: CherryStudio-Logik **portieren oder symlinken** nach `astrocore/` (bereits vorhanden: `emergence_evaluator.py`). `astrocore_coupling.py` aus Import in Repo übernehmen, wenn `coupling_analysis` produktiv genutzt wird.

---

## 6. JSON-Interface — `AstroCoreHookEnvelope`

Einheitliches Ausgabeformat für Agent X / EventBus / RAG — analog RaaS `diagnostic_only: true`.

```json
{
  "schema": "astrocore_hook_envelope/v1",
  "generated_at": "2026-08-30T07:20:00+00:00",
  "mode": "class_c_liquidation_funding",
  "read_only": true,
  "live_execution": false,
  "order_send": false,
  "not_investment_advice": true,
  "diagnostic_only": true,
  "data_provenance": "neo4j | worm | synthetic",
  "warnings": ["liquidation_feed_missing_using_synthetic"],
  "inputs": {
    "carrier_source": "perp:funding_8h",
    "funding_period_s": 28800.0,
    "event_source": "neo4j:LiquidationEvent",
    "n_events": 1000,
    "since_ts": 1710000000.0,
    "lookback_days": 7
  },
  "metrics": {
    "rayleigh": {"R": 0.042, "p": 0.003, "significant_at_001": true},
    "surrogate_test": {"p_surrogate": 0.012, "significant_at_005": true},
    "phase_histogram": {"peak_phase": 0.03, "peak_hour": 0.2}
  },
  "verdict": "CLUSTER_DETECTED | UNIFORM | INSUFFICIENT_N",
  "interpretation": "…"
}
```

### 6.1 Modus `coupling_a_a` (zwei PhaseSources)

```json
{
  "mode": "coupling_a_a",
  "inputs": {
    "source_a": "swe:sun",
    "source_b": "eth:slot_in_epoch",
    "days": 90,
    "interval_minutes": 60
  },
  "metrics": {
    "resultant_vector": {"R": 0.15, "mean_diff_deg": 42.0},
    "rayleigh": {"p": 0.02},
    "plv_by_harmonic": {"n=1": {"plv": 0.31, "aspect": "Konjunktion (0°)"}},
    "surrogate_test": {"p_surrogate": 0.04, "significant_at_005": true}
  },
  "verdict": "COUPLED | NO_COUPLING | UNVERIFIED"
}
```

### 6.2 Modus `kuramoto_wirtschaft` (bestehend)

Nutzt unverändert `EmergenceResult` aus `agents_b2g/wirtschaft/emergence_adapter.py`:

```python
@dataclass
class EmergenceResult:
    mean_r: float
    p_value: float
    status: str       # EMERGENCE_PASSED | EMERGENCE_FAILED
    verdict: str      # COUPLED | NO_COUPLING
```

Hook mappt `EmergenceResult` → `AstroCoreHookEnvelope` mit `"mode": "kuramoto_wirtschaft"`.

---

## 7. Verdict-Logik (normiert)

| Modus | `COUPLED` / positiv | `NO_COUPLING` / negativ | Blockiert |
|-------|---------------------|-------------------------|-----------|
| Class C (Liquidation) | `ray_p < 0.01` **und** `p_surrogate < 0.05` | sonst | `n_events < 50` → `INSUFFICIENT_N`; **`data_provenance=synthetic` → max `SYNTHETIC_ONLY` (D1b)** |
| Class A↔A (PLV) | `p_surrogate < 0.05` (n=1) | sonst | unbekannte Source-ID → `UNVERIFIED` |
| Kuramoto (Wirtschaft) | `EMERGENCE_PASSED` (p < 0.01) | `NO_COUPLING` | leere Logs → Error, kein Verdict |

**Kein automatisches Trading:** Verdict ist diagnostisch. Wave-39 Ethical Boundary + Wave-40 Fiscal Gate bleiben vorgeschaltet.

---

## 8. Implementierungs-Phasen

| Phase | Lieferung | Cluster-Impact |
|-------|-----------|----------------|
| **P0** (dieses Dokument) | Spec + Schreib-Audit | Keiner |
| **P1** | `neo4j_reader.py` (D2: Pflicht-`since_ts`, D1: synthetic fallback in `class_c.py` Stub) + Mock-Test | Keiner (READ session) |
| **P2** | `AstrocoreHookClient` + `emergence_adapter` opt-in | `use_astrocore_hook` / `ASTROCORE_HOOK_ENABLED=false` (default) | Keiner |
| **P3** | `class_c.py` — Timestamps aus P1/P2 → `analyze_liquidation_events` | Keiner |
| **P4** | `class_a_coupling.py` — `coupling_analysis` offline | Keiner |
| **P5** | EventBus-Hook + WORM append (`diagnostic_only`) | Optionaler Sidecar, kein Runner-Patch |
| **P6** | Bridge zu `wirtschaft/` Dashboard / UX Wave-31 | Read-only Anzeige |

**Explizit zurückgestellt:** Neo4j-Seeds, `astrocore_setup.py` ohne `--check`, Kuramoto → Position Sizing.

---

## 9. Preflight-Checkliste (vor erstem Hook-Lauf)

```bash
# 1. Kein Seed auf Live-DB
grep -l 'CREATE\|MERGE\|DELETE' imports/cherrystudio/astrocore/seed_*.py

# 2. Neo4j nur lesen
python3 imports/cherrystudio/astrocore/seed_liquidations.py --check
python3 imports/cherrystudio/astrocore/astrocore_setup.py --check

# 3. Class C offline (synthetisch, zero DB)
python3 imports/cherrystudio/astrocore/test_liquidation_coupling.py

# 4. Class A offline (braucht swisseph)
python3 imports/cherrystudio/astrocore/astrocore_coupling.py swe:sun test:sine_b --days 7 --no-surrogates

# 5. Wirtschaft Kuramoto (bestehend, in-memory)
python3 -m agents_b2g.wirtschaft.emergence_adapter
```

---

## 10. Bezug zu CherryStudio-Import

| Import-Datei | Hook-Rolle |
|--------------|------------|
| `astrocore_coupling.py` | Class A↔A Engine — **Port-Ziel** `astrocore/coupling.py` |
| `test_liquidation_coupling.py` | Class C API — direkt wrapbar |
| `PHASENKOPPLUNG.md` | Domänen-Spec (Klasse A/B/C) |
| `SYMBOLKARTE.md` | PhaseSource-IDs ↔ Neo4j |
| `choral_text/PROJEKT_LOG.md` | Pipeline-Referenz (unten §11) — **kein** Secret-Block übernehmen |
| `prompt_registry.json` | RAG-Index; kein Runtime-Hook |

---

## 11. Import-Referenz — Multi-Source Liquidation Pipeline

Quelle: `imports/cherrystudio/choral_text/PROJEKT_LOG.md` (Session 01.08.2026 + 30.07.2026). Abgleich mit Hook D3/D4. **Nicht** den `.env`-Block aus dem Log kopieren (dort steht ein Infura-Key).

### 11.1 Drei Quellen, ein Phasen-Schema

```
Binance CEX (!forceOrder)   ──┐
Aave V3 (LiquidationCall)   ──┤  → :LiquidationEvent → Rayleigh-R → :RiskAdjustment
Uniswap V3 (Swap-Volumen)    ──┘    (einheitliches 8h-Phasen-Schema)
```

Phase (D3): `(t mod 28800) / 28800` — identisch für Liquidation und Swap. BTC-Difficulty separat: `(block_height % 2016) / 2016` als `:PhaseSource {id: 'btc:difficulty_epoch'}`.

| Writer | Label | Schema-Variante (D4) | Im Import? |
|--------|-------|------------------------|------------|
| Binance `liquidation_listener.py` | `:LiquidationEvent` | Cherry: `ts`, `phase`, `usd_value`, `source='binance_futures'` | ja, `choral_text/` |
| Aave V3 | `:LiquidationEvent` | `source='aave_v3'`, `user`, `debt_asset` | **nein** — Log verweist auf LangGraph `feeds/aave_liquidation_listener.py` |
| Uniswap V3 | `:SwapEvent` | `pool`, `price`, `volume_usd` (nicht Liquidation) | **nein** — Log verweist auf LangGraph `feeds/dex_listener.py` |
| AstroCore `seed_liquidations.py` | `:LiquidationEvent` | Seed: `timestamp`, `funding_phase`, `amount_usd` | ja, `astrocore/` |

Hook liest nur `:LiquidationEvent` (D4-Adapter). `:SwapEvent` ist kein P4-Ingest.

### 11.2 Neo4j-Labels (CherryStudio)

`:PhaseSource`, `:AstroProject`, `:AstroSample`, `:CouplingResult`, `:LiquidationEvent`, `:GasPriceEvent`, `:RiskAdjustment`. Indizes laut Log: `liq_ts`, `liq_phase` (Cherry) bzw. Seed `timestamp`/`funding_phase`.

`:CouplingResult`: `source_a`, `source_b`, `class` (`CLASS_AB`/`CLASS_C`), `plv_n1`, `rayleigh_R`, `p_surrogate`, `n_samples`. Relationship `:ANALYZES` → PhaseSource.

### 11.3 Log-Befund (nicht übernehmen)

Simulierte Liquidationen aus Preis-Drops haben keine Phasen-Information — 295 Backtests ohne Edge. Die Regel braucht echte Binance/Aave-Events. Das bestätigt D1: ohne Feed kein positives Verdict.

---

*Nächster Schritt: **P4 prepared / not live** — Dual-Schema + Lab-Smoke erledigt; Live-Quelle bleibt `ASTROCORE_DATA_SOURCE=worm`, bis ein Liquidations-Feed Frames liefert (`fstream` WS 2026-08-30 tot, Spot ok). `ROLE reader` erst auf Enterprise.*
