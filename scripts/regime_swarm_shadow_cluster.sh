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
  if ! command -v kubectl >/dev/null 2>&1; then
    log "kubectl not found — install kubectl or use Docker Compose for local dev"
    exit 1
  fi
  if ! command -v helm >/dev/null 2>&1; then
    log "helm not found — install helm 3.x"
    exit 1
  fi
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  log "namespace $NAMESPACE ready"
  helm upgrade --install "$RELEASE" "$CHART" \
    -n "$NAMESPACE" \
    -f "$VALUES" \
    --wait --timeout 5m
  log "release $RELEASE installed (replicaCount=2, ordinal leader)"
  kubectl get pods -n "$NAMESPACE" -o wide
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
  # C-01 prep: delete ordinal-0, expect K8s recreate (no Lease failover yet)
  leader_pod="$RELEASE-0"
  log "C-01: deleting $leader_pod (expect StatefulSet recreate)"
  kubectl delete pod -n "$NAMESPACE" "$leader_pod" --wait=false
  sleep 5
  kubectl get pods -n "$NAMESPACE"
  log "check standby $RELEASE-1 for standby_tick in logs"
  kubectl logs -n "$NAMESPACE" "$RELEASE-1" --tail=10 2>/dev/null | grep -E 'standby_tick|is_leader' || true
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
