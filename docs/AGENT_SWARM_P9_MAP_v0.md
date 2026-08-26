# 9-Agenten-Schwarm — Artefakt-Zuordnung P₁…P₉

**Status:** MAP + SCREENING-GATE (kein DRAFT · keine Pre-Reg · keine Hypothesentestung)  
**Stand:** 2026-08-26  
**Screen:** `scripts/run_agent_swarm_prototype_screen.py`  
**Artefakte:** `agents_b2g/emergence/agent_swarm_prototype_v0/`

---

## 0. Regeln (bindend für Prototyp)

1. **Keine Verhaltens-Matrizen** — Interaktion nur über \(\mathbf{P}_i=(g_i,\theta_i^0)\) und Kanten-Ledger.  
2. **Kanten-Signal-Pfad** — \(S_{ij}=\ell_{ij}\) (`avg_latency`), kein globaler Broadcast-Bus als Steuergröße.  
3. **Screening-Pflicht** — Batterie A∧B∧C muss PASS, bevor Experimente auf dieser Architektur starten.  
4. **Charter (Option 1)** — Scope `DEFENSIVE_CAUSAL_GROUNDING` (`docs/AGENT_X_CHARTER.md`).  
   P9 modelliert Markt-/Handels**dynamik** zur Risiko- und Schwarmanalyse — **keine** Order-Execution,  
   keine MEV-Extraktion, keine offensiven Liquidationen. Wave 39 fail-closed.

Messkontinuität: sticky-ℓ-Zahlen der Kopplungsserie (EWMA) sind **Vorher-Zustand**;
dieses Screening prüft die **aktuelle** Intake-Definition (heute noch EWMA).

---

## 1. Zuordnung (überschneidungsfrei)

Pfade relativ zum Repo-Root `agent_x_storage/`. Wo nötig: `api_agents/`-Präfix.

| Agent | Rolle | Primäre Artefakte | Aufgabe (defensiv) |
|-------|-------|-------------------|---------------------|
| **P₁** | Ingestion & Invarianten | `agent_x_klasse_a_1_ingestion.py`, `api_agents/agent_1_gatekeeper.py`, `contracts/HandwerkAnchor.sol` | Filter, Schema, Null-Toleranz; Beobachter-Intake |
| **P₂** | Telematic & Relay | `api_agents/agent_9_telemetry.py`, `api_agents/agent_17_supply_chain.py`, `agents_b2g/telemetry/` | Datenfluss-Puffer, Latenz-Analytik; Relay/Mempool-**Beobachtung** (kein Bundle-Send) |
| **P₃** | Pressure & Exec-Risk | `agent_x_klasse_b_pressure_b1_ingestion.py`, `agent_x_klasse_b_pressure_b2_analytics.py`, `api_agents/agent_5_sync_exec.py` | Durchsatz/Druck; Ausführungs-**Risiko** (Slippage, MEV-Exposition) — keine Order |
| **P₄** | Market-Stress | `agent_x_klasse_c_3_arbitrage.py`, `agent_x_klasse_f_sentiment_whale.py`, `out/ResourceTrader.sol` | Arbitrage-**Lücken** als Stress-Indikator messen — keine Arb-Execution |
| **P₅** | Analytics & Oracle | `agent_x_klasse_d_2_analytics.py`, `agent_x_klasse_d_oracle_models.py`, `agent_x_pyth_client.py` | Reduktion, Oracle-Feeds (Beobachtung) |
| **P₆** | Risk & Compliance | `agent_x_lending_b2_risk.py`, `api_agents/agent_14_audit_compliance.py`, `services/z3_solver/` | Z3/BHO-Invarianten, Risk-Limits — Beobachter |
| **P₇** | Strategy-Scout (obs.) | `agent_x_klasse_a_3_strategie.py`, `agent_x_offchain_scout.py`, `agent_x_jito_client.py` | Off-Chain-**Signale** beobachten; Szenario-Scout — keine Trade-Steuerung |
| **P₈** | Cascade & Force-Risk | `agent_x_klasse_c_2_flashloans.py`, `agent_x_lending_b3_liquidation.py`, `agent_x_flashbots_client.py` | Liquidations-**Kaskaden** modellieren (`liquidatable`/`at_risk`) — keine Execution |
| **P₉** | Storage & Anchor | `agent_x_storage_guardian.py`, `agent_x_orchestrator.py`, `core/state_store.py`, `api_agents/agent_10_blockchain_anchor.py` | State, Ledger, GoBD-WORM-Beobachtung |

