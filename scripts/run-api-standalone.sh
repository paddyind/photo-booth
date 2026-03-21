#!/usr/bin/env bash
# Photo Booth API on the host (no Docker). Default port 8001 (Docker can use 8000).
# Self-contained on macOS/Linux: finds Python 3.10+, creates .venv if needed, installs deps, runs uvicorn.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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
echo ""
echo "Standalone API: http://127.0.0.1:${PORT}  |  LAN: http://<this-mac-ip>:${PORT}"
echo "DATA_DIR=$DATA_DIR"
echo "FRAMES_DIR=$FRAMES_DIR"
echo ""
exec python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port "$PORT"
