# AstroCore Hook — Regime-Swarm Image & Deploy (P3)

Read-only Class-C liquidation coupling hook for the regime-swarm pod.
**Charter:** `diagnostic_only` · `live_execution=false` · D1b verdict cap for non-neo4j.

## Voraussetzungen

- Pod-Live-Test grün (WORM ingest, `prov=worm`, verdict `SYNTHETIC_ONLY`)
- Cluster-Health-Check bestanden
- Image-Tag: `astrocore-hook-v1` (oder eigenes)

## Schnellstart (empfohlen — PVC-sicher)

Auf Live-Shadow-Clustern mit bestehendem StatefulSet und PVC **nicht** `helm upgrade` auf
den StatefulSet anwenden (SSA-Konflikt mit früherem `kubectl set image` + immutable
`volumeClaimTemplates`). Stattdessen:

```bash
# 1. Image bauen + in Kind laden
make raas-regime-swarm-astrocore-hook-build
kind load docker-image agentx-regime-swarm:astrocore-hook-v1 --name regime-shadow

# 2. ConfigMap + Image + Rollout (Hook OFF)
make raas-regime-swarm-astrocore-hook-apply

# 3. Smoke
kubectl exec -n trading regime-swarm-0 -- \
  env ASTROCORE_DATA_SOURCE=worm python3 scripts/helm_astrocore_hook_smoke.py

# 4. Hook aktivieren
make raas-regime-swarm-astrocore-hook-apply ASTROCORE_HOOK_ENABLED=true
```

Makefile-Variablen (optional):

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `RAAS_NS` | `trading` | Kubernetes-Namespace |
| `RAAS_IMAGE_REPO` | `agentx-regime-swarm` | Image-Repository |
| `RAAS_IMAGE_TAG` | `astrocore-hook-v1` | Image-Tag |
| `ASTROCORE_HOOK_ENABLED` | `false` | ConfigMap-Schalter |

---

## 1. Image bauen

```bash
make raas-regime-swarm-astrocore-hook-build
```

Enthält:

- `agents_b2g/astrocore_hook/` (client, raas_ingest, verdict, neo4j_reader)
- `imports/cherrystudio/astrocore/` (test_liquidation_coupling, astrocore_coupling, CLI)
- `scripts/helm_astrocore_hook_smoke.py`

Build-Smoke im Dockerfile:

```bash
python3 -c "from agents_b2g.astrocore_hook import AstrocoreHookClient, parse_gap_logs"
```

## 2. Image in Kind/Cluster laden

```bash
kind load docker-image agentx-regime-swarm:astrocore-hook-v1 --name regime-shadow
```

Bei Registry-Cluster: `docker push` + Tag in `RAAS_IMAGE_TAG` setzen.

## 3. Deploy — primär: `make apply` (PVC-sicher)

### 3a. Nur ConfigMap (Helm-Template, kein StatefulSet-Touch)

```bash
make raas-regime-swarm-astrocore-hook-config
```

Rendert `charts/regime-swarm/values-astrocore-hook.yaml` in die ConfigMap
(`regime-swarm-config`) — inkl. AstroCore-Env, ohne PVC/Image zu ändern.

### 3b. Vollständiger Rollout

```bash
make raas-regime-swarm-astrocore-hook-apply
# Hook einschalten:
make raas-regime-swarm-astrocore-hook-apply ASTROCORE_HOOK_ENABLED=true
```

Intern:

1. ConfigMap via `helm template … --show-only templates/configmap.yaml | kubectl apply`
2. `kubectl set image statefulset/regime-swarm …`
3. `kubectl patch configmap … ASTROCORE_HOOK_ENABLED`
4. `kubectl rollout restart` + `rollout status`

### 3c. Helm `upgrade` (optional — oft blockiert)

```bash
make raas-regime-swarm-astrocore-hook-install
```

**Warnung:** Scheitert typischerweise auf Live-Shadow-Clustern mit:

- SSA-Konflikt: `conflict with "kubectl-set"` auf `.spec.template.spec.containers[].image`
- Immutable field: `spec.volumeClaimTemplates` (5Gi overlay vs. 10Gi base)

