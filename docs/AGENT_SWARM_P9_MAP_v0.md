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

Messkontinuität: sticky-ℓ-Zahlen der Kopplungsserie (EWMA) sind **Vorher-Zustand**;
dieses Screening prüft die **aktuelle** Intake-Definition (heute noch EWMA).

---

## 1. Zuordnung (überschneidungsfrei)

Pfade relativ zum Repo-Root `agent_x_storage/`. Wo nötig: `api_agents/`-Präfix.

| Agent | Rolle | Primäre Artefakte | Aufgabe |
|-------|-------|-------------------|---------|
| **P₁** | Ingestion & Invarianten | `agent_x_klasse_a_1_ingestion.py`, `api_agents/agent_1_gatekeeper.py`, `contracts/HandwerkAnchor.sol` | Filter, Schema, Null-Toleranz |
| **P₂** | Telematic & Relay | `api_agents/agent_9_telemetry.py`, `api_agents/agent_17_supply_chain.py`, `agents_b2g/telemetry/` | Puffer, Signal, Latenz-Glättung |
| **P₃** | Pressure & Execution | `agent_x_klasse_b_pressure_b1_ingestion.py`, `agent_x_klasse_b_pressure_b2_analytics.py`, `api_agents/agent_5_sync_exec.py` | Durchsatz, Batch, Druck |
| **P₄** | Arbitrage & Market | `agent_x_klasse_c_3_arbitrage.py`, `agent_x_klasse_f_sentiment_whale.py`, `out/ResourceTrader.sol` | Asymmetrien, Rand-Signale |
| **P₅** | Analytics & Oracle | `agent_x_klasse_d_2_analytics.py`, `agent_x_klasse_d_oracle_models.py`, `agent_x_pyth_client.py` | Reduktion, Oracle-Feeds |
| **P₆** | Risk & Compliance | `agent_x_lending_b2_risk.py`, `api_agents/agent_14_audit_compliance.py`, `services/z3_solver/` | Audit, Z3, Risiko |
| **P₇** | Strategy & Scout | `agent_x_klasse_a_3_strategie.py`, `agent_x_offchain_scout.py`, `agent_x_jito_client.py` | Exploration, Off-Chain |
| **P₈** | Liquidation & Force | `agent_x_klasse_c_2_flashloans.py`, `agent_x_lending_b3_liquidation.py`, `agent_x_flashbots_client.py` | Schwellen, Liquidation |
| **P₉** | Storage & Anchor | `agent_x_storage_guardian.py`, `agent_x_orchestrator.py`, `core/state_store.py`, `api_agents/agent_10_blockchain_anchor.py` | State, Ledger, Konsolidierung |

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
| **infra-z3** | Build `services/z3_solver/Dockerfile.z3` → Tag lokal `agentx-z3:p9` | `uvicorn main:app --host 0.0.0.0 --port 8000` · Volume `z3-data:/data` |
| **infra-hsm** | Build `Dockerfile.bunker` → Tag lokal `agentx-bunker:p9` | SoftHSM/Mock · Volume `hsm-keys:/keys` (+ SoftHSM-Token-Pfad) |
| **infra-state** | `redis:7.4-alpine` | Persistenz hinter `core/state_store.py` · Volume `state-data:/data` |

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