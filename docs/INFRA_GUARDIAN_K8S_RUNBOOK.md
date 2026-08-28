# Infra-Guardian K8s Runbook — kind Shadow-Cluster

**Stand:** 2026-08-28  
**Branch:** `feature/lease-k8s-gate`  
**Parent:** `docs/INFRA_GUARDIAN_SWARM_v0.md`

## Voraussetzungen

| Tool | Zweck |
|------|-------|
| Docker Desktop | Image-Build + kind-Node |
| `kind` | Lokaler K8s-Cluster |
| `kubectl` | Cluster-Zugriff |
| `helm` | Chart-Deploy |

## 1. Cluster erstellen

```bash
kind create cluster --name regime-shadow --wait 5m
kubectl config use-context kind-regime-shadow
```

## 2. Image bauen und laden (wichtig: Chart-Tag)

Der Helm-Chart nutzt `appVersion: "2.0.0"` → Image-Tag **`2.0.0`**, nicht nur `:latest`.

```bash
cd /Volumes/THX_OS_ULTRA\ -\ Data/Users/olivermueller/agent_x_storage

make raas-regime-swarm-build
docker tag agentx-regime-swarm:latest agentx-regime-swarm:2.0.0
kind load docker-image agentx-regime-swarm:2.0.0 --name regime-shadow
```

**Häufiger Fehler:** Nur `:latest` geladen → `ImagePullBackOff` auf `agentx-regime-swarm:2.0.0`.

## 3. Shadow-Stack deployen

```bash
bash scripts/regime_swarm_shadow_cluster.sh up
kubectl get pods -n regime-swarm-shadow
```

Erwartung:

- `regime-swarm-shadow-0` → Leader (`is_leader: true`)
- `regime-swarm-shadow-1` → Standby (`standby_tick`)

## 4. Lease-Objekt (T-S1a/T-S2b)

```bash
kubectl apply -f manifests/infra-guardian/lease.yaml
kubectl get lease -n regime-swarm-shadow
```

Alternativ via Helm-Overlay (`values-shadow.yaml`: `lease.enabled: true`):

```bash
helm upgrade --install regime-swarm-shadow charts/regime-swarm \
  -n regime-swarm-shadow -f charts/regime-swarm/values-shadow.yaml
```

## 5. Tests

```bash
make raas-regime-lease-t-s1a    # Split-Brain Lease-Race (K8s)
make raas-regime-lease-t-s2b    # Silent Hang / Lease expiry failover
```

## 6. Teardown

```bash
bash scripts/regime_swarm_shadow_cluster.sh down
kind delete cluster --name regime-shadow
```

## 7. Failover-Drills (vor Push klären)

### Drill 1 — `kubectl delete pod` (StatefulSet)

**Kein Failover-Test.** Der STS erzeugt denselben Pod-Namen neu; der Standby behält seine Identität nicht, der gelöschte Pod kommt mit gleicher Ordinalität zurück und erneuert die Lease sofort.

### Drill 2 — Scale auf 1 (geordnete Abmeldung)

Zwei **verschiedene** Szenarien — nicht vermischen:

| Szenario | Mechanismus | Typische Zeit | Referenz |
|----------|-------------|---------------|----------|
| **Stillen Hänger** (T-S2b) | Lease läuft ab (`renewTime` + 15 s), kein `release()` möglich | ~15 s + `acquire_delay` ≤ 1 s | `make raas-regime-lease-t-s2b` |
| **Geordnetes Scale-Down** | `preStop` sendet SIGTERM → `request_shutdown()` → sofortiges `release()` | Sekunden (Holder leer, dann Acquire) | Forensic unten |

**Wichtig:** Der alte `preStop: sleep 10` blockierte SIGTERM (Kubelet sendet SIGTERM erst **nach** preStop). Während des Sleeps erneuerte der Leader die Lease weiter — das erklärt widersprüchliche Drill-2-Zeiten (~3 s vs. ~10–15 s).

**Release-Pfad (ab Commit 2 Fix):**

1. `preStop`: `kill -TERM 1; sleep 20` — Shutdown sofort starten
2. `request_shutdown()` → `_release_lease_if_holder()` — Lease **vor** Loop-Exit freigeben
3. `finally` → idempotentes `_release_lease_if_holder()`

**Forensic wiederholen:**

```bash
make raas-regime-swarm-build
docker tag agentx-regime-swarm:latest agentx-regime-swarm:2.0.0
kind load docker-image agentx-regime-swarm:2.0.0 --name regime-shadow
helm upgrade --install regime-swarm-shadow charts/regime-swarm \
  -n regime-swarm-shadow -f charts/regime-swarm/values-shadow.yaml
python3 scripts/regime_swarm_lease_failover_forensic.py
```

Erwartung: `verdict: RELEASE_OR_EMPTY_TAKEOVER`, `renew_age_s` beim Takeover **< 15 s** (Holder war leer nach Release, nicht abgelaufen).

**Split-Brain-Risiko:** Nur wenn `try_acquire` eine **nicht abgelaufene** fremde Lease überschreibt (`STEAL_NON_EXPIRED_SUSPECT`). `try_acquire` blockiert das explizit (`holder != identity and not expired` → `False`).

## Referenzen

- `docs/INFRA_GUARDIAN_LEASE_T_S1A_ERGEBNIS.md` — T-S1a Ergebnis
- `docs/INFRA_GUARDIAN_LEASE_T_S2B_ERGEBNIS.md` — T-S2b Ergebnis + §6 Gate OPEN
- `logs/infra_guardian/lease_t_s1a_latest.json` — Maschinenlesbarer Report
