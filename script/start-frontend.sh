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

REMOTE_HOST="${DEPLOY_HOST}"
REMOTE_PATH="${DEPLOY_PATH:-/opt/aiprovider/frontend/dist}"

if [ -z "$REMOTE_HOST" ]; then
    echo "[warn] DEPLOY_HOST not set, skip upload"
    echo "  export DEPLOY_HOST=your-server   # 指定服务器地址"
    echo "  export DEPLOY_PATH=...           # 可选，默认 $REMOTE_PATH"
    exit 0
fi

echo "[deploy] uploading to $REMOTE_HOST:$REMOTE_PATH..."
rsync -avz --delete dist/ "root@$REMOTE_HOST:$REMOTE_PATH/"

echo "[done] frontend deployed -> $REMOTE_HOST"
