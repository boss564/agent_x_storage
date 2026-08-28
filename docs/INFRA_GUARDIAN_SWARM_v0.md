# Infra-Guardian-Schwarm — MAP v0 (HA-Erweiterung Regime-Drift)

**Status:** MAP + UPGRADE-GATE (keine Lease-API-Implementierung vor Freigabe)  
**Stand:** 2026-08-28  
**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · monitoring only · `live_execution=false`  
**Geltungsbereich:** Kubernetes-Betrieb des **9-Agenten Regime-Drift-Schwarms** (Baustein 2)  
**Basis-Stand:** Branch `feature/statefulset-ha` · Commit `3b47d1ef` (StatefulSet, Ordinal-0-Leader, 19/19 Smoke)

**Verwandte Artefakte:**

| Artefakt | Pfad |
|----------|------|
| Regime-Schwarm A1–A9 | `prototypes/raas_paper_trading/regime_swarm/` |
| Pre-Reg Baustein 2 | `docs/RaaS_REGIME_DRIFT_PREREG.md` |
| Produktions-Daemon | `scripts/run_regime_swarm_daemon.py` |
| Leader-Election (Ordinal) | `prototypes/raas_paper_trading/regime_swarm/leader.py` |
| Helm StatefulSet | `charts/regime-swarm/` |
| Z3 Compliance Gate | `services/z3_solver/main.py` |

---

## 0. Regeln (bindend)

1. **Charter unverändert** — Der Infra-Schwarm prüft **Infrastruktur**, nicht Handelsausführung. Kein Order-Send, kein Live-WebSocket-Feed im Regime-Daemon (Paper-WORM only).
2. **Kein Code vor Gate** — Lease-API, RBAC-Erweiterungen und Failover-Logik werden **erst** nach dokumentiertem PASS aller Pflicht-Checks in §6 deployed.
3. **Wahrheit vor Optik** — Szenarien 3 (Reconnect-Storm) und 4 (Active-Active) sind **out of scope v0**; sie werden in der Matrix geführt, aber blockieren die Lease-API-Freigabe nicht.
4. **Ein aktiver Entscheider** — Invariante I1: zu keinem Zeitpunkt dürfen zwei Pods gleichzeitig A1/A7/A8-State mutieren oder Webhooks auslösen.
5. **State bei Failover** — Invariante I2: nach kontrolliertem Leader-Wechsel dürfen Cooling-Counter und Soft-Multiplier nicht regressieren (kein stiller Reset auf 0 ohne Audit-Eintrag).

---

## 1. Motivation — vier HA-Szenarien

| # | Szenario | Scheitern des Ordinal-0-Modells | v0-Priorität | Ziel-Erweiterung |
|---|----------|----------------------------------|--------------|------------------|
| **S1** | **Split-Brain** (Netzwerk-Partition) | Pod-0 und Pod-1 glauben beide, Leader zu sein; doppelte Audits/Webhooks | **Hoch** | Kubernetes **Lease-API** + Write-Fencing |
| **S2** | **Silent Hang** (Deadlock, kein Crash) | Liveness-Probe zu langsam; Regime-Zyklen aus | **Hoch** | Lease-Renewal alle **≤5 s**; Failover **<15 s** |
| **S3** | **Reconnect-Storm** (API-Ban) | Failover baut viele Live-Feeds gleichzeitig neu auf | **Niedrig** (Paper-WORM) | Backoff-Orchestrator — **nur bei Charter-Änderung** |
| **S4** | **Active-Active** (Durchsatz) | Ein Python-Prozess skaliert nicht auf 500+ Symbole | **Später** | Sharding + Coordinator — **Charter-Amendment** |

**Aktueller Mitigationsstand (ohne Lease):**

- StatefulSet `OrderedReady`, PVC pro Ordinal, Pod-0 = Leader, Standby = Heartbeat only.
- Pod-0-Crash → K8s-Neustart, State auf `data-<sts>-0` erhalten.
- **Nicht abgedeckt:** S1, S2.

