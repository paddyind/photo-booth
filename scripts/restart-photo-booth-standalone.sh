#!/usr/bin/env bash
# Photo Booth — FORCE STOP then START (macOS / Linux)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/stop-photo-booth-standalone.sh"
echo "Starting server in 2 seconds…"
sleep 2
exec "$ROOT/scripts/run-api-standalone.sh"
