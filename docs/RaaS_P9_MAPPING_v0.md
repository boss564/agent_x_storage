# RaaS — Risk-as-a-Service Mapping (P₁…P₉)

**Status:** MAP v0 (2026-08-27) · bindend unter Charter Option 1  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · keine Order-Execution · `live_execution=false`  
**Basis:** `docs/AGENT_SWARM_P9_MAP_v0.md` · `docs/AGENT_X_CHARTER.md` · `podman-compose.p9.yml`

---

## 1. Produkt (eine Zeile)

**Isolierte Contract-Stress-Simulation → fail-closed Gate → GoBD-Audit-Zertifikat.**  
Kunden-Contracts werden in einer Sandbox analysiert; Agent X führt keine echten Orders aus.

---

## 2. Agent ↔ RaaS-Rolle

| Agent | RaaS-Rolle | Defensive Funktion | Primäre Artefakte |
|-------|------------|--------------------|-------------------|
| **P₁** | Contract-Parser | Bytecode/Schema importieren, Invarianten-Vorfilter | `agent_x_klasse_a_1_ingestion.py`, `api_agents/agent_1_gatekeeper.py`, `contracts/` |
| **P₂** | Latenz-Simulator | Jitter/Latenz injizieren (simuliert), Relay-Beobachtung | `api_agents/agent_9_telemetry.py`, `agents_b2g/telemetry/` |
| **P₃** | Execution-Pressure | Ausführungs-**Exposition** belasten (simuliert) | `agent_x_klasse_b_pressure_b*.py`, `api_agents/agent_5_sync_exec.py` |
| **P₄** | MEV Scout | Angriffs-**Szenarien** simulieren, nicht ausführen | `agent_x_klasse_c_3_arbitrage.py`, `agent_x_klasse_f_sentiment_whale.py` |
| **P₅** | Oracle-Stress | Verrauschte Feeds einspeisen (Mock/Live-Read) | `agent_x_klasse_d_2_analytics.py`, `agent_x_klasse_d_oracle_models.py` |
| **P₆** | Z3 Auditor | BHO/Z3-Grenzen, fail-closed Abbruch | `agent_x_lending_b2_risk.py`, `services/z3_solver/`, `infra-gate` |
| **P₇** | Shock Injector | Extreme Szenarien erzeugen (simuliert) | `agent_x_klasse_a_3_strategie.py`, `agent_x_offchain_scout.py` |
| **P₈** | Kaskaden-Modellierer | Ansteckung/`liquidatable` modellieren | `agent_x_klasse_c_2_flashloans.py`, `agent_x_lending_b3_liquidation.py` |
| **P₉** | Audit-Anchor | Telemetrie aggregieren, WORM/GoBD-Export | `agent_x_storage_guardian.py`, `api_agents/agent_10_blockchain_anchor.py` |

**Alle Rollen bleiben defensiv.** Stress = Simulation in isolierter Umgebung; Charter Negativklausel unberührt.

---

## 3. B2B-Kundenablauf