\(\mathbf{P}_i\)-Vektoren selbst: Gas A1…A9 → `agents_b2g/emergence/response_rij.py` (`derive_p_bank`).

---

## 2. Screening-Batterie (Prototyp)

| Schicht | Definition | Schwelle |
|---------|------------|----------|
| **A** | Median \|ρ\| Sticky-`R` vs. Schwarm-Mittel | ≤ 0.90 (`n_corr ≥ 14`) |
| **B** | MAE_norm unter Partnerpermutation auf `R` | ≥ 0.05 |
| **C** | mean \|ΔR(S1)−ΔR(S2)\| | ≥ 0.05 |

Dynamik: φ_L + \(R_{ij}=a_i(1+\gamma_{ij})(\ell_{ij}-b_i)\) wie Closed-Loop-Capture
(kein κ-Sweep). Seeds: `{20261701…03}` (Kopplungs-Screening/Sweep gesperrt).

| Ergebnis | Konsequenz |
|----------|------------|
| A∧B∧C PASS | Architektur für Experimente geeignet |
| A∧B∧C FAIL | Quelle / Reaktion / Kanten-Pfad anpassen — kein Experiment |

---

## 3. Status

```text
Map:     docs/AGENT_SWARM_P9_MAP_v0.md
Runner:  scripts/run_agent_swarm_prototype_screen.py
Typ:     Prototypen-Screen (Pass/Fail) — keine Pre-Reg
Screen:  ARCHITECTURE_FIT · A∧B∧C+edge PASS · 5.3s · Seeds 20261701…03
Static:  28/28 Artefakte present
Compose: podman-compose.p9.yml  (Intent aus §4–§7; kein Image-Tag-Inventar)
Scope:   DEFENSIVE_CAUSAL_GROUNDING · Option 1 Analyse/Simulation (§9–§10)
```

---

## 4. Podman-Intent — Entry-Points (Wahrheit vor Optik)

**Regel:** Keine erfundenen Image-Tags (`agent_x/p1-ingestion:latest` existiert nicht).  
Jeder P-Container startet mit **`python3 <Modul>`** (Code unter `/app` via `Dockerfile.p9`, kein Host-Bind).  
Begleitmodule ohne `__main__` sind **Import-Only** (nicht eigener Service).

| Service | Primärer Entry-Point | Begleiter (Import / Co-Mount) | `__main__`? |
|---------|----------------------|-------------------------------|-------------|
| **p1-ingestion** | `python3 agent_x_klasse_a_1_ingestion.py status` | `api_agents/agent_1_gatekeeper.py` (kein `__main__`), `contracts/HandwerkAnchor.sol` | ja / nein / n/a |
| **p2-telematic** | `python3 api_agents/agent_9_telemetry.py` | `api_agents/agent_17_supply_chain.py`, `agents_b2g/telemetry/` | ja / ja / pkg |
| **p3-pressure** | `python3 agent_x_klasse_b_pressure_b1_ingestion.py` | `agent_x_klasse_b_pressure_b2_analytics.py`, `api_agents/agent_5_sync_exec.py`, optional `agent_x_bundle_executor.py` | ja |
| **p4-arbitrage** | `python3 agent_x_klasse_c_3_arbitrage.py` | `agent_x_klasse_f_sentiment_whale.py`, `out/ResourceTrader.sol` | ja |
| **p5-analytics** | `python3 agent_x_klasse_d_2_analytics.py` | `agent_x_klasse_d_oracle_models.py`, `agent_x_pyth_client.py` | ja |
| **p6-risk** | `python3 agent_x_lending_b2_risk.py` | `api_agents/agent_14_audit_compliance.py`, HTTP → `infra-z3` | ja |
| **p7-strategy** | `python3 agent_x_klasse_a_3_strategie.py` | `agent_x_offchain_scout.py`, `agent_x_jito_client.py` | ja |
| **p8-force** | `python3 agent_x_klasse_c_2_flashloans.py` | `agent_x_lending_b3_liquidation.py`, `agent_x_flashbots_client.py` | ja |
| **p9-storage** | `python3 agent_x_storage_guardian.py` | `agent_x_orchestrator.py`, `api_agents/agent_10_blockchain_anchor.py`; State via `core/state_store.py` → Redis | ja |

**P2-Pfad-Korrektur (bindend):** nur `api_agents/agent_9_telemetry.py` und `api_agents/agent_17_supply_chain.py` — **nicht** Repo-Root-`agent_9_telemetry.py`.

