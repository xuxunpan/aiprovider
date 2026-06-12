#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../backend-hk"
cd "$APP_DIR"

if [ ! -d "$APP_DIR/.venv" ]; then
    echo "[init] creating virtual environment..."
    python3.11 -m venv "$APP_DIR/.venv" || python3 -m venv "$APP_DIR/.venv"
    echo "[init] installing dependencies..."
    "$APP_DIR/.venv/bin/python" -m pip install -q -r "$APP_DIR/requirements.txt"
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

echo "[start] backend-hk -> http://$HOST:$PORT"
"$APP_DIR/.venv/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
