#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Storage-Worker Start-Skript (M3)
# Startet den Redis-basierten Worker als Daemon via nohup.
#
# Voraussetzung: Redis läuft lokal (Docker-Container 'redis', localhost:6379)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

WORKER_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$WORKER_DIR")"
LOG_DIR="$BASE_DIR/logs"
WORKER_SCRIPT="$WORKER_DIR/storage_worker.py"
PID_FILE="$WORKER_DIR/worker.pid"

# Redis-Host (lokal auf M3; via Env überschreibbar)
REDIS_HOST="${REDIS_HOST:-localhost}"

mkdir -p "$LOG_DIR"

# Prüfen ob bereits ein Worker läuft
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "⚠️  Worker läuft bereits (PID $OLD_PID)"
        echo "   Neustart: $0 restart"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# Redis-Verbindung testen (nur wenn redis-cli vorhanden; sonst überspringen)
if command -v redis-cli >/dev/null 2>&1; then
    if ! redis-cli -h "$REDIS_HOST" -p 6379 ping 2>/dev/null | grep -q PONG; then
        echo "⚠️  Redis auf $REDIS_HOST:6379 via redis-cli nicht erreichbar – starte trotzdem (Worker prüft selbst per ping)."
    fi
else
    echo "ℹ️  redis-cli nicht installiert – überspringe Vorab-Check."
fi

# Worker starten
cd "$BASE_DIR"
export REDIS_HOST="$REDIS_HOST"

nohup python3 "$WORKER_SCRIPT" \
    >> "$LOG_DIR/storage_worker.boot.log" \
    2>&1 &

PID=$!
echo $PID > "$PID_FILE"
echo "✅ Storage-Worker gestartet (PID $PID)"
echo "   Redis: $REDIS_HOST:6379"
echo "   Logs:  $LOG_DIR/storage_worker.log"
echo "   Stop:  kill $PID"
