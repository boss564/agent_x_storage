#!/bin/bash
set -e

FILTER="${WORKER_FILTER:-name=d01-worker}"
INTERVAL="${KILL_INTERVAL:-25}"

echo "☠️ [F07] Worker-Killer gestartet. Filter: $FILTER, Intervall: ${INTERVAL}s"

while true; do
  TARGETS=$(docker ps --filter "$FILTER" --format "{{.ID}}")

  if [ -z "$TARGETS" ]; then
    echo "⚠️ Keine Worker gefunden. Warte..."
    sleep 5
    continue
  fi

  TARGET=$(echo "$TARGETS" | shuf -n 1)

  echo "💀 [F07] Tödlicher Schlag gegen Container: $TARGET"

  docker kill "$TARGET" 2>/dev/null || echo "❌ Container existiert nicht mehr."

  sleep 5

  echo "🔄 [F07] Warte auf Autoscale/Neustart für ${INTERVAL}s..."
  sleep "$INTERVAL"
done