**Infra (kein P-Vektor):**

| Service | Image / Build | Entry / Rolle |
|---------|---------------|---------------|
| **infra-z3** | Build `services/z3_solver/Dockerfile.z3` → Tag lokal `agentx-z3:p9` | Container `:8000` · Host-Publish `8001:8000` · Volume `z3-data:/data` |
| **infra-hsm** | Build `Dockerfile.bunker` → Tag lokal `agentx-bunker:p9` | SoftHSM/Mock · Volume `hsm-keys:/keys` (+ SoftHSM-Token-Pfad) |
| **infra-state** | `redis:7.4-alpine` | Persistenz hinter `core/state_store.py` · Volume `state-data:/data` |
| **infra-gate** | Build `services/fail_closed_gate/Dockerfile.gate` → `agentx-gate:p9` | Fail-Closed Gate HTTP `:8010` · Default `HUMAN_GATE_OPEN=false` |

Hinweis: `core/state_store.py` ist Schnittstelle (kein Daemon). Persistenz = Redis + Volume, nicht `python3 core/state_store.py`.

---

## 5. Shared-Volumes

| Volume | Mount | Nutzer | Inhalt |
|--------|-------|--------|--------|
| **z3-data** | `/data` | `infra-z3`, lesend `p6-risk` | Z3-Artefakte / Compliance-Caches |
| **hsm-keys** | `/keys` | `infra-hsm`, lesend `p9-storage` (Signatur-Pfad) | Schlüsselmaterial / SoftHSM-Bindung |
| **state-data** | `/data` | `infra-state` | Redis AOF/RDB |
| **Image** `Dockerfile.p9` | `/app` (im Image) | alle `p1`…`p9` | Quellcode gebacken; WorkingDir `/app` |

Compose-Namen: `z3-data`, `hsm-keys`, `state-data` (named volumes).

**macOS / Podman-Maschine:** Host-Bind `.:/app` auf Pfade unter `/Volumes/…` schlägt fehl
(`mkdir /Volumes: operation not permitted`). Deshalb **kein Repo-Bind** — Code kommt
über Build-Context → `Dockerfile.p9`. Named volumes bleiben VM-intern und funktionieren.

---

## 6. Kommunikationspfade (kein Broadcast-Bus)

Steuergröße bleibt **Kanten-Ledger**:

\[
S_{ij}=\ell_{ij}\quad(\texttt{avg\_latency}/\texttt{trimmed\_m7})
\]

| Pfad | Medium | Erlaubt als Steuergröße? |
|------|--------|--------------------------|
| Pᵢ ↔ Pⱼ Signal | Kanten-Ledger (`agents_b2g/emergence/kanten_ledger.py`) | **ja** — einzig |
| P₆ → Z3 | HTTP `http://infra-z3:8000` (`/prove_bho_invariant`, `/compliance`) | ja (Audit/Invariante, nicht Swarm-Broadcast) |
| P₉ → State | Redis `infra-state:6379` via `StateStore` | ja (Persistenz) |
| P₉ → HSM | PKCS#11 / Adapter gegen `infra-hsm` | ja (Signatur) |
| NATS / global PubSub als Schwarm-Steuerung | — | **nein** (Screening-Regel §0.2) |

Compose-Netzwerk: `agent_x_p9` (bridge). DNS-Namen = Service-Namen.

---

## 7. Abhängigkeiten (`depends_on`)

| Service | `depends_on` | Begründung |
|---------|--------------|------------|
| `infra-z3` | — | Basis |
| `infra-hsm` | — | Basis |
| `infra-state` | — | Basis |
| `p1`…`p5`, `p7`, `p8` | `infra-state` | StateStore / gemeinsame Persistenz |
| `p6-risk` | `infra-z3`, `infra-state` | Z3-Audit + State |
| `p9-storage` | `infra-hsm`, `infra-state` | Anchor/Guardian + Keys + State |
| `infra-gate` | `infra-z3`, `infra-state` | Map §10 Option A |
| `p3`–`p8` | `infra-state`, `infra-gate` | Signal/Risk/Gate-Clients |

Keine künstliche `depends_on`-Kette P₁→P₂→… — Kopplung läuft über Ledger, nicht über Compose-Startreihenfolge.

---

## 8. Compose-Ableitung

Datei: **`podman-compose.p9.yml`** + **`Dockerfile.p9`** (Repo-Root).  
Ableitung ausschließlich aus §4–§7. Startbeispiel (cwd = Repo-Root):

