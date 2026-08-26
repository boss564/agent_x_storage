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
```
