# Infra-Guardian Shadow-Chaos — Ergebnis (P2/P5)

**Status:** Ordinal-HA PASS · Lease-API **GATE CLOSED**  
**Datum:** 2026-08-28  
**Parent:** `docs/INFRA_GUARDIAN_SWARM_v0.md` §5–§6  
**Report:** `logs/infra_guardian/shadow_chaos_latest.json`

## Umgebung

| Feld | Wert |
|------|------|
| Plattform | Docker Compose (`docker-compose.regime-swarm-shadow.yml`) |
| Replicas | 2 (`regime-swarm-shadow-0` Leader, `regime-swarm-shadow-1` Standby) |
| Leader-Modus | `ordinal_0_static` (`SWARM_LEADER_ELECTION_ENABLED=true`) |
| K8s/Helm | Nicht verfügbar lokal — Compose-Shadow als äquivalente Drill-Umgebung |
| Charter | `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` |

## Ergebnisse (8/8 PASS)

| Test-ID | Agent | Szenario | Ergebnis | Detail |
|---------|-------|----------|----------|--------|
| BASELINE | P2 | Leader/Standby-Rollen | **PASS** | `swarm_is_leader`: pod0=1, pod1=0 |
| **T-S1a** | **P5** | Split-Brain (ordinal) | **PASS** | standby_tick≥1, complete_cycles=0 auf Standby |
| **C-01** | P2 | Leader-Pod löschen | **PASS** | Heartbeat nach `docker restart` |
| **C-02** | P2 | Geordnetes Rolling | **PASS** | Nach Restart: pod0=1, pod1=0 |
| **C-03** | P2 | PVC-I/O-Stress | **PASS** | State-Write + Heartbeat ok |
| **T-S2a** | P4/P2 | Silent Hang (`docker pause`) | **PASS** | Standby bleibt `is_leader=0` (kein Promotion) |
| **C-04** | P8 | Standby-OOM-Risiko | **PASS** | Standby läuft (384M limit) |
| **P3-state** | P3 | State-Persistenz | **PASS** | `swarm_state.json` auf Leader-Volume |

**Verdict:** `INFRA_SHADOW_CHAOS_PASS`

## §6 Upgrade-Protokoll — Fortschritt

```text
P7 Scout     ✅ HA-Lücke S1/S2 dokumentiert (MAP v0)
P1 Wächter   ✅ I1–I6 eingefroren
P6 Z3        ✅ REGIME_LEADER_Z3_PASS (0c819b18)
P2 Chaos     ✅ C-01…C-04 PASS (Compose-Shadow)
P5 Conflict  ✅ T-S1a PASS (ordinal — kein Doppel-Mutator)
P3 Transfer  ✅ State-Datei vorhanden (ordinal; kein Lease-Failover)
P8 Kaskade   ✅ C-04 PASS
P9 Archivar  ✅ Freigabe-Record unten (ordinal HA only)
GATE OPEN    🔒 CLOSED — Lease-API + K8s T-S1a (Lease) ausstehend
```

### Bewusste Abgrenzung

- **T-S1a (Lease/Split-Brain):** Erfordert Lease-Runtime + Netzwerk-Partition auf K8s — **nicht** in diesem Lauf.
- **T-S2b (etcd/API-Latenz):** Erfordert Lease-Objekt — **deferred**.
- **I3 Failover ≤15s:** Gilt für Lease-Modus; Ordinal-Modell re-kreiert Pod-0 via K8s/Compose-Restart (C-01 ~12s beobachtet).

## P9 Freigabe-Record (ordinal HA — kein Lease)

```json
{
  "schema": "infra_guardian_release_v0",
  "upgrade": "regime_swarm_ordinal_ha_v1",
  "invariants_hash": "sha256:INFRA_GUARDIAN_SWARM_v0_sec3",
  "tests_passed": ["BASELINE", "T-S1a", "C-01", "C-02", "C-03", "T-S2a", "C-04", "P3-state", "P6-Z3"],
  "z3_gate": "PASS",
  "chaos_gate_ordinal": "PASS",
  "charter": "DEFENSIVE_CAUSAL_GROUNDING",
  "live_execution": false,
  "approved_at": "2026-08-28T07:27:29Z",
  "prev_leader_mode": "ordinal_0_static",
  "next_leader_mode": "kubernetes_lease",
  "lease_api_gate": "CLOSED"
}
```

## Reproduktion

```bash
make raas-regime-shadow-chaos
# oder
PYTHONPATH=. python3 scripts/regime_swarm_shadow_chaos.py
```

## Nächster Schritt

1. **K8s-Shadow** (wenn Helm/Cluster verfügbar): `make raas-regime-shadow-up` + manuelles C-01  
2. **Lease-Implementierung** (Commit 2) — erst nach Lease-T-S1a/T-S2b auf K8s + erneutem §6 PASS