```bash
podman compose -f podman-compose.p9.yml up --build
# oder: docker compose -f podman-compose.p9.yml up --build
```

Optional (Live-Edit ohne Rebuild): Volume in die Podman-Maschine share’n, z. B.
`podman machine set -v "/Volumes/THX_OS_ULTRA - Data:/Volumes/THX_OS_ULTRA - Data"`,
dann erst wieder Bind-Mount — Default bleibt Image-Bake.

---

## 9. Defensive Markt-/Handelsdynamik (Option 1 — bindend)

**Entscheidung 2026-08-26:** Analyse-/Simulationssystem, **nicht** ausführende Abschöpfung.  
Charter: `docs/AGENT_X_CHARTER.md` · Scope-Flag `DEFENSIVE_CAUSAL_GROUNDING` · Wave 39 Vierfach-Sperre.

### 9.1 Erlaubt vs. ausgeschlossen

| Ebene | Erlaubt (Option 1) | Ausgeschlossen (Option 2 / Negativklausel) |
|-------|--------------------|---------------------------------------------|
| P2 | Relay-/Mempool-**Beobachtung**, Latenz-/Puffer-Messung | Flashbots/Jito-**Bundles senden** |
| P3 | Ausführungs-**Risiko** (Slippage, MEV-Exposition) modellieren | Uniswap-/DEX-**Order-Ausführung** |
| P4 | Arbitrage-Lücken als **Marktstress-Indikator** | DEX-**Arbitrage ausführen** |
| P8 | Liquidations-**Kaskaden** / Ansteckung simulieren | Flashloan-**Liquidationen** zur Gewinn-Umleitung |
| P1/P5/P6/P9 | Ingestion, Oracles, Z3/BHO, State/GoBD-WORM (Beobachter) | Kausalsignale → Trade-Execution-Pipeline |
| P7 | Off-Chain-Signale / Szenario-Scout (obs.) | Searcher-/Builder-Steuerung |

### 9.2 Rollen ↔ defensive Handelsdynamik

| Agent | Defensive Funktion | Anbindung (Beobachtung / Modell) |
|-------|--------------------|----------------------------------|
| **P₁** | Intake & Invarianten | On/Off-Ramp-**Daten** (Schema/Null-Toleranz); HSM nur Signatur-Beobachtungspfad |
| **P₂** | Signal-Puffer & Latenz | Relay/Mempool-Telemetrie; Wave-28-Frontrunning-**Detection** (kein Send) |
| **P₃** | Exec-Risiko / Druck | Stress der Ausführungs-Exposition; keine Order-Relays |
| **P₄** | Marktstress | Preis-Asymmetrien als Indikator; keine Arb-Tx |
| **P₅** | Oracle-Feeds | Pyth u. a. als Input für Risiko-Modelle |
| **P₆** | BHO / Z3 / Limits | Settlement-Invarianten, Risk-Gates (fail-closed) |
| **P₇** | Scout (obs.) | Off-Chain-Frühwarnsignale; keine Trade-Dispatch |
| **P₈** | Kaskaden-Risiko | `liquidatable` / `at_risk` (Klasse C / Orchestrator); Simulation only |
| **P₉** | State-Anchor | Ledger-Persistenz, GoBD-WORM-Beobachtung |

### 9.3 Architektur-Hinweis

Bestehende Module (`agent_x_klasse_c_3_arbitrage.py`, Flashloan-/Flashbots-/Jito-Clients)
bleiben **Artefakt-Quellen** für Analyse und Simulation. Ihre Nutzung im P9-Schwarm unter
Option 1 ist auf **Lesen / Modellieren / Melden** beschränkt — nicht auf live Execution-Pfade
zu Searcher-/Builder- oder Gewinn-Stacks (Charter §5 Air-Gap).

---

## 10. Fail-Closed Kapitalschutz & menschliches Execution-Gate

**Bindend unter Option 1.** Der „Gewinn“ liegt im **Risikofilter**, nicht in der Execution.
Pipeline: Signal → Gate-Prüfung → (nur bei Mensch-Freigabe) optionale Externalisierung.
Ohne menschliche Freigabe bleibt das Gate **zu** (fail-closed Default).

### 10.1 Schichten

| Schicht | Agenten / Module | Defensive Rolle |
|---------|------------------|-----------------|
| **Signalerzeugung** | P4, P5, P7 | Market-Stress erkennen · Oracle-Feeds · Szenario-/Strategie-**Vorschlag** (obs., kein Auto-Dispatch) |
| **Execution-Gate** | P3, P8 | Exec-Risk · Cascade-Risk — **prüfen und blockieren**, nicht ausführen |
| **Fail-Closed** | P6, M7 (`kanten_ledger`), Z3 | BHO-Settlement · Z3-Invariante · Latenz-Poison-Filter |

