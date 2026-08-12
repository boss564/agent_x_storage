#!/bin/bash
set -e

FILTER="${WORKER_FILTER:-name=d01-worker}"
INTERVAL="${THROTTLE_INTERVAL:-45}"
LOAD="${CPU_LOAD:-90}"

echo "🌡️ [F08] CPU-Throttler gestartet. Load: ${LOAD}%, Dauer: ${INTERVAL}s"

while true; do
  TARGETS=$(docker ps --filter "$FILTER" --format "{{.ID}}")

  if [ -z "$TARGETS" ]; then
    echo "⚠️ Keine Worker gefunden. Warte..."
    sleep 5
    continue
  fi

  TARGET=$(echo "$TARGETS" | shuf -n 1)

  echo "🔥 [F08] Drossele CPU von Container $TARGET auf ${LOAD}% für ${INTERVAL}s"

  docker exec "$TARGET" /bin/sh -c "
    if command -v stress-ng >/dev/null 2>&1; then
      stress-ng --cpu 2 --cpu-load ${LOAD} --timeout ${INTERVAL}s > /dev/null 2>&1 &
    else
      echo '⚠️ stress-ng nicht gefunden, nutze dd als Fallback.'
      dd if=/dev/zero of=/dev/null &
      sleep ${INTERVAL}
      kill %1
    fi
  " 2>/dev/null || echo "❌ Konnte Throttle nicht ausführen (Container tot?)."

  echo "❄️ [F08] Throttling beendet. Warte auf Erholung..."
  sleep 60
done
