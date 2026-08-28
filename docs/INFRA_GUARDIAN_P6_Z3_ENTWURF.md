# P6 — Z3 Leader-FSM Entwurf (Infra-Guardian)

**Status:** ENTWURF verifiziert (Z3 + BFS) · Lease-Runtime **gate-closed**  
**Stand:** 2026-08-28  
**Parent:** `docs/INFRA_GUARDIAN_SWARM_v0.md` §4, §6

## Implementierung

| Komponente | Pfad |
|------------|------|
| Z3/BFS Engine | `prototypes/raas_paper_trading/regime_swarm/leader_fsm_z3.py` |
| Smoke | `scripts/test_regime_leader_z3.py` |
| HTTP | `POST /prove_regime_leader_invariant` in `services/z3_solver/main.py` |
| Shadow-Cluster | `scripts/regime_swarm_shadow_cluster.sh` + `charts/regime-swarm/values-shadow.yaml` |

## Drei Proof-Modi

| Modus | Methode | Behauptung |
|-------|---------|------------|
| `ordinal_z3` | Z3 UNSAT | Genau ein Ordinal-0-Slot bei aktivierter Election |
| `lease_mutex_z3` | Z3 UNSAT | etcd-Mutex: `sum(holds) ≤ 1` |
| `lease_bfs` | Bounded BFS (depth 14, ≤4 replicas) | Lease-FSM-Übergänge verletzen I1 nicht |

## Lease-FSM (geplant — noch nicht in `leader.py`)

```text
States/pod:  FOLLOWER | STANDBY | LEADER
Global:      holder ∈ {-1, 0, …, n-1}

Acquire:     holder=-1 ∧ state_i=FOLLOWER → holder=i, LEADER
Renew:       holder=i → unchanged
Fail/Release: holder=i → holder=-1, FOLLOWER
Standby:     ordinal>0, no lease → STANDBY (no A1/A7/A8)
```

**Invariante I1:** `mutators_count ≤ 1` (nur ein Pod mit Lease darf State mutieren).

## Ausführung

```bash
# Lokal (kein K8s)
PYTHONPATH=. python3 scripts/test_regime_leader_z3.py

# Z3-Service
curl -s -X POST http://localhost:8000/prove_regime_leader_invariant \
  -H 'Content-Type: application/json' \
  -d '{"mode":"all","max_replicas":2}'

# Shadow-Cluster (kubectl + helm)
chmod +x scripts/regime_swarm_shadow_cluster.sh
./scripts/regime_swarm_shadow_cluster.sh up
./scripts/regime_swarm_shadow_cluster.sh chaos-delete-leader
```

## Gate-Status

| Check | Status |
|-------|--------|
| P6 Z3-Entwurf | ✅ PASS (`REGIME_LEADER_Z3_PASS`) |
| P2 Chaos C-01…C-04 | ⏳ Shadow-Skript bereit, manuell auf Cluster |
| P5 Split-Brain T-S1a | ⏳ nach Lease-Runtime |
| §6 GATE OPEN | 🔒 **CLOSED** — kein Lease-Code |
