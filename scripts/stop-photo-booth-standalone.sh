#!/usr/bin/env bash
# Photo Booth — FORCE STOP (macOS / Linux)
# Stops processes tied to THIS repo: orchestrator, uvicorn, print_watcher.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/apps/api/requirements.txt" ]]; then
  echo "Run this from the photo-booth repo (missing apps/api/requirements.txt)."
  exit 1
fi

# Escape ROOT for use in pkill -f (regex)
esc=$(printf '%s' "$ROOT" | sed 's/[][\\.^$*+?{}|()]/\\&/g')

echo ""
echo "Photo Booth — stopping processes for:"
echo "  $ROOT"
echo ""

set +e
# Orchestrator (starts API + watcher)
pkill -TERM -f "${esc}/scripts/photo_booth_standalone\\.py" 2>/dev/null
# Stand-alone print watcher
pkill -TERM -f "${esc}/scripts/print_watcher\\.py" 2>/dev/null
# Uvicorn child (venv python path lives under repo)
pkill -TERM -f "${esc}/\\.venv/.*uvicorn" 2>/dev/null
pkill -TERM -f "${esc}/\\.venv/bin/python.*-m uvicorn" 2>/dev/null
set -e

sleep 2

set +e
pkill -KILL -f "${esc}/scripts/photo_booth_standalone\\.py" 2>/dev/null
pkill -KILL -f "${esc}/scripts/print_watcher\\.py" 2>/dev/null
pkill -KILL -f "${esc}/\\.venv/.*uvicorn" 2>/dev/null
pkill -KILL -f "${esc}/\\.venv/bin/python.*-m uvicorn" 2>/dev/null
set -e

echo "  Done. If a terminal is still stuck, close it or press Ctrl+C there."
echo ""
echo "Next: ./scripts/run-api-standalone.sh"
echo ""
