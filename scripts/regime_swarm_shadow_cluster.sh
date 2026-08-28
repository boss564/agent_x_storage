#!/usr/bin/env bash
# Regime-swarm shadow cluster — Helm install for HA chaos drills (P2/P5).
# Does NOT enable Lease-API (gate closed per docs/INFRA_GUARDIAN_SWARM_v0.md).
#
# Usage:
#   ./scripts/regime_swarm_shadow_cluster.sh up
#   ./scripts/regime_swarm_shadow_cluster.sh status
#   ./scripts/regime_swarm_shadow_cluster.sh chaos-delete-leader
#   ./scripts/regime_swarm_shadow_cluster.sh down
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${REGIME_SHADOW_NAMESPACE:-regime-swarm-shadow}"
RELEASE="${REGIME_SHADOW_RELEASE:-regime-swarm-shadow}"
CHART="${ROOT}/charts/regime-swarm"
VALUES="${CHART}/values-shadow.yaml"

log() { printf '[shadow] %s\n' "$*"; }

cmd_up() {
  if command -v helm >/dev/null 2>&1 && kubectl config current-context >/dev/null 2>&1; then
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    log "namespace $NAMESPACE ready (helm)"
    helm upgrade --install "$RELEASE" "$CHART" \
      -n "$NAMESPACE" \
      -f "$VALUES" \
      --wait --timeout 5m
    kubectl get pods -n "$NAMESPACE" -o wide
    return
  fi
  log "helm/k8s unavailable — using docker compose shadow stack"
  docker compose -f "${ROOT}/docker-compose.regime-swarm-shadow.yml" up -d --build
  docker compose -f "${ROOT}/docker-compose.regime-swarm-shadow.yml" ps
}

cmd_status() {
  kubectl get pods,svc,pvc -n "$NAMESPACE" 2>/dev/null || {
    log "namespace $NAMESPACE not found — run: $0 up"
    exit 1
  }
  leader_pod="$RELEASE-0"
  if kubectl get pod -n "$NAMESPACE" "$leader_pod" >/dev/null 2>&1; then
    log "leader pod logs (last 5 lines):"
    kubectl logs -n "$NAMESPACE" "$leader_pod" --tail=5 2>/dev/null || true
  fi
}

cmd_chaos_delete_leader() {
  if kubectl get pod -n "$NAMESPACE" "${RELEASE}-0" >/dev/null 2>&1; then
    leader_pod="${RELEASE}-0"
    log "C-01 (k8s): deleting $leader_pod"
    kubectl delete pod -n "$NAMESPACE" "$leader_pod" --wait=false
    sleep 5
    kubectl get pods -n "$NAMESPACE"
    return
  fi
  log "C-01 (compose): full chaos battery"
  PYTHONPATH="$ROOT" python3 "${ROOT}/scripts/regime_swarm_shadow_chaos.py"
}

cmd_down() {
  helm uninstall "$RELEASE" -n "$NAMESPACE" 2>/dev/null || true
  log "release removed (PVCs retained unless manually deleted)"
}

case "${1:-up}" in
  up) cmd_up ;;
  status) cmd_status ;;
  chaos-delete-leader) cmd_chaos_delete_leader ;;
  down) cmd_down ;;
  *)
    echo "Usage: $0 {up|status|chaos-delete-leader|down}"
    exit 1
    ;;
esac
