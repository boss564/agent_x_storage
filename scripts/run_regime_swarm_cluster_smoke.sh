#!/usr/bin/env bash
# Cluster smoke runbook — infra gates A0/A2.5 (helm test hook).
# Charter: DEFENSIVE_CAUSAL_GROUNDING · live_execution=false
#
# Usage:
#   ./scripts/run_regime_swarm_cluster_smoke.sh baseline   # G0=20 via Helm/ConfigMap
#   ./scripts/run_regime_swarm_cluster_smoke.sh override   # G0=10 ConfigMap upgrade + re-test
#   ./scripts/run_regime_swarm_cluster_smoke.sh full       # baseline then override
#
# Env overrides:
#   NAMESPACE=trading RELEASE=regime-swarm IMAGE_REPO=local/regime-swarm IMAGE_TAG=latest

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-trading}"
RELEASE="${RELEASE:-regime-swarm}"
IMAGE_REPO="${IMAGE_REPO:-local/regime-swarm}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CHART="${CHART:-$ROOT/charts/regime-swarm}"
TIMEOUT="${HELM_TEST_TIMEOUT:-5m}"
OUT_DIR="${OUT_DIR:-$ROOT/logs/cluster_smoke}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

helm_install() {
  local g0="$1"
  log "helm upgrade --install $RELEASE (G0=$g0%) namespace=$NAMESPACE"
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install "$RELEASE" "$CHART" \
    -n "$NAMESPACE" \
    --set "image.repository=$IMAGE_REPO" \
    --set "image.tag=$IMAGE_TAG" \
    --set image.pullPolicy=IfNotPresent \
    --set smokeTest.enabled=true \
    --set smokeTest.deleteHookOnSuccess=false \
    --set infrastructureGates.enabled=true \
    --set "infrastructureGates.G0_MAX_PRICE_CHANGE_PCT=$g0"
  kubectl rollout status "statefulset/$RELEASE" -n "$NAMESPACE" --timeout=180s
}

helm_test() {
  local label="$1"
  local out_json="$OUT_DIR/${label}.json"
  local log_file="$OUT_DIR/${label}.log"
  mkdir -p "$OUT_DIR"

  log "helm test $RELEASE (timeout $TIMEOUT)"
  if ! helm test "$RELEASE" -n "$NAMESPACE" --timeout "$TIMEOUT" 2>&1 | tee "$log_file"; then
    die "helm test failed — see $log_file"
  fi

  local pod=""
  pod="$(kubectl get pod -n "$NAMESPACE" -l "job-name=${RELEASE}-smoke" \
    --sort-by=.metadata.creationTimestamp \
    -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || true)"

  if [[ -n "$pod" ]]; then
    kubectl logs -n "$NAMESPACE" "$pod" >>"$log_file" 2>&1 || true
    if kubectl cp "$NAMESPACE/$pod:/data/audit/pod_smoke_summary.json" "$out_json" 2>/dev/null; then
      log "copied pod_smoke_summary.json from $pod"
    fi
  fi

  if [[ ! -f "$out_json" ]]; then
    log "extract summary JSON from captured logs"
    python3 - "$log_file" "$out_json" <<'PY'
import json, re, sys
log_path, out_path = sys.argv[1], sys.argv[2]
text = open(log_path, encoding="utf-8").read()
matches = list(re.finditer(r'\{\s*"schema": "regime_swarm_helm_pod_smoke_v1"', text))
if not matches:
    sys.exit("pod summary JSON not found in logs")
chunk = text[matches[-1].start():]
depth = 0
end = 0
for i, ch in enumerate(chunk):
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break
summary = json.loads(chunk[:end])
open(out_path, "w", encoding="utf-8").write(json.dumps(summary, indent=2) + "\n")
PY
  fi

  if grep -q '"status": "PASS"' "$out_json" && grep -q 'VERDICT: HELM_POD_SMOKE_PASS' "$log_file"; then
    log "$label: PASS"
  else
    die "$label: FAIL — see $out_json and $log_file"
  fi
}

show_configmap_g0() {
  kubectl get configmap "${RELEASE}-config" -n "$NAMESPACE" \
    -o jsonpath='{.data.SWARM_G0_MAX_PRICE_CHANGE_PCT}{"\n"}' 2>/dev/null || true
}

run_baseline() {
  helm_install 20
  log "ConfigMap SWARM_G0_MAX_PRICE_CHANGE_PCT=$(show_configmap_g0)"
  helm_test "smoke_summary_baseline"
}

run_override() {
  log "ConfigMap override: G0=10 (helm upgrade — smoke Job reads ConfigMap, not Deployment env)"
  helm upgrade "$RELEASE" "$CHART" -n "$NAMESPACE" --reuse-values \
    --set infrastructureGates.G0_MAX_PRICE_CHANGE_PCT=10
  kubectl rollout status "statefulset/$RELEASE" -n "$NAMESPACE" --timeout=180s
  log "ConfigMap SWARM_G0_MAX_PRICE_CHANGE_PCT=$(show_configmap_g0)"
  helm_test "smoke_summary_override"
}

main() {
  need_cmd kubectl
  need_cmd helm
  local mode="${1:-full}"
  case "$mode" in
    baseline) run_baseline ;;
    override) run_override ;;
    full) run_baseline; run_override ;;
    *) die "usage: $0 {baseline|override|full}" ;;
  esac
  log "artifacts: $OUT_DIR"
}

main "$@"
