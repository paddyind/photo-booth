#!/usr/bin/env bash
# Watch DATA_DIR for new **/finals/** files and print (same folder layout as Docker or standalone).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PHOTOBOOTH_DATA_DIR="${PHOTOBOOTH_DATA_DIR:-$ROOT/data-standalone}"

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
  echo "Python 3.10+ required."
  exit 1
}

if ! "$PY" -c "import watchdog" 2>/dev/null; then
  echo "Installing print-watcher dependencies…"
  "$PY" -m pip install -q -r "$ROOT/scripts/requirements-print-watcher.txt"
fi

echo "PHOTOBOOTH_DATA_DIR=$PHOTOBOOTH_DATA_DIR"
exec "$PY" "$ROOT/scripts/print_watcher.py" --data-dir "$PHOTOBOOTH_DATA_DIR" "$@"
