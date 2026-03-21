#!/usr/bin/env bash
# Photo Booth — one command: API + print watcher (when configured) in scripts/photo_booth_standalone.py.
# Self-contained on macOS/Linux: finds Python 3.10+, creates .venv if needed, installs API deps, then starts everything.
#
# Copy .env.standalone.example → .env.standalone and set PHOTOBOOTH_PRINTER_NAME (exact queue name).
# The print watcher starts automatically when a printer name is set; use PHOTOBOOTH_ENABLE_PRINT_WATCHER=0 to disable.
# Queue mode: PHOTOBOOTH_PRINT_WATCH_MODE=queue and PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE=1 (see README).
# Windows: scripts/run-api-standalone.bat (same behavior).
#
# Port: default API_PORT (8001) is kept — listeners on that port are stopped, then bind (no 8002+ unless PHOTOBOOTH_PORT_FALLBACK=1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cat <<'EOS'

============================================================
  PHOTO BOOTH — STANDALONE SERVER (keep this terminal open)
============================================================

  NORMAL USE
  ------------
  • Leave this terminal open while guests use the booth.
  • To stop: press Ctrl+C in this window.

  IF SOMETHING IS STUCK OR WON'T START
  ------------------------------------
  1) Run:  ./scripts/stop-photo-booth-standalone.sh
     (force-stops this booth's API + print watcher)
  2) Then run:  ./scripts/run-api-standalone.sh  again.

  OR one step:
     ./scripts/restart-photo-booth-standalone.sh

  TEST PHONE: open the LAN URL printed below + /health in Safari/Chrome
  MOBILE APK: default is fixed API_PORT (8001) — busy ports are cleared automatically.
    Legacy 8002+ scan: PHOTOBOOTH_PORT_FALLBACK=1 in .env.standalone

============================================================

EOS

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