---

## 2. Infra-Guardian-Schwarm P1–P9

Meta-Schwarm: handelt **nicht** an der Börse, sondern prüft und härtet die HA-Erweiterung.

| ID | Name | Klasse | Primäre Repo-Anker | Aufgabe (HA-Erweiterung) |
|----|------|--------|-------------------|--------------------------|
| **P1** | Charter- & Invarianten-Wächter | Governance | `docs/RaaS_REGIME_DRIFT_PREREG.md`, Wave 39 `ethical_boundary/` | Friert §3-Invarianten ein; blockiert Deploy bei Charter-Verletzung |
| **P2** | Chaos-Orchestrator (Red Team) | Ops | `chaos/`, `agents_b2g/settlement/chaos_harness.py` | `kubectl delete pod`, Netz-Latenz, PVC-I/O-Drossel auf Shadow-Cluster |
| **P3** | State-Transfer-Simulator | Daten | `regime_swarm/state_store.py`, `leader_snapshot.json` | Misst Failover-Latenz bis konsistenter Readiness (Ziel **<15 s**) |
| **P4** | Netzwerk- & API-Latenz-Simulator | Infra | `agents_b2g/resilience/` (RPC-Failover-Muster) | etcd/API-Ausfall; Lease-Ablauf korrekt? |
| **P5** | Conflict-Injector (Split-Brain) | Security | `chaos/docker-compose.chaos.yml` (throttler) | Zwei Pods manipulieren Lease gleichzeitig → Race aufdecken |
| **P6** | Z3-Formalverifizierer | Compliance | `services/z3_solver/main.py` | Beweist: Automat **niemals** `leaders_count > 1` bei gültigem Lease |
| **P7** | Blast-Radius-Scout | Ops | `scripts/raas_notify_gate_blocks.py`, Webhook-Pfade im Daemon | Rate-Limits (Slack/PagerDuty) bei Failover-Sturm |
| **P8** | Kaskaden-Modellierer | Risiko | `charts/regime-swarm/values.yaml` (resources) | OOM/CPU-Spike beim Failover killt Standby? |
| **P9** | Rollback-Archivar (WORM) | Compliance | A9-Audit-Pattern, `state_store.py` | Signierter Snapshot vor Upgrade; Rollback **<30 s** |

**Abgrenzung zum Regime-Schwarm (A1–A9):** A-Schwarm = Markt-/Drift-Logik auf Paper-WORMs. P-Schwarm = **Infrastruktur-Freigabe** für HA-Upgrades.

---

## 3. Formale Invarianten (P1 — vor Implementierung eingefroren)

| ID | Invariante | Formalisierung (Z3-Vorbereitung) | Messgröße |
|----|------------|----------------------------------|-----------|
| **I1** | Exklusiver Leader | `leaders_count ≤ 1` über alle Pods im Namespace | Lease-Holder-Count |
| **I2** | Kein stiller State-Verlust | `cooling_counters_after ≥ cooling_counters_before` OR dokumentiertes `ROLLBACK_EVENT` in Audit | JSON diff `swarm_state.json` |
| **I3** | Max Failover-Zeit | `t_standby_active − t_leader_last_renewal ≤ 15 s` (S2) | P3 Stopwatch |
| **I4** | Lease-Renewal | Leader erneuert Lease alle `≤ lease_duration/3` (Default: **5 s** bei 15 s Lease) | Prometheus / Audit |
| **I5** | Charter | `live_execution = false` in jedem Cycle-Log | Statischer Check |
| **I6** | Kein Doppel-Webhook | `webhook_dispatches_per_incident ≤ 1` | P7 Zähler |

**Fail-closed:** Verletzung von I1 oder I5 → Deploy **BLOCKED** (Wave-39-Analogie: `ETHICAL_BOUNDARY` / Gate `FAIL`).

---

## 4. Z3-Constraints (P6 — Entwurf für Lease-`leader.py` v2)

Zustandsautomat (vereinfacht):

