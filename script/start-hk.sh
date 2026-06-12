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

echo "[start] backend-hk -> http://0.0.0.0:9000"
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
