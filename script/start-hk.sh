#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../backend-hk"

if [ ! -d ".venv" ]; then
    echo "[init] creating virtual environment..."
    python3.11 -m venv .venv || python3 -m venv .venv
    echo "[init] installing dependencies..."
    .venv/bin/python -m pip install -q -r requirements.txt
fi

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[init] copying .env.example to .env"
        cp .env.example .env
        echo "[warn] please edit .env and fill in OPENAI_API_KEY and other configs"
        exit 0
    else
        echo "[warn] .env not found, copy .env.example to .env and fill in configs"
        exit 1
    fi
fi

set -a
. .env
set +a

HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-9000}"

echo "[start] backend-hk -> http://$HOST:$PORT"
.venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