Nur für **frische** Installs ohne prior `kubectl set image` geeignet.
ConfigMap-only als Fallback:

```bash
helm template regime-swarm charts/regime-swarm \
  -f charts/regime-swarm/values-dev.yaml \
  -f charts/regime-swarm/values-live-shadow.yaml \
  -f charts/regime-swarm/values-astrocore-hook.yaml \
  --show-only templates/configmap.yaml | kubectl apply -f -
```

---

## 4. Hook-Smoke im Pod

```bash
make raas-regime-swarm-astrocore-hook-smoke   # lokal
# oder im Pod:
kubectl exec -n trading regime-swarm-0 -- \
  env ASTROCORE_DATA_SOURCE=worm python3 scripts/helm_astrocore_hook_smoke.py
```

Erwartung (Stand Rollout 2026-08-30):

```json
{
  "status": "PASS",
  "data_provenance": "worm",
  "verdict": "SYNTHETIC_ONLY",
  "raw_verdict": "CLUSTER_DETECTED",
  "events_read": 90
}
```

## 5. Hook aktivieren

```bash
make raas-regime-swarm-astrocore-hook-apply ASTROCORE_HOOK_ENABLED=true
```

Pod-Env nach Restart:

```bash
kubectl exec -n trading regime-swarm-0 -- env | grep ASTROCORE
```

---

## Rückrollen

```bash
make raas-regime-swarm-astrocore-hook-rollback
# oder manuell:
kubectl patch configmap regime-swarm-config -n trading \
  --type merge -p '{"data":{"ASTROCORE_HOOK_ENABLED":"false"}}'
kubectl set image statefulset/regime-swarm \
  regime-swarm=agentx-regime-swarm:xv-observer-v1 -n trading
kubectl rollout restart statefulset/regime-swarm -n trading
```

---

## Env-Referenz

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `ASTROCORE_HOOK_ENABLED` | `false` | ConfigMap-Schalter (Daemon-Integration später) |
| `ASTROCORE_DATA_SOURCE` | `worm` | `worm` \| `neo4j` \| `synthetic` |
| `RAAS_AUDIT_DIR` | `/data/audit` | Gap-JSONL-Verzeichnis |
| `ASTROCORE_NEO4J_LOOKBACK_DAYS` | `7` | Lookback-Fenster |
| `ASTROCORE_FUNDING_PERIOD_S` | `28800` | 8h Funding-Periode (D3) |
| `ASTROCORE_STRICT` | `false` | Hard-Fail: echte Events **und** `NEO4J_USER_READ` (CI / P4-Tor) |
| `NEO4J_URI_READ` | — | Bolt-URI für den Hook (vor `NEO4J_URI`) |
| `NEO4J_USER_READ` | — | **Pflicht vor P4:** User mit Rolle `reader` |
| `NEO4J_PASS_READ` | — | Passwort des Reader-Users |

## Neo4j-Lese-Benutzer (vor P4)

Die Token-Sperrliste fängt versehentliche `SET`/`CREATE` im eigenen Code früh. APOC/DROP und jede künftige Query deckt sie nicht ab. **Die verlässliche Schicht ist der Server:**

1. Driver: `READ_ACCESS` + `execute_read` (bereits verdrahtet).
2. Login: eigener User ohne Schreibrechte — **nicht** der Admin `neo4j`.

Ops (einmal, als Admin — nicht aus dem Hook):

```cypher
CREATE USER astrocore_reader IF NOT EXISTS SET PASSWORD $password CHANGE NOT REQUIRED;
GRANT ROLE reader TO astrocore_reader;
```

Env am Hook:

```bash
export NEO4J_URI_READ=bolt://neo4j:7687
export NEO4J_USER_READ=astrocore_reader
export NEO4J_PASS_READ=...   # nicht committen
```

Ohne `NEO4J_USER_READ` warnt `resolve_neo4j_read_auth()` — Session ist trotzdem READ, das Login kann aber noch schreiben.

### P4-Lab (lokal, isoliert)

Throwaway-Container auf **127.0.0.1:17687** — **nicht** Host-Enterprise `:7687`, nicht Compose-Neo4j, nicht den Live-Cluster.

