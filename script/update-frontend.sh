#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[update] pulling latest code..."
git pull

cd frontend

echo "[update] installing dependencies..."
npm install

echo "[update] building..."
npm run build

echo "[done] frontend updated"
