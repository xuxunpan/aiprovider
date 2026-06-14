#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../backend-hk"
PID_FILE="$APP_DIR/uvicorn.pid"

# 自动检测并安装依赖（requirements.txt 内容变化时自动重装）
CUR_HASH=$(md5sum "$APP_DIR/requirements.txt" | awk '{print $1}')
OLD_HASH=""
[ -f "$APP_DIR/.venv/.deps_hash" ] && OLD_HASH=$(cat "$APP_DIR/.venv/.deps_hash")
if [ "$CUR_HASH" != "$OLD_HASH" ]; then
    if [ ! -d "$APP_DIR/.venv" ]; then
        echo "[restart] creating virtual environment..."
        python3.11 -m venv "$APP_DIR/.venv" || python3 -m venv "$APP_DIR/.venv"
    fi
    echo "[restart] installing/updating dependencies..."
    "$APP_DIR/.venv/bin/python" -m pip install -q -r "$APP_DIR/requirements.txt"
    echo "$CUR_HASH" > "$APP_DIR/.venv/.deps_hash"
fi

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
