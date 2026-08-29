# Regime Swarm — Live Shadow Runbook

Monitoring-only Betrieb: Binance-WebSocket → Paper-WORM → A0/A2.5 + A1–A9. **`live_execution=false`** (hartcodiert, keine Orders).

Helm-Overlay: [`charts/regime-swarm/values-live-shadow.yaml`](../charts/regime-swarm/values-live-shadow.yaml)

## Voraussetzungen

| Punkt | Detail |
|-------|--------|
| Image | `Dockerfile.regime-swarm` mit PR #15+ (Live-Feed + Prometheus-Counter) |
| Netzwerk | Pod braucht **Egress** zu `wss://stream.binance.com:9443` (oder `LIVE_FEED_WS_URL`) |
| Workload | **StatefulSet** (nicht Deployment) — PVC unter `/data` |
| Default Prod | `LIVE_FEED_ENABLED=false` in `values.yaml` — Shadow ist expliziter Overlay |

## 1. Image bauen und laden

```bash
docker build -f Dockerfile.regime-swarm -t agentx-regime-swarm:live-shadow .

# Kind: Cluster-NAME ist regime-shadow (kubectl context: kind-regime-shadow)
kind load docker-image agentx-regime-swarm:live-shadow --name regime-shadow
```

Für **Code-Updates auf einem laufenden Cluster** ohne PVC-Re-Create siehe [§9 Strang D](#9-strang-d--image-update-pvc-sicher-post-pr-22).

## 2. Helm installieren (Shadow-Overlay)

```bash
helm upgrade --install regime-swarm charts/regime-swarm \
  -n trading --create-namespace \
  -f charts/regime-swarm/values-dev.yaml \
  -f charts/regime-swarm/values-live-shadow.yaml \
  --set image.repository=agentx-regime-swarm \
  --set image.tag=live-shadow \
  --set image.pullPolicy=IfNotPresent
```

Alternativ nur Makefile-Hilfsziel (gleiche Flags):

```bash
make raas-regime-swarm-live-shadow-install \
  IMAGE_REPO=agentx-regime-swarm IMAGE_TAG=live-shadow
```

## 3. Rollout prüfen

```bash
kubectl rollout status statefulset/regime-swarm -n trading --timeout=180s
kubectl get pods -n trading -l app.kubernetes.io/name=regime-swarm
kubectl logs -n trading regime-swarm-0 -f | grep -E 'swarm_daemon_start|cycle_error|INFRASTRUCTURE'
```

Erwartung im Start-Log: `"live_execution": false`, `"live_feed_enabled": true`, `"interval_s": 30`, `"worm_dir": "/data/worm/live"`, `"swarm_live_execution_env": "false"`.

### Charter-Check (4. Signal — vor Metriken)

Ebene 1 = Deklaration (ConfigMap/JSON), Ebene 2 = Durchsetzung (Code + WORM).

```bash
# ConfigMap → Pod-Env (soll SWARM_LIVE_EXECUTION=false zeigen)
kubectl exec -n trading regime-swarm-0 -- env | grep -E 'SWARM_LIVE_EXECUTION|LIVE_FEED_ENABLED'

# Image-JSON (Fallback-Deklaration im Container)
kubectl exec -n trading regime-swarm-0 -- cat /app/config/regime_swarm.json

# Start-Log (Code-Durchsetzung)
kubectl logs -n trading regime-swarm-0 | grep swarm_daemon_start | tail -1

# WORM-Zeile (jede SIGNAL-Zeile muss live_execution=false tragen)
kubectl exec -n trading regime-swarm-0 -- \
  tail -1 /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl \
  | grep -E '"live_execution": false|"order_send": false'
```

| Check | Erwartung |
|-------|-----------|
| `SWARM_LIVE_EXECUTION` | `false` (Pod startet nicht bei `true`) |
| `regime_swarm.json` | `"live_execution": false` |
| Start-Log | `"live_execution": false` |
| WORM-Zeile | `"live_execution": false`, `"order_send": false` |

Ohne `SWARM_LIVE_EXECUTION` in der ConfigMap gilt weiterhin Ebene 2 (Code-WORM-Gate) — der Pod läuft, aber die Deklaration ist im Env nicht sichtbar.

**Config-Priorität (ab Daemon-Fix):** ConfigMap/Env **schlägt** `/app/config/regime_swarm.json` für `CYCLE_INTERVAL_SECONDS`, `LIVE_FEED_*`, `SWARM_METRICS_PORT`. Kein JSON-Volume-Override nötig.

## 4. Metriken (Checkliste)

```bash
kubectl port-forward -n trading statefulset/regime-swarm 8080:8080 &
curl -s http://localhost:8080/health
curl -s http://localhost:8080/metrics | grep -E '^drift_counter|^risk_multiplier|^gate_block_counter|^swarm_cycles_total|^sizing_'
```

| Metrik | Erwartung (1–2 Tage Shadow) |
|--------|-----------------------------|
| `swarm_cycles_total` | Steigt ~alle 30 s (Leader-Pod) |
| `drift_counter{regime,type}` | Bewegt sich bei Regime-Klassifikation (nicht bei jedem Tick) |
| `risk_multiplier` | A8-Advisory-Multiplikator (Default 1.0, Soft-Adapt bei Unreliable) |
| `gate_block_counter{gate="A0"}` | Nur bei Flash/Spread-Verletzung — **nicht** dauerhaft >0 bei normalen Ticks |
| `sizing_gamma_current` | Serien vorhanden; **0 / `regime=none`** solange `POSITION_SIZING_ENABLED=false` (Strang D) |
| `sizing_regime_trigger_total` | Placeholder `0` bis Strang B (nach [Paper-Exit-Spec](PAPER_EXIT_ROUNDTRIP_SPEC.md)) |
| `sizing_gate_block_total` | Placeholder `0` bis Strang B |
| `swarm_up` | `1` solange Heartbeat frisch |

## 5. WORM-Live-Archiv

Pfad im Pod (Tenant `live`, Symbol lowercase):

```text
/data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl
```

```bash
kubectl exec -n trading regime-swarm-0 -- \
  ls -la /data/worm/live/live/paper/runs/ethusdt/
kubectl exec -n trading regime-swarm-0 -- \
  tail -3 /data/worm/live/live/paper/runs/ethusdt/paper_trades.worm.jsonl
```

Jede Zeile: `"live_execution": false`, `"action": "SIGNAL"`, `mark_price`.

## 6. Audit / Report

```bash
kubectl exec -n trading regime-swarm-0 -- tail -5 /data/reports/regime_drift_latest.json
kubectl logs -n trading regime-swarm-0 | grep regime_swarm_audit | tail -3
```

Erfolgskriterien:

- `infrastructure.infrastructure_healthy: true` bei normalen Marktphasen
- `drift_summary` mit `classified_regime` (nicht dauerhaft `NOT_COMPUTED`)
- Kein Pod-Restart-Loop, kein WS-Reconnect-Sturm in Logs

## 7. Rollback (Live-Feed aus)

**Schnell** — Feed aus, WORM-Pfad zurück auf Paper-Runs:

```bash
helm upgrade regime-swarm charts/regime-swarm -n trading \
  -f charts/regime-swarm/values-dev.yaml \
  --set config.LIVE_FEED_ENABLED=false \
  --reuse-values
```

**Vollständig** — ohne Live-Overlay:

```bash
helm upgrade regime-swarm charts/regime-swarm -n trading \
  -f charts/regime-swarm/values-dev.yaml \
  --reuse-values
```

PVC `/data/worm/live` bleibt erhalten (Archiv für Offline-Replay).

## 8. Offline-Replay (gespeicherte Live-WORM)

Kein separater Replay-Modus nötig — gleicher Orchestrator, lokales WORM-Verzeichnis:

```bash
# WORM vom Pod kopieren
kubectl cp trading/regime-swarm-0:/data/worm/live ./data/worm/live

# Offline-Drift (einmalig oder Verzeichnis)
PYTHONPATH=. python3 scripts/raas_regime_drift_monitor.py \
  --worm-dir data/worm/live
```

Oder Daemon lokal mit archiviertem WORM (Feed aus):

```bash
export SWARM_DATA_ROOT=./data
export LIVE_FEED_ENABLED=false
mkdir -p data/worm/paper_runs
cp -r data/worm/live/* data/worm/paper_runs/  # optional mirror
PYTHONPATH=. python3 scripts/run_regime_swarm_daemon.py \
  --config config/regime_swarm.json
```

## 9. Strang D — Image-Update (PVC-sicher, Post PR #22)

Nach Merge von **PR #22** (γ-Map, Trigger `regime_flag>=1`, `sizing_*`-Metriken im Daemon): neuen Code ins Cluster bringen, **ohne** Position Sizing zu aktivieren.

| Ziel | Detail |
|------|--------|
| Code | Daemon mit B0-Integration + Prometheus `sizing_*` |
| Config | `POSITION_SIZING_ENABLED=false` (explizit in `values-live-shadow.yaml`) |
| Metriken | `sizing_*` erscheinen in `/metrics`, bleiben bei **0** bis **Strang B** |

### 9.1 Image bauen und in Kind laden

```bash
git checkout main && git pull
docker build -f Dockerfile.regime-swarm -t agentx-regime-swarm:live-shadow .
kind load docker-image agentx-regime-swarm:live-shadow --name regime-shadow
```

### 9.2 Rollout (PVC-sicher — ohne `helm upgrade` bei PVC-Drift)

Wenn `helm upgrade` an **immutable `volumeClaimTemplates`** scheitert (z. B. bestehendes PVC 10Gi vs. Chart 5Gi), Image per `kubectl` setzen:

```bash
kubectl set image statefulset/regime-swarm -n trading \
  regime-swarm=agentx-regime-swarm:live-shadow
kubectl rollout restart statefulset/regime-swarm -n trading
kubectl rollout status statefulset/regime-swarm -n trading --timeout=180s
```

Container-Name prüfen falls abweichend:

```bash
kubectl get statefulset regime-swarm -n trading -o jsonpath='{.spec.template.spec.containers[*].name}'
```

### 9.3 ConfigMap-Env (optional, wenn Helm ohne PVC-Fehler)

Nur wenn `helm upgrade` durchläuft — sonst Env manuell patchen oder beim nächsten Cluster-Neuaufbau:

```bash
helm upgrade regime-swarm charts/regime-swarm -n trading \
  -f charts/regime-swarm/values-dev.yaml \
  -f charts/regime-swarm/values-live-shadow.yaml \
  --set image.repository=agentx-regime-swarm \
  --set image.tag=live-shadow \
  --reuse-values
```

### 9.4 Verifikation

```bash
kubectl exec -n trading regime-swarm-0 -- env | grep POSITION_SIZING
# Erwartung: POSITION_SIZING_ENABLED=false

kubectl port-forward -n trading statefulset/regime-swarm 8080:8080 &
curl -s http://localhost:8080/metrics | grep -E '^sizing_'
# Erwartung: sizing_gamma_current{regime="none"} 0, sizing_*_total{...} 0
```

**Nächster Schritt:** Nach Pod-Stabilität (Streaming-WORM-Fix) → [Paper Exit](PAPER_EXIT_ROUNDTRIP_SPEC.md) Kalibrierung §7 → [Strang B](POSITION_SIZING_REGIME_MAPPING.md#nach-implementierung).

### OOM / CrashLoopBackOff (2026-08-29)

**Ursache:** A2 lud die Live-WORM zweimal via `Path.read_text().splitlines()` (~670k Zeilen) → Peak >2 GiB → `OOMKilled` (Exit 137).

**Fix:** Streaming-Reader (`prototypes/raas_paper_trading/worm_io.py`) + Trailing-`SWARM_WORM_MAX_TICKS` (Default 10 000). Siehe PR `fix/worm-oom-streaming`.

```bash
# Nach Image-Rebuild / kind load / pod delete:
kubectl logs -n trading regime-swarm-0 | grep -E 'swarm_daemon_start|cycle_complete'
kubectl get pods -n trading   # READY 1/1
```

## Erfolgskriterien (Zusammenfassung)

| Kriterium | Erwartung |
|-----------|-----------|
| Zyklen stabil | Kein Crash; WS-Feed läuft im Hintergrund-Thread |
| Infra normal | Kein dauerhaftes `INFRASTRUCTURE_BLOCKED` bei regulären Ticks |
| Metriken leben | `swarm_cycles_total` ↑; `drift_counter` / `risk_multiplier` reagieren auf Drift-Pipeline |
| WORM wächst | JSONL-Datei unter `…/paper_trades.worm.jsonl` append-only |
| Charter | Jede WORM-Zeile `live_execution=false`; kein Order-Send |

## Siehe auch

- [`docs/REGIME_SWARM_INFRA_GATES.md`](REGIME_SWARM_INFRA_GATES.md) — A0/A2.5, Cluster-Smoke
- [`prototypes/raas_paper_trading/regime_swarm/README.md`](../prototypes/raas_paper_trading/regime_swarm/README.md) — Architektur
- [`docs/PAPER_EXIT_ROUNDTRIP_SPEC.md`](PAPER_EXIT_ROUNDTRIP_SPEC.md) — Exit-Voraussetzung für B2 / Strang B
- [`docs/POSITION_SIZING_REGIME_MAPPING.md`](POSITION_SIZING_REGIME_MAPPING.md) — γ-Map, Strang B/D
- [`docs/RaaS_REGIME_DRIFT_PREREG.md`](RaaS_REGIME_DRIFT_PREREG.md) — Pre-Reg v2
