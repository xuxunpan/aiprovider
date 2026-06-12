#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../backend-hk"
PID_FILE="$APP_DIR/uvicorn.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[restart] stopping backend-hk (pid=$PID)..."
        kill "$PID"
        sleep 1
        if kill -0 "$PID" 2>/dev/null; then
            echo "[restart] force killing..."
            kill -9 "$PID"
        fi
    fi
    rm -f "$PID_FILE"
else
    echo "[restart] no pid file, stopping by port..."
    set -a
    . "$APP_DIR/.env"
    set +a
    PORT="${APP_PORT:-9000}"
    fuser -k "$PORT/tcp" 2>/dev/null || true
    sleep 1
fi

echo "[restart] starting backend-hk..."
exec "$SCRIPT_DIR/start-hk.sh"