```bash
make raas-p4-lab-up          # neo4j:5.26-community, Bolt :17687
make raas-p4-lab-smoke        # Dual-Schema-Seed + Hook data_source=neo4j
make raas-p4-lab-listener    # nur sinnvoll, wenn fstream Frames liefert (siehe unten)
make raas-p4-lab-down
```

Das Lab-Skript lehnt Bolt `:7687` ohne `--allow-default-port` ab. Community Edition hat in der Regel **kein** `ROLE reader` — der Smoke dokumentiert das und fährt den Hook trotzdem über `READ_ACCESS`. Live bleibt `ASTROCORE_DATA_SOURCE=worm`.

**Stand 2026-08-30 — vorbereitet, nicht live.** Dual-Schema-Adapter + Lab-Smoke (`provenance=neo4j`) sind grün. `ROLE reader` braucht Enterprise. Live-Force-Orders fehlen: `fstream.binance.com` liefert von Lab-Host **und** Cluster keine WS-Frames; Spot `stream.binance.com:9443` läuft an beiden Orten (stdlib-Client wie Live-Shadow). Diagnose: `scripts/p4_ws_path_probe.py`. Nicht mit `P4_LISTENER_SECONDS` wiederholen. Cluster-Quelle bleibt `worm`, bis ein Liquidations-Feed Frames liefert.

## Manueller Hook-Aufruf

```bash
kubectl exec -n trading regime-swarm-0 -- \
  env ASTROCORE_DATA_SOURCE=worm python3 -c "
from agents_b2g.astrocore_hook import AstrocoreHookClient
c = AstrocoreHookClient(data_source='worm', audit_dir='/data/audit')
s = c.to_evaluator_signal()
print('astrocore=%s R=%.3f prov=%s' % (s['verdict'], s['R'], s['data_provenance']))
"
```

---

## Stündliche RT-Verifikation (CronJob :14 UTC)

Automatischer Check für **W_xv** (v1+v2 Heartbeats), **Feed-Gap (W)** und **AstroCore Hook**
— ohne `kubectl exec`/`make` im laufenden Betrieb.

### Manuell (sofort)

```bash
make raas-swarm-hourly-rt-check
# oder im Pod:
kubectl exec -n trading regime-swarm-0 -- python3 scripts/raas_hourly_rt_check.py
```

Erwartung nach erfolgreichem :14-Tick:

| Prüfung | Erwartung |
|---------|-----------|
| `cross_venue_v1` / `v2` | `ACTIVE`, `last_ts` ≈ :14 |
| `feed_gap_w` | `ACTIVE`, `fsm_state=ALIVE` (Writer-Heartbeat — nicht Paper-Ticks) |
| `paper_tick` | `PASS`: `last_tick_ts` aus `feed_gap_state.json` (Fallback: `heartbeat.last_tick_ts`) jünger als `HOURLY_RT_PAPER_TICK_MAX_AGE_S` (Default 300 s). **Nicht** `heartbeat.ts`. |
| `astrocore_hook` | `prov=worm`, `verdict=SYNTHETIC_ONLY` |

### CronJob aktivieren (PVC read-only)

Voraussetzung: Image enthält `scripts/raas_hourly_rt_check.py` (Tag `astrocore-hook-v1`+).

```bash
make raas-swarm-hourly-rt-cron-enable RAAS_IMAGE_TAG=astrocore-hook-v1
kubectl get cronjob -n trading regime-swarm-hourly-rt
```

- Schedule: `14 * * * *` (UTC)
- Mount: PVC `data-regime-swarm-0` (append-only Log in `/data/audit/hourly_rt_checks.jsonl`)
- Deaktivieren: `make raas-swarm-hourly-rt-cron-disable`

Nach Image-Rebuild ohne Script im Container zuerst Image laden + Pod/CronJob-Tag angleichen.

---

## Alerting (Stufe 2 — Telegram)

Automatische Benachrichtigung bei:

| Event | Auslöser |
|-------|----------|
| RT-Check FAIL | CronJob `:14` — Heartbeat >65 Min., Feed-Gap, AstroCore-Fehler |
| Pod-Restart | Daemon-Start — vorheriger Boot-Marker auf PVC |
| Manuell | `make raas-swarm-alert-test` / `make raas-swarm-telegram-alert` |
| Health STALE / Pod-Down | `make raas-swarm-health` → `scripts/telegram_alert.py` (lokal `.env`) |

Secret aus Projekt-`.env` (Chat-ID-Fallback `ADMIN_TELEGRAM_USER_ID`):

```bash
# Token nicht in die Shell-History tippen — Make liest die Variablen aus der Umgebung
set -a && source .env && set +a
make raas-swarm-alerting-secret \
  TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-$ADMIN_TELEGRAM_USER_ID}"
```

Lokal / Cron:

```bash
python3 scripts/telegram_alert.py --from-health
# oder
make raas-swarm-health          # sendet bei STALE/Pod-Down
make raas-swarm-health-no-alert # nur Tabelle
```

### Einrichtung (PVC-sicher)

1. **Telegram Bot** (@BotFather) → `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
2. **Secret** (nicht committen):

```bash
make raas-swarm-alerting-secret \
  TELEGRAM_BOT_TOKEN='123456:ABC...' \
  TELEGRAM_CHAT_ID='987654321'
```

3. **Image** mit `scripts/raas_alert.py` (Tag `astrocore-hook-v1`+), Kind laden, Pod restart
4. **Aktivieren:**

```bash
make raas-swarm-alerting-apply RAAS_IMAGE_TAG=astrocore-hook-v1
make raas-swarm-alert-test
```

Rollback (Alert-Flags weg, Telegram-Env vom STS, Cron ohne Alert-Overlay):

```bash
make raas-swarm-alerting-rollback
```

Env (ConfigMap): `RAAS_ALERT_ENABLED=true`, `RAAS_ALERT_COOLDOWN_S=3600`  
`values-alerting.yaml` setzt `ASTROCORE_HOOK_ENABLED=true`, damit `make raas-swarm-alerting-config` den Hook nicht wieder ausschaltet.  
Dedup: gleicher Fehler max. 1×/Stunde. Optional: `SLACK_WEBHOOK_URL` im Secret.

Tests lokal: `make raas-swarm-alerting-test-local`

---

## Roadmap

| Phase | Status | Inhalt |
|-------|--------|--------|
| P3 WORM-Ingest | **done** | Gap-JSONL → Hook-Envelope, D1b cap |
| Image + ConfigMap | **done** | `astrocore-hook-v1`, PVC-sicherer Apply |
| Ops-Health-Probe | **done** | `swarm_health.py` kubectl-exec, skipbar |
| Alerting (Telegram) | **done** | `raas_alert.py`, RT-Cron + Pod-Restart, Dedup |
| Daemon-Integration | **backlog** | Erst sinnvoll bei `provenance=neo4j` oder bewusstem Diagnostic-Monitor |
| Neo4j-Ingest | **prepared / not live** | Adapter + Lab-Smoke grün; `fstream` WS tot (Spot ok); Cluster bleibt `worm` |

## Ops-Health (`make raas-swarm-health`)

`scripts/swarm_health.py` fragt den Hook **optional** per `kubectl exec` ab, wenn
`regime-swarm-0` Running/Ready ist. Kein Daemon-Umbau. Skip:

```bash
ASTROCORE_HEALTH_PROBE=false make raas-swarm-health
```

Erwartete Zeile:

```
AstroCore hook → status=PASS  prov=worm  verdict=SYNTHETIC_ONLY  events=…
```

## Hinweise

- `emergence_adapter` / `wirtschaft/` sind **nicht** im regime-swarm-Image — Hook läuft standalone oder per `exec`/Smoke.
- `ASTROCORE_HOOK_ENABLED=true` in der ConfigMap hat **noch keine** Daemon-Wirkung; Signal ist per Smoke/Exec abrufbar.
- D1b: `worm` und `gap_synthetic` liefern max. `SYNTHETIC_ONLY`, auch bei signifikanter Rayleigh-Statistik.
