# Infra-Guardian — Lease Failover Drills (Ergebnis)

**Stand:** 2026-08-28  
**Cluster:** `kind-regime-shadow` / `regime-swarm-shadow`  
**Branch:** `feature/lease-k8s-gate`

## Zusammenfassung

Die widersprüchlichen Failover-Zeiten (**~3 s** im ersten Drill 2 vs. **~15,32 s** im T-S2b-Harness) beschreiben **zwei verschiedene Szenarien** — kein Messfehler, aber der erste Drill war **methodisch unzureichend dokumentiert**.

| Szenario | Auslöser | Mechanismus | Gemessene Zeit | Status |
|----------|----------|-------------|----------------|--------|
| **Drill 1** | `kubectl delete pod` auf STS | Kein Failover — gleiche Pod-Identität kehrt zurück | n/a | Dokumentiert (kein Failover-Test) |
| **Drill 2 (alt, ~3 s)** | Scale→1 bei **bereits pod-0 Leader** | Kein echter Failover — nur Standby entfernt | ~3 s (irreführend) | **Invalidiert** als Failover-Nachweis |
| **Drill 2 (forensic, post-fix)** | Scale→1, **pod-1 Leader** | `preStop` → SIGTERM → `release()` → leerer Holder → Acquire | **~12 s** bis pod-0, `renew_age` **0,36 s** | `RELEASE_OR_EMPTY_TAKEOVER` |
| **T-S2b Silent Hang** | Harness: Renewal stoppt, kein Release | Lease-Expiry + `acquire_delay` | ~15 s + ≤1 s | `T_S2B_LEASE_PASS` |

## Root Cause: fehlender sofortiger Release-Pfad

**Vor dem Fix:**

- `release()` existierte, wurde aber nur im `finally` von `main_loop()` aufgerufen — **nach** Loop-Exit.
- `request_shutdown()` setzte nur ein Event; kein Lease-Release bei SIGTERM.
- `preStop: sleep 10` — Kubelet sendet SIGTERM **erst nach** preStop; während des Sleeps erneuerte der Leader die Lease weiter.

**Nach dem Fix (dieser Commit):**

1. `preStop`: `kill -TERM 1; sleep 20` — Shutdown sofort starten
2. `request_shutdown()` → `_release_lease_if_holder()` — Lease **sofort** freigeben
3. `finally` → idempotentes `_release_lease_if_holder()`
4. Audit-Events: `lease_released`, `lease_release_patch`, `lease_acquired` (via `empty` / `expired`)

## Forensic Drill 2 (post-fix)

**Skript:** `scripts/regime_swarm_lease_failover_forensic.py`  
**Report:** `logs/infra_guardian/lease_failover_forensic_latest.json`

**Setup:** 2 Replicas → Lease geleert → **pod-1** als Leader erzwungen → Scale auf 1 (pod-1 wird terminiert, pod-0 bleibt).

**Ergebnis:**

```json
{
  "verdict": "RELEASE_OR_EMPTY_TAKEOVER",
  "holder_empty_seen_early": true,
  "takeover": {
    "t_s": 11.84,
    "holder": "regime-swarm-shadow-0",
    "renew_age_s": 0.361,
    "acquire_time": "2026-08-28T09:21:55.886082Z"
  }
}
```

**Interpretation:**

- Holder wurde **leer** (Release), bevor pod-0 übernahm — **kein** Überschreiben einer gültigen fremden Lease (`renew_age` beim Takeover ≪ 15 s).
- Failover-Dauer ~12 s = preStop-SIGTERM-Pfad + Drain — **nicht** die 3 s des ersten Drills.
- **Split-Brain bei Partition:** `try_acquire` blockiert explizit, wenn `holder != identity and not expired` → kein stiller Steal.

## I1 und Partition

Ein I1-PASS bei Scale-Down **beweist nicht** automatisch Partition-Sicherheit. Getrennt zu halten:

- **Geordnete Abmeldung:** Release-Pfad (oben) — schneller Failover, Holder leer
- **Stiller Hänger / Partition:** Nur Expiry (T-S2b) — ~15 s, kein Release möglich

## Empfehlung vor Push

1. Fix (Release bei SIGTERM + preStop) ist **implementiert und forensisch verifiziert**
2. Runbook §7 dokumentiert beide Szenarien (`docs/INFRA_GUARDIAN_K8S_RUNBOOK.md`)
3. Push mit beiden Failover-Zeiten **und Bedingungen** — keine nackte „3 s“-Zahl mehr

## Referenzen

- `docs/INFRA_GUARDIAN_LEASE_T_S2B_ERGEBNIS.md` — Silent Hang
- `docs/INFRA_GUARDIAN_K8S_RUNBOOK.md` — Drills + Release-Pfad
- `scripts/regime_swarm_lease_failover_forensic.py` — reproduzierbarer Forensic-Drill
