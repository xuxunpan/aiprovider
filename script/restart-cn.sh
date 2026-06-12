#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../backend-cn"

set -a
. "$APP_DIR/.env"
set +a

PORT="${APP_PORT:-8000}"

echo "[restart] stopping backend-cn on port $PORT..."
fuser -k "$PORT/tcp" 2>/dev/null || true
sleep 1

echo "[restart] starting backend-cn..."
exec "$SCRIPT_DIR/start-cn.sh"
