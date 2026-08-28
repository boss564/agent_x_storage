# Regime Swarm — Infrastructure Gates (A0 / A2.5)

Monitoring-only privileged sub-agents that veto the A3–A8 drift pipeline when tick or transport integrity fails. Charter: `DEFENSIVE_CAUSAL_GROUNDING`, `live_execution=false`.

## Purpose

| Gate | Agent ID | Role |
|------|----------|------|
| Core sanity | **A0** | Last WORM tick → `GateInput` → `evaluate_gate()` (price, spread, flash move) |
| Transport boundary | **A2.5** | Latency budget, optional frame checksum, sequence gaps |

Both adapters call `services/fail_closed_gate/gate_core.py` — **no duplicated gate rules**.

## Mapping: Chaos strand vs production

| Chaos (P6-Trading) | Production swarm | Notes |
|--------------------|------------------|-------|
| G1 offline harness | A0 (core sanity) | Same `evaluate_gate()` kernel |
| G2 HTTP harness | A2.5 (transport) | Latency → `latency_spike` (CHAOS-02 pattern) |
| CHAOS-03 flash | A0 flash mapping | `exec_risk` / `cascade_risk` elevation |

Audit field names use `g0_core_sanity` and `g25_transport_boundary` to avoid confusion with Chaos G1/G2 labels.

## Fail-closed expectation

1. A2 ingest completes.
2. A0 runs on the last `mark_price` (reference = previous tick in the same WORM).
3. A2.5 runs when `transport_meta` is present on the latest SIGNAL row (or derived from `m7_latency_ms` / `seq_num`).
4. On any infrastructure fault: `status=INFRASTRUCTURE_BLOCKED`, `drift_summary=NOT_COMPUTED`, A5–A8 **not** executed, `order_send` remains false.
5. `evaluate_gate()` always returns `BLOCKED` for monitoring (`human_gate_open=false`). Infrastructure **pass** means reasons contain only `HUMAN_GATE_CLOSED` (no `INFRA_BLOCK_REASONS`).

## Audit schema (A9 extension)

```json
{
  "status": "INFRASTRUCTURE_BLOCKED",
  "infrastructure": {
    "g0_core_sanity": "PASSED | A0_BLOCKED: …",
    "g25_transport_boundary": "PASSED | SKIPPED (…) | A25_BLOCKED: …",
    "infrastructure_healthy": false
  },
  "drift_summary": "NOT_COMPUTED"
}
```

Complete cycles add the same `infrastructure` block with `infrastructure_healthy: true`.

## ConfigMap / environment

Helm `values.yaml`:

```yaml
infrastructureGates:
  enabled: true
  G0_MAX_PRICE_CHANGE_PCT: 20
  G0_MAX_SPREAD_PCT: 5
  G25_MAX_LATENCY_MS: 500
```

Rendered env (via `charts/regime-swarm/templates/configmap.yaml`):

| Key | Default |
|-----|---------|
| `SWARM_INFRA_GATES_ENABLED` | `true` |
| `SWARM_G0_MAX_PRICE_CHANGE_PCT` | `20` |
| `SWARM_G0_MAX_SPREAD_PCT` | `5` |
| `SWARM_G25_MAX_LATENCY_MS` | `500` |

Legacy aliases `G0_*` / `G25_*` / `INFRA_GATES_ENABLED` are also read by `InfraGatesConfig.from_env()`.

## Tests

```bash
PYTHONPATH=. python3 scripts/test_infrastructure_gates.py
# INFRASTRUCTURE_GATES_PASS

make raas-regime-swarm-infra-smoke
# REGIME_SWARM_INFRA_SMOKE_PASS — writes logs/worm/smoke_audit/*.json

docker compose -f docker-compose.regime-swarm-smoke.yml run --rm swarm-smoke
```

WORM format: JSONL `action=SIGNAL` + `mark_price` (not CSV). Flash fixture: 69 stable ticks + crash tick (−50% at G0=20%).

## Helm pod smoke (cluster)

Runs the same three WORM scenarios inside the cluster image, reads ConfigMap thresholds from env, and verifies **G0 propagation**: a −15% borderline tick must block or pass according to `infra_gates.g0_max_price_change_pct` (no internal threshold override).

```bash
helm upgrade --install regime-swarm charts/regime-swarm -n trading \
  --set smokeTest.enabled=true \
  --set infrastructureGates.enabled=true

helm test regime-swarm -n trading
kubectl logs -n trading job/regime-swarm-smoke
```

Local pod-style run (no cluster):

```bash
make raas-regime-swarm-helm-pod-smoke
# VERDICT: HELM_POD_SMOKE_PASS
```

ConfigMap threshold override (smoke Job reads **ConfigMap**, not Deployment env):

```bash
helm upgrade regime-swarm charts/regime-swarm -n trading --reuse-values \
  --set infrastructureGates.G0_MAX_PRICE_CHANGE_PCT=10
helm test regime-swarm -n trading
```

Or run the full runbook script:

```bash
chmod +x scripts/run_regime_swarm_cluster_smoke.sh
IMAGE_REPO=local/regime-swarm IMAGE_TAG=latest ./scripts/run_regime_swarm_cluster_smoke.sh full
```

Helm values (`smokeTest`):

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `false` | Renders `templates/smoke-job.yaml` as `helm.sh/hook: test` |
| `thresholdTest` | `true` | `propagation_test`: −15% tick enforced via ConfigMap G0 |
| `wormDir` | `/data/worm/smoke` | WORM fixtures written at Job start |
| `summaryPath` | `/data/audit/pod_smoke_summary.json` | Machine-readable summary |
| `deleteHookOnSuccess` | `true` | `false` keeps smoke Job pod until `ttlSecondsAfterFinished` (debug) |
| `ttlSecondsAfterFinished` | `600` | Job TTL after completion |