P1 bleibt Intake/Invarianten-Vorfilter; P2 liefert Latenz-/Mempool-Beobachtung als Gate-Input;
P9 archiviert Gate-Entscheidungen (GoBD-WORM).

### 10.2 Abbruchbedingungen (fail-closed)

Ein vorgeschlagener Trade / eine Freigabe-Anfrage wird **abgebrochen** (`BLOCKED`), wenn
mindestens eine Bedingung gilt:

1. **M7** — Latenz-Poisoning / MAD-Reject am Kanten-Ledger (`trimmed_m7`)
2. **Z3-Proof-Gate** — unkalkulierbare Markt-Kaskade / Invariantenbruch prognostiziert
3. **BHO-Settlement** — Zero-Sum / Haushaltsregeln verletzt (\|Δ\| > Toleranz)

Wave 39 (`EthicalAssertionAgent` / `ScopeEnforcerAgent`) bleibt fail-closed über dem Gate.

### 10.3 Schaltbares Execution-Gate (Mensch)

```text
Charter:         DEFENSIVE_CAUSAL_GROUNDING  (immutable Scope-Flag)
Default:         Gate CLOSED — Analyse & Warnung only
Öffnung:         nur explizite menschliche Freigabe (kein Autopilot)
Air-Gap:         Analyse-Ebene ⟂  Ausführungs-Ebene (Charter §5)
Nach Freigabe:   externe Systeme dürfen handeln; Agent X führt nicht selbst aus
```

Das Gate ist **schaltbar**, aber die Charter stellt sicher: Agent X startet **keine**
eigenständigen Orders, Bundles oder Liquidationen. Die menschliche Entscheidung öffnet
höchstens einen **Freigabe-Kanal** zu charter-geprüften Schnittstellen — sie ersetzt
nicht die Negativklausel (keine MEV-Extraktion, keine offensive Liquidation).

### 10.4 Datenfluss (logisch)

```text
P1 Intake → P5 Oracles / P4 Stress / P7 Szenario
                ↓
         P3 Exec-Risk ∧ P8 Cascade-Risk
                ↓
         P6 BHO/Z3  ∧  M7 Latenz-Filter
                ↓
         FAIL → BLOCKED (P9 WORM)
         PASS → HUMAN_GATE?
                ↓ nein → bleibt CLOSED
                ↓ ja  → Freigabe-Artefakt (kein On-Chain-Send durch P*)
```

### 10.5 Was dieser Abschnitt nicht ist

- Keine Implementation von Order-Routing oder Searcher-Pipelines
- Keine Aufweichung von §9 / Charter Negativklausel
- E2E mit „simulierten Trades“ = **Simulation der Gate-Logik** (BLOCKED/RELEASED),
  nicht Live-Execution

### 10.6 Podman — Option A (`infra-gate`)

Isolierter Service (nicht in P3/P8 eingebettet):

| Fakt | Wert |
|------|------|
| Compose | `infra-gate` in `podman-compose.p9.yml` |
| Image | `Dockerfile.gate` → `agentx-gate:p9` |
| Port | `8010` (`GATE_BASE_URL=http://infra-gate:8010`) |
| Core | `services/fail_closed_gate/gate_core.py` (M7 echt, Z3/BHO Score-Gates) |
| Human | Default CLOSED · `POST /v1/human_gate` mit Header `X-Human-Gate-Token` + Body `{open, confirm}` (`OPEN_GATE`/`CLOSE_GATE`) |
| Evaluate | `POST /v1/evaluate` → `BLOCKED`\|`RELEASED` · `live_execution=false` immer |
| Auth | `HUMAN_GATE_TOKEN` muss gesetzt sein; ohne Token → 403 (kein Remote-Open) |

```bash
export HUMAN_GATE_TOKEN='…'   # required to open
podman compose -f podman-compose.p9.yml up --build infra-gate
curl -s http://127.0.0.1:8010/health
# Manual open (fail-closed until this):
curl -s -X POST http://127.0.0.1:8010/v1/human_gate \
  -H "Content-Type: application/json" -H "X-Human-Gate-Token: $HUMAN_GATE_TOKEN" \
  -d '{"open":true,"confirm":"OPEN_GATE"}'
```
