#!/usr/bin/env bash
# Start EdgeSight. Restarts it if it is already running.  Usage: ./run.sh [--no-browser]
set -euo pipefail
cd "$(dirname "$0")"
PORT="${EDGESIGHT_PORT:-8800}"
OLD=$(ss -ltnp 2>/dev/null | grep ":$PORT " | sed -nE 's/.*pid=([0-9]+).*/\1/p' | head -1 || true)
if [ -n "$OLD" ]; then echo "stopping old EdgeSight (pid $OLD)"; kill "$OLD"; sleep 1; fi
PYTHONPATH=src exec .venv/bin/python -m edgesight "$@"