## Cluster-Test-Runbook (manuell)

Voraussetzungen: laufender Cluster (Minikube/Kind/Remote), `kubectl`, Helm 3.x, Image gebaut und im Cluster ladbar.

### 1. Image bereitstellen

```bash
docker build -f Dockerfile.regime-swarm -t local/regime-swarm:latest .
minikube image load local/regime-swarm:latest          # Minikube
# kind load docker-image local/regime-swarm:latest     # Kind
```

### 2. Installieren (G0=20 %)

```bash
kubectl create namespace trading --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install regime-swarm charts/regime-swarm -n trading \
  --set image.repository=local/regime-swarm \
  --set image.tag=latest \
  --set image.pullPolicy=IfNotPresent \
  --set smokeTest.enabled=true \
  --set infrastructureGates.enabled=true \
  --set infrastructureGates.G0_MAX_PRICE_CHANGE_PCT=20

kubectl rollout status deployment/regime-swarm -n trading
```

### 3. Baseline `helm test`

```bash
helm test regime-swarm -n trading --timeout 5m
SMOKE_POD=$(kubectl get pod -n trading -l job-name=regime-swarm-smoke -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n trading "$SMOKE_POD"
kubectl cp trading/"$SMOKE_POD":/data/audit/pod_smoke_summary.json ./smoke_summary_baseline.json
```

**Erwartung (Baseline):** `VERDICT: HELM_POD_SMOKE_PASS` in Logs; `pod_smoke_summary.json` mit `"status": "PASS"`.

| Szenario | Erwartung bei G0=20 % |
|----------|------------------------|
| `flash_crash` (−50 %) | infra block (`A0_BLOCKED`) |
| `valid_ticks` | infra OK (`INSUFFICIENT_WINDOWS`, pipeline partial) |
| `latency_spike` (600 ms) | infra block (`A25_BLOCKED`) |
| `propagation_test` (−15 %) | infra OK (enforced) |

Beispiel-Ausschnitt `pod_smoke_summary.json` (Baseline G0=20):

```json
{
  "schema": "regime_swarm_helm_pod_smoke_v1",
  "status": "PASS",
  "propagation_test": {
    "passed": true,
    "g0_max_price_change_pct": 20.0,
    "borderline_drop_pct": 15.0,
    "expect_infra_block": false,
    "detail": "propagation: G0=20.0 -15% → infra_ok (enforced)"
  }
}
```

Override (G0=10) — gleicher Test, andere Durchsetzung:

```json
"propagation_test": {
  "passed": true,
  "g0_max_price_change_pct": 10.0,
  "expect_infra_block": true,
  "status": "INFRASTRUCTURE_BLOCKED",
  "detail": "propagation: G0=10.0 -15% → BLOCK (enforced)"
}
```

### 4. ConfigMap-Override (G0=10 %)

**Wichtig:** Der Smoke-**Job** liest Schwellwerte aus der **ConfigMap** (`envFrom.configMapRef`), nicht aus dem Deployment. Override daher per `helm upgrade` oder `kubectl patch configmap`, nicht nur `kubectl set env deployment/...`.

```bash
helm upgrade regime-swarm charts/regime-swarm -n trading --reuse-values \
  --set infrastructureGates.G0_MAX_PRICE_CHANGE_PCT=10
kubectl rollout status deployment/regime-swarm -n trading

helm test regime-swarm -n trading --timeout 5m
SMOKE_POD=$(kubectl get pod -n trading -l job-name=regime-swarm-smoke -o jsonpath='{.items[0].metadata.name}')
kubectl cp trading/"$SMOKE_POD":/data/audit/pod_smoke_summary.json ./smoke_summary_override.json
```

**Erwartung (Override):** `HELM_POD_SMOKE_PASS`; `propagation_test.expect_infra_block: true`; `status: INFRASTRUCTURE_BLOCKED` für −15 %.

### 5. Automatisierung (optional)

```bash
./scripts/run_regime_swarm_cluster_smoke.sh full
# Artefakte: logs/cluster_smoke/smoke_summary_baseline.json, smoke_summary_override.json
```

### 6. Aufräumen

```bash
helm uninstall regime-swarm -n trading
kubectl delete job regime-swarm-smoke -n trading --ignore-not-found=true
```

### Cluster-Validierung (nach erfolgreichem Lauf eintragen)

| Datum | G0 (ConfigMap) | helm test | propagation −15 % | Fazit |
|-------|----------------|-----------|-------------------|-------|
| 2026-08-28 | 20 % | PASS | infra OK (enforced) | ✅ kind-regime-shadow |
| 2026-08-28 | 10 % | PASS | BLOCK (enforced) | ✅ Override wirksam |

### CI (optional)

Scheduled Kind regression: `.github/workflows/cluster-smoke-cron.yml` (weekly + `workflow_dispatch`). Uses `scripts/run_regime_swarm_cluster_smoke.sh full` and uploads `logs/cluster_smoke/` artifacts.

## Code layout

```
prototypes/raas_paper_trading/regime_swarm/gates/
├── core_sanity_adapter.py   # A0
├── transport_boundary.py    # A2.5
├── config.py
└── common.py                # INFRA_BLOCK_REASONS, InfraGateResult
```

Orchestrator hook: `RegimeSwarmOrchestrator._run_infrastructure_gates()` before A3 in `run_cycle()`.
