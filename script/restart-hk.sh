#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../backend-hk"

set -a
. "$APP_DIR/.env"
set +a

PORT="${APP_PORT:-9000}"

echo "[restart] stopping backend-hk on port $PORT..."
fuser -k "$PORT/tcp" 2>/dev/null || true
sleep 1

echo "[restart] starting backend-hk..."
exec "$SCRIPT_DIR/start-hk.sh"