```text
States:  FOLLOWER | CANDIDATE | LEADER | STANDBY_OBSERVER
Vars:    holds_lease ∈ {0,1}  renewal_age_s  pod_ordinal

Transitions (erlaubt):
  FOLLOWER + acquire_lease_ok     → LEADER     (holds_lease=1)
  LEADER   + renew_ok             → LEADER     (renewal_age_s=0)
  LEADER   + renew_fail           → FOLLOWER   (holds_lease=0)
  LEADER   + release              → FOLLOWER
  STANDBY  + (no lease, ord>0)    → STANDBY    (kein A1/A7/A8)

Forbidden:
  LEADER(p0) ∧ LEADER(p1)                    → I1 violation
  LEADER ∧ live_execution=true               → I5 violation
  LEADER ∧ ¬write_audit ∧ mutate_cooling     → I2 risk
```

**Z3-Endpoint (geplant):** `POST /prove_regime_leader_invariant` — Payload: Lease-Duration, Renewal-Interval, Replica-Count.  
**PASS-Kriterium:** `failed_count == 0` (analog BHO-Gate).

---

## 5. Test-Matrix (Pflicht vor Lease-API)

### 5.1 Szenario-Tests

| Test-ID | Szenario | Agent | Methode | PASS |
|---------|----------|-------|---------|------|
| **T-S1a** | Split-Brain | P5 | Netpol-Partition: Pod-0 ↔ Pod-1; beide versuchen Lease | Genau **1** Holder |
| **T-S1b** | Split-Brain | P6 | Z3-Proof auf Lease-FSM | `gate=PASS` |
| **T-S2a** | Silent Hang | P2 | `SIGSTOP` auf Leader-Prozess 20 s | Standby übernimmt **<15 s** |
| **T-S2b** | Silent Hang | P4 | API-Latenz 10 s auf Lease-Endpoint | Lease expires, kein Zombie-Leader |
| **T-S3** | Reconnect-Storm | P7 | *Deferred* — Paper-WORM only | N/A v0 |
| **T-S4** | Active-Active | P8 | *Deferred* — Charter | N/A v0 |

### 5.2 Chaos-Batterie (P2 — Shadow-Cluster)

| Lauf | Injektion | Erwartung |
|------|-----------|-----------|
| **C-01** | `kubectl delete pod <leader>` | Neuer Leader **oder** Pod-0 reclaim **<30 s**, I2 PASS |
| **C-02** | RollingUpdate StatefulSet | `maxUnavailable=0`, kein I1-Verstoß |
| **C-03** | PVC I/O stress (`stress-ng`) | Heartbeat bleibt; kein Datenkorruption in `swarm_state.json` |
| **C-04** | OOM-Simulation (limit memory) | Standby überlebt; P8-Report ohne Kaskaden-Kill |

**Seeds / Wiederholungen:** 10 Läufe pro Chaos-Test, α = 0.01 für Signifikanz-Claims (konsistent mit CI-/Rescue-Studien).

### 5.3 State-Transfer (P3)

| Metrik | Schwellwert |
|--------|-------------|
| Zeit bis Standby `is_leader=1` (Lease-Modus) | **≤ 15 s** (I3) |
| Zeit bis `swarm_state.json` konsistent lesbar | **≤ 5 s** nach Leader-Claim |
| Cooling-Counter-Drift nach Failover | **0** (I2) |

---

## 6. Infrastructure Upgrade Protocol (Freigabe-Gate)

Geordnete Pipeline — **kein Schritt überspringen**:

```text
P7 Scout     → HA-Lücke dokumentiert (S1/S2), Blast-Radius Webhooks OK
     ↓
P1 Wächter   → I1–I6 eingefroren (dieses Dokument, Hash in Audit)
     ↓
P6 Z3        → FSM-Proof PASS (Entwurf leader.py v2)
     ↓
P2 Chaos     → C-01…C-04 auf Shadow-Cluster (Namespace: regime-swarm-shadow)
     ↓
P5 Conflict  → T-S1a PASS (kein Split-Brain)
     ↓
P3 Transfer  → T-S2a/b + I3/I2 PASS
     ↓
P8 Kaskade   → C-04 PASS (kein OOM-Domino)
     ↓
P9 Archivar  → WORM-Snapshot + signierter Freigabe-Record
     ↓
GATE OPEN    → Lease-API + RBAC (Commit 2) erlaubt
```

