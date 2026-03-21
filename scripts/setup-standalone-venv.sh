#!/usr/bin/env bash
# One-time (or occasional) setup: Python venv + API dependencies for standalone mode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$(command -v python3)" ]]; then
  echo "python3 not found. Install Python 3.11+ and retry."
  exit 1
fi
python3 -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r apps/api/requirements.txt
echo "Done. Activate with: source .venv/bin/activate"
echo "Then run: ./scripts/run-api-standalone.sh"
