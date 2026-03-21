#!/usr/bin/env bash
# Photo Booth — one command: API + print watcher (when configured) in scripts/photo_booth_standalone.py.
# Self-contained on macOS/Linux: finds Python 3.10+, creates .venv if needed, installs API deps, then starts everything.
#
# Copy .env.standalone.example → .env.standalone and set PHOTOBOOTH_PRINTER_NAME (exact queue name).
# The print watcher starts automatically when a printer name is set; use PHOTOBOOTH_ENABLE_PRINT_WATCHER=0 to disable.
# Queue mode: PHOTOBOOTH_PRINT_WATCH_MODE=queue and PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE=1 (see README).
# Windows: scripts/run-api-standalone.bat (same behavior).
#
# Port: if API_PORT (default 8001) is busy, the next free port is used (8002, …) and printed clearly.
# Require an exact port only: PHOTOBOOTH_STRICT_PORT=1 ./scripts/run-api-standalone.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env.standalone" ]]; then
  echo "Loading $ROOT/.env.standalone …"
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.standalone"
  set +a
fi

REQ="$ROOT/apps/api/requirements.txt"
if [[ ! -f "$REQ" ]]; then
  echo "Missing $REQ — run this script from the photo-booth repo root."
  exit 1
fi

pick_python() {
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      if "$cmd" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        printf '%s' "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PY="$(pick_python)" || {
  echo "Python 3.10+ not found. Install from https://www.python.org/downloads/ or: brew install python@3.12"
  exit 1
}

export PYTHONPATH="$ROOT"
export DATA_DIR="${DATA_DIR:-$ROOT/data-standalone}"
export FRAMES_DIR="${FRAMES_DIR:-$ROOT/shared/frames}"
export API_PORT="${API_PORT:-8001}"
export PHOTOBOOTH_DATA_DIR="${PHOTOBOOTH_DATA_DIR:-$DATA_DIR}"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creating .venv with $($PY --version 2>&1) …"
  "$PY" -m venv "$ROOT/.venv"
fi

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"

echo "Syncing API dependencies …"
python -m pip install -q --upgrade pip
python -m pip install -q -r "$REQ"

python -c "import uvicorn" 2>/dev/null || {
  echo "uvicorn missing after install. Try: rm -rf .venv && $0"
  exit 1
}

mkdir -p "$DATA_DIR"

echo "Starting API (and print watcher if enabled in .env.standalone) …"
exec python "$ROOT/scripts/photo_booth_standalone.py"