### Freigabe-Record (P9 — JSONL-Felder)

```json
{
  "schema": "infra_guardian_release_v0",
  "upgrade": "regime_swarm_lease_api_v1",
  "invariants_hash": "<sha256 of §3>",
  "tests_passed": ["T-S1a", "T-S1b", "T-S2a", "T-S2b", "C-01", "C-02", "C-03", "C-04"],
  "z3_gate": "PASS",
  "charter": "DEFENSIVE_CAUSAL_GROUNDING",
  "live_execution": false,
  "approved_at": "<ISO8601>",
  "prev_leader_mode": "ordinal_0_static",
  "next_leader_mode": "kubernetes_lease"
}
```

**Gate geschlossen (aktuell):** Ordinal-0-Modell produktiv erlaubt; Lease-API **verboten** bis `approved_at` gesetzt.

---

## 7. Geplanter Commit 2 (nach Gate — nicht Teil von v0)

| Komponente | Änderung |
|------------|----------|
| `leader.py` | `KubernetesLeaseLeader` (acquire/renew/release), Fallback Ordinal-0 wenn `IN_CLUSTER!=true` |
| `run_regime_swarm_daemon.py` | Renewal-Loop 5 s; Fencing vor `_persist_state` / Webhooks |
| `charts/regime-swarm/` | ServiceAccount, Role, RoleBinding (`coordination.k8s.io/leases`) |
| `scripts/test_regime_swarm_ha.py` | T-S1/T-S2 Smoke (kind/minikube oder mocked API) |

**Lease-Spec (vorab):**

| Parameter | Wert |
|-----------|------|
| Lease-Name | `regime-swarm-leader` |
| Namespace | Release-Namespace |
| `leaseDurationSeconds` | 15 |
| `renewIntervalSeconds` | 5 |
| Holder identity | `POD_NAME` |

---

## 8. Abgrenzung & bewusste Nicht-Ziele (v0)

- **Kein** Live-Market-WebSocket im Regime-Daemon (S3 irrelevant bis Charter-Änderung).
- **Kein** Multi-Leader-Sharding (S4) — erfordert separates Pre-Reg-Amendment.
- **Kein** Redis-State-Layer in v0 — Lease + PVC pro Ordinal; Shared State nur via `leader_snapshot.json` auf Leader-PVC (Standby read-only bis Promotion).
- **Kein** automatisches Promotion ohne Lease — Ordinal-1 bleibt STANDBY bis Lease-API gate-open.

---

## 9. Status

```text
Map:              docs/INFRA_GUARDIAN_SWARM_v0.md
Regime-Schwarm:   19/19 smoke (scripts/test_raas_regime_drift.py)
K8s-Basis:        charts/regime-swarm/ StatefulSet (feature/statefulset-ha)
Leader-Modus:     ordinal_0_static (SWARM_LEADER_ELECTION_ENABLED)
Lease-API:        GATE CLOSED — wartet auf §6 Freigabe
Nächster Schritt: Shadow-Cluster + P6 Z3-Entwurf (nach Merge Map-Commit)
```

---

## 10. Referenzen

- `docs/RaaS_REGIME_DRIFT_PREREG.md` — Baustein-2-Pre-Reg (A1–A9)
- `docs/CI_RESILIENZ_STUDIE_PREREG.md` — Studien-Design-Muster (α, Seeds, H0/H1)
- `docs/AGENT_SWARM_P9_MAP_v0.md` — P-Schwarm-Map (anderer Kontext; Namensraum nicht verwechseln)
- `charts/regime-swarm/templates/NOTES.txt` — PVC-pro-Pod-Hinweis
