# Infra-Guardian Lease T-S1a — Ergebnis (K8s Split-Brain)

**Status:** **T_S1A_LEASE_PASS** · Lease-Runtime im Daemon **GATE CLOSED**  
**Datum:** 2026-08-28  
**Parent:** `docs/INFRA_GUARDIAN_SWARM_v0.md` §5.1  
**Report:** `logs/infra_guardian/lease_t_s1a_latest.json`  
**Runbook:** `docs/INFRA_GUARDIAN_K8S_RUNBOOK.md`

## Umgebung

| Feld | Wert |
|------|------|
| Cluster | `kind-regime-shadow` (K8s v1.37) |
| Namespace | `regime-swarm-shadow` |
| Lease | `coordination.k8s.io/v1` / `regime-swarm-leader` |
| `leaseDurationSeconds` | 15 |
| Harness | `prototypes/raas_paper_trading/regime_swarm/lease_harness.py` |
| Daemon-Modus | Ordinal-0 static (kein `leader.py` v2) |

## Testdesign (P5 Conflict-Injector)

| Phase | Methode | Erwartung |
|-------|---------|-----------|
| **Race** | 2 Worker × 40 `try_acquire` parallel (`shadow-0`, `shadow-1`) | Genau **1** Holder nach Race |
| **Stability** | 20× Poll (250 ms) | Holder stabil, kein Flip |
| **Renew-Fence** | Leader renewed, Challenger greift zu | Challenger **darf nicht** stehlen |

**Hinweis:** Netpol-Partition Pod-0↔Pod-1 auf Single-Node-`kind` nicht vollständig simuliert; Split-Brain wird über **parallele API-Contention** auf dem echten Lease-Objekt abgebildet (§5.1 P5).

## Ergebnis

| Metrik | Wert |
|--------|------|
| Verdict | `T_S1A_LEASE_PASS` |
| Violations | 0 |
| Final Holder | `regime-swarm-shadow-0` |
| Worker-0 Wins | 40/40 |
| Worker-1 Wins | 0/40 |
| Stability Holders | `{regime-swarm-shadow-0}` |
| Renew-Fence Stolen | `false` |

## Invariante I1

```text
leaders_count ≤ 1  →  PASS (jeder Snapshot: ≤1 holderIdentity)
```

## Gate-Status (§6)

| Gate | Status |
|------|--------|
| T-S1a Lease (K8s) | **PASS** |
| T-S1b Z3 | PASS (bereits `REGIME_LEADER_Z3_PASS`) |
| T-S2a/T-S2b | **OFFEN** — nächster Schritt |
| `leader.py` v2 / Daemon-Lease | **CLOSED** bis T-S2b + P9-Record |

## Reproduktion

```bash
kubectl config use-context kind-regime-shadow
kubectl apply -f manifests/infra-guardian/lease.yaml
make raas-regime-lease-t-s1a
```

## Bekannte Einschränkung (behoben im Harness)

K8s-Lease-Timestamps erfordern **6-stellige** Mikrosekunden (`2006-01-02T15:04:05.000000Z`).  
3-stellige Millisekunden führen zu `Invalid value` beim `kubectl patch` — siehe Runbook §2.