```text
┌─────────────────────────────────────────────────────────────────┐
│ 1. Upload & Konfiguration          api/v1/raas/…                │
│    Contract (bytecode/ABI) · Szenario-Profil · Tenant-ID        │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Stress-Execution                Stress-Runner (Podman P1–P8) │
│    N parallele Szenarien (Ziel: 10k) · Kanten-Ledger S_ij=ℓ_ij  │
│    P2–P7 injizieren · P4/P8 messen · kein On-Chain-Send         │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Gate & Zertifikat               infra-gate + P6 + P9           │
│    M7 ∧ Z3 ∧ BHO → BLOCKED|RELEASED · live_execution=false      │
│    P9 → GoBD JSONL + PDF/A-3 Risikogutachten                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 API-Skizze (`api/v1/raas/`)

| Methode | Pfad | Rolle |
|---------|------|-------|
| `POST` | `/contracts/upload` | P₁ — Bytecode/ABI + Schema-Check |
| `POST` | `/runs` | Job anlegen (Tenant, Profil, N-Szenarien) |
| `GET` | `/runs/{id}` | Status, Gate-Entscheidungen, Metriken |
| `GET` | `/runs/{id}/certificate` | P9 — PDF/JSON Audit-Zertifikat |
| `POST` | `/gate/evaluate` | Proxy → `infra-gate:8010/v1/evaluate` (intern) |

Auth: Tenant-Key · Scope-Flag `DEFENSIVE_CAUSAL_GROUNDING` in jedem Response.  
Human-Gate: nur intern/Operator — nicht Kunden-Self-Service für Execution.

---

## 4. Stress-Runner (Compose-Anbindung)

Bestehend: `podman-compose.p9.yml` (P1–P9 + infra-z3/state/hsm/gate).

| Phase | Services | Output |
|-------|----------|--------|
| Intake | P₁ | normalisierter Contract-Handle, Invarianten-OK/FAIL |
| Simulate | P₂–P₇ | Szenario-Telemetrie, Stress-Scores |
| Risk | P₃, P₄, P₈ | exec_risk, cascade_risk, market_stress |
| Gate | P₆, `infra-gate` | `BLOCKED`\|`RELEASED`, reasons[] |
| Anchor | P₉ | WORM-JSONL, Zertifikat-Hash |

Runner-Orchestrator (neu): `scripts/raas_stress_runner.py` — sequenziert Phasen,
ruft Gate HTTP, schreibt unter `{data_root}/{tenant_id}/raas/runs/{run_id}/`.

---

## 5. Audit-Exporter (P₉)

Wiederverwendung:

- `agents_b2g/ops/pilot_agents.py` — `AuditExporterAgent` (GoBD-XML/ZIP)
- `agents_b2g/compliance/subagents/pdf_audit_composer.py` — PDF/A-3
- Shadow-Pilot: `/api/v1/audit/export/{id}/jsonl` · `/pdf` (Referenz-Pattern)

RaaS-Zertifikat-Inhalt (Minimum):

1. Run-Metadaten (Tenant, Contract-Hash, Seeds, N-Szenarien)
2. Gate-Trace (M7/Z3/BHO pro Szenario-Cluster)
3. Verdict: `ENTLASTET` / `VORBEHALT` / `BLOCKED` (analog RPA-Pipeline)
4. Scope: `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false`
5. WORM-Signatur / Hash-Kette (P₉)

---

## 6. Gate & Charter (bindend)

```text
Default:         Gate CLOSED · live_execution=false
Kunden-Output:   Analyse + Zertifikat — keine Trade-Freigabe durch Agent X
Freigabe:        menschlich + Token (infra-gate) — optional extern, nie Auto-Exec
Wave 39:         ScopeEnforcer · EthicalAssertion · fail-closed
```

Referenz: Map §10 · `services/fail_closed_gate/` · `prototypes/v5_fail_closed_gate/`.

---

## 7. Geschäftsmodell (ROI, nicht Implementation)

| Zielgruppe | Nutzen |
|------------|--------|
| DeFi-Teams | Audit-Kosten senken (simuliert vor Mainnet) |
| Krypto-Fonds | Versicherungs-/Limit-Prämien mit Gutachten belegen |
| Protokolle | Kaskaden-Crashs vorhersagen, nicht auslösen |

Abrechnung: Lizenz pro Tenant + Volumen (Runs/Monat) — **außerhalb** dieses Repos.

---

## 8. Nächste Implementierungsschritte

| # | Deliverable | Abhängigkeit |
|---|-------------|--------------|
| 1 | **RaaS-Portal** — FastAPI `api/v1/raas/*` (Upload, Runs, Status) | P₁ Intake |
| 2 | **Stress-Runner** — `scripts/raas_stress_runner.py` + Compose-Health | P2–P8 live |
| 3 | **Audit-Exporter** — P₉ Zertifikat-Pipeline (JSON + PDF/A-3) | Gate-Trace |
| 4 | E2E Smoke | `make raas-smoke` — 1 Contract, 100 Szenarien, Zertifikat |

**Nicht in Scope:** Order-Routing, Searcher-Pipelines, Live-DEX-Execution.

---

## 9. Verweise

| Dokument | Rolle |
|----------|-------|
| `docs/AGENT_SWARM_P9_MAP_v0.md` | P-Agenten, Compose, §9–§10 Gate |
| `docs/AGENT_X_CHARTER.md` | Negativklausel, Air-Gap |
| `docs/COMPLIANCE_PLAYBOOK.md` | GoBD/K1–K8 |
| `podman-compose.p9.yml` | Runtime-Stack |
