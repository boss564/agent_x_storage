# Infra-Guardian Lease T-S2b — Ergebnis (Silent Hang / Renewal Timeout)

**Status:** **T_S2B_LEASE_PASS** · §6 Gate **OPEN** · `leader.py` v2 implementiert (Commit 2)  
**Datum:** 2026-08-28  
**Parent:** `docs/INFRA_GUARDIAN_SWARM_v0.md` §5.1 / §6  
**Report:** `logs/infra_guardian/lease_t_s2b_latest.json`  
**Runbook:** `docs/INFRA_GUARDIAN_K8S_RUNBOOK.md`

## Umgebung

| Feld | Wert |
|------|------|
| Cluster | `kind-regime-shadow` |
| Namespace | `regime-swarm-shadow` |
| Lease | `regime-swarm-leader` |
| `leaseDurationSeconds` | 15 |
| Iterationen | **5** |
| Harness | `lease_harness.py` + `regime_swarm_lease_t_s2b.py` |

## Metrik-Design (überarbeitet)

**Problem (v0):** Schwelle `failover ≤ 16 s` prüft praktisch nichts — Failover ist strukturell `≥ lease_duration` (15 s). Die 1 s Marge testete nur Poll-Rauschen.

**Fix (v1):** Primäre Metrik = **Übernahmezeit nach Expiry**:

```text
acquire_delay = failover_seconds − lease_duration_seconds
PASS wenn max(acquire_delay) ≤ 1.0 s  (über 5 Läufe)
```

| Metrik | Median | Max |
|--------|--------|-----|
| `acquire_delay_seconds` | **0,287 s** | **0,339 s** |
| `failover_seconds` (informativ) | ~15,29 s | ~15,34 s |

## Testdesign (P4 — Silent Hang)

| Phase | Methode | Erwartung |
|-------|---------|-----------|
| **Leader aktiv** | `try_acquire` + `renew` (Pod-0) | Holder = Pod-0 |
| **Silent Hang** | Kein Renewal > `leaseDurationSeconds` | Lease läuft ab |
| **Failover** | Standby `try_acquire` nach Expiry | Holder = Pod-1 |
| **I3 (v1)** | `acquire_delay` max ≤ 1,0 s | Übernahme < 1 s nach Expiry |
| **Zombie-Check** | Hung Leader `renew` / `try_acquire` | Beides FAIL |
| **I1** | Holder-Snapshots | Kein Split-Brain |

## Ergebnis (5/5 PASS)

| Metrik | Wert |
|--------|------|
| Verdict | `T_S2B_LEASE_PASS` |
| `n_iterations` | 5 |
| Violations | 0 |
| Zombie Renew / Acquire | `false` / `false` (alle Läufe) |

## Vorbehalt (vor Commit 2 dokumentiert)

- **Gesamt-Failover** ist an `lease_duration_seconds` gebunden (~15 s + `acquire_delay`). Das ist erwartetes Lease-Verhalten, kein Performance-Defekt.
- **Schwelle 1,0 s** für `acquire_delay` misst Poll-Intervall (0,25 s), API-Latenz und Scheduling — variiert mit Last/Maschine.
- **5 Läufe** auf `kind-regime-shadow`; Median/Max berichtet. Langsamere API kann `acquire_delay` streuen.
- Keine echte Netzwerk-Partition (Single-Node-`kind`); Semantik via API-Contention + Expiry validiert.

## §6 Gate-Status

```text
T-S1a Lease (K8s):     PASS
T-S2b Lease (K8s):     PASS (v1 acquire_delay, 5 runs)
P6 Z3:                 PASS
§6 GATE:               OPEN
Commit 2:              leader.py v2 + daemon renewal + Helm RBAC
```

## Reproduktion

```bash
kubectl config use-context kind-regime-shadow
kubectl apply -f manifests/infra-guardian/lease.yaml
make raas-regime-lease-t-s2b
```
