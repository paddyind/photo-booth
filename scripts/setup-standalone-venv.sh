#!/usr/bin/env bash
# Optional: create .venv only (no server). Same Python rules as run-api-standalone.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REQ="$ROOT/apps/api/requirements.txt"
[[ -f "$REQ" ]] || { echo "Missing $REQ"; exit 1; }

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
  echo "Python 3.10+ not found."
  exit 1
}
if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creating .venv with $($PY --version 2>&1) …"
  "$PY" -m venv "$ROOT/.venv"
else
  echo "Using existing .venv"
fi
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
python -m pip install --upgrade pip
pip install -r "$REQ"
echo "Done. Run: ./scripts/run-api-standalone.sh"
