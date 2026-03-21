#!/usr/bin/env bash
# Photo Booth API on the host (no Docker). Default port 8001 (Docker can use 8000).
# Self-contained on macOS/Linux: finds Python 3.10+, creates .venv if needed, installs deps, runs uvicorn.
#
# Optional printer setup (same process):
#   Copy .env.standalone.example → .env.standalone and set:
#     PHOTOBOOTH_ENABLE_PRINT_WATCHER=1
#     PHOTOBOOTH_PRINTER_NAME="Your Printer"   # optional; default system printer
#     PHOTOBOOTH_DATA_DIR=...                  # optional; defaults to DATA_DIR
# Or export those variables before running this script.
#
# The folder watcher prints new files under **/finals/ (see scripts/print_watcher.py).
# Windows (GDI): use scripts/run-api-standalone.bat + pywin32 for best results.
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
PORT="${API_PORT:-8001}"
export PHOTOBOOTH_DATA_DIR="${PHOTOBOOTH_DATA_DIR:-$DATA_DIR}"

WATCHER_PID=""
cleanup() {
  if [[ -n "${WATCHER_PID:-}" ]] && kill -0 "$WATCHER_PID" 2>/dev/null; then
    echo ""
    echo "Stopping print watcher (pid $WATCHER_PID)…"
    kill "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

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

_enable="${PHOTOBOOTH_ENABLE_PRINT_WATCHER:-0}"
case "$_enable" in
  1 | true | yes | on | TRUE | YES | ON) _enable=1 ;;
  *) _enable=0 ;;
esac

if [[ "$_enable" == "1" ]]; then
  echo "Syncing print-watcher dependencies …"
  python -m pip install -q -r "$ROOT/scripts/requirements-print-watcher.txt"
  WATCH_ARGS=(--data-dir "$PHOTOBOOTH_DATA_DIR")
  if [[ -n "${PHOTOBOOTH_PRINTER_NAME:-}" ]]; then
    WATCH_ARGS+=(--printer "$PHOTOBOOTH_PRINTER_NAME")
    echo "Print watcher: printer=${PHOTOBOOTH_PRINTER_NAME}"
  else
    echo "Print watcher: printer=(system default)"
  fi
  echo "Print watcher: PHOTOBOOTH_DATA_DIR=$PHOTOBOOTH_DATA_DIR"
  python "$ROOT/scripts/print_watcher.py" "${WATCH_ARGS[@]}" &
  WATCHER_PID=$!
  echo "Print watcher started (pid $WATCHER_PID). Stop the API (Ctrl+C) to stop both."
fi

mkdir -p "$DATA_DIR"
echo ""
echo "Standalone API: http://127.0.0.1:${PORT}  |  LAN: http://<this-mac-ip>:${PORT}"
echo "DATA_DIR=$DATA_DIR"
echo "FRAMES_DIR=$FRAMES_DIR"
echo ""
python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port "$PORT"
