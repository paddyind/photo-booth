#!/usr/bin/env bash
# Run FastAPI on the host (no Docker). Default port 8001 so Docker can use 8000 in parallel.
# Uses data-standalone/ by default so uploads do not clash with docker-compose ./data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export DATA_DIR="${DATA_DIR:-$ROOT/data-standalone}"
export FRAMES_DIR="${FRAMES_DIR:-$ROOT/shared/frames}"
PORT="${API_PORT:-8001}"
if [[ ! -d "$ROOT/.venv" ]]; then
  echo "No .venv found. Run: ./scripts/setup-standalone-venv.sh"
  exit 1
fi
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
mkdir -p "$DATA_DIR"
echo "Standalone API: http://0.0.0.0:${PORT}  (LAN: http://<this-host-ip>:${PORT})"
echo "DATA_DIR=$DATA_DIR"
echo "FRAMES_DIR=$FRAMES_DIR"
exec uvicorn apps.api.app.main:app --host 0.0.0.0 --port "$PORT"
