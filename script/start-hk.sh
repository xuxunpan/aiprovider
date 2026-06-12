#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../backend-hk"
cd "$APP_DIR"

PID_FILE="$APP_DIR/uvicorn.pid"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/app.log"

if [ ! -d "$APP_DIR/.venv" ] || [ ! -f "$APP_DIR/.venv/.deps_ok" ]; then
    if [ ! -d "$APP_DIR/.venv" ]; then
        echo "[init] creating virtual environment..."
        python3.11 -m venv "$APP_DIR/.venv" || python3 -m venv "$APP_DIR/.venv"
    fi
    echo "[init] installing dependencies..."
    "$APP_DIR/.venv/bin/python" -m pip install -q -r "$APP_DIR/requirements.txt"
    touch "$APP_DIR/.venv/.deps_ok"
fi

if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        echo "[init] copying .env.example to .env"
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo "[warn] please edit .env and fill in OPENAI_API_KEY and other configs"
        exit 0
    else
        echo "[warn] .env not found, copy .env.example to .env and fill in configs"
        exit 1
    fi
fi

set -a
. "$APP_DIR/.env"
set +a

HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-9000}"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[warn] backend-hk is already running (pid=$PID)"
        exit 1
    fi
    rm -f "$PID_FILE"
fi

mkdir -p "$LOG_DIR"

echo "[start] backend-hk -> http://$HOST:$PORT (background)"
nohup "$APP_DIR/.venv/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "[start] pid=$(cat "$PID_FILE"), log=$LOG_FILE"
