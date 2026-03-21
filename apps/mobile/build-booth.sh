#!/usr/bin/env bash
# Build the Capacitor web bundle (www/) with booth-friendly injection, then cap sync.
# Prerequisites: Node 18+, from repo: apps/mobile/
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

ENV_FILE="$DIR/env.build"
if [[ -f "$ENV_FILE" ]]; then
  echo "Loading $ENV_FILE"
  # KEY=value lines; set -a exports assignments for child processes (npm).
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
else
  echo "Missing $ENV_FILE — copy env.build.example to env.build and set PHOTOBOOTH_API_BASE." >&2
  exit 1
fi

if [[ -z "${PHOTOBOOTH_API_BASE:-}" ]]; then
  echo "PHOTOBOOTH_API_BASE is empty. Set it in env.build (e.g. http://192.168.0.50:8001)." >&2
  exit 1
fi

export PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT="${PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT:-1}"

echo "API base: $PHOTOBOOTH_API_BASE"
npm install
npm run prepare-www

if [[ -d android ]] || [[ -d ios ]]; then
  npx cap sync android ios
  echo ""
  echo "Done: www/ updated and native projects synced."
  echo "  Android: open android/ in Android Studio → Build APK."
  echo "  iOS: open ios/App/App.xcworkspace in Xcode → Run / Archive."
else
  echo ""
  echo "www/ is ready at apps/mobile/www/index.html"
  echo "First time only — add native projects from apps/mobile:"
  echo "  npx cap add android"
  echo "  npx cap add ios"
  echo "Then re-run: ./build-booth.sh"
fi
