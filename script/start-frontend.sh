#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../frontend"

if [ ! -d "node_modules" ]; then
    echo "[init] installing dependencies..."
    npm install
fi

echo "[build] building frontend..."
npm run build

echo "[start] frontend preview -> http://0.0.0.0:8000"
npm run preview -- --host 127.0.0.1 --port 8000
