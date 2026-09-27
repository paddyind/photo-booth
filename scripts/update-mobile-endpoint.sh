#!/usr/bin/env bash
# Quick re-bundle mobile www/ with a new API endpoint — no full rebuild needed.
# Usage:
#   ./scripts/update-mobile-endpoint.sh http://192.168.1.2:3201
#   ./scripts/update-mobile-endpoint.sh http://192.168.1.2:8001
#
# After running, sync to device:
#   cd apps/mobile && npx cap sync android ios
#   Then build APK in Android Studio or run in Xcode.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="$DIR/apps/mobile"

API_BASE="${1:-}"
if [[ -z "$API_BASE" ]]; then
  echo "Usage: $0 <API_BASE_URL>"
  echo ""
  echo "Examples:"
  echo "  $0 http://192.168.1.2:3201    # Docker backend"
  echo "  $0 http://192.168.1.2:8001    # Standalone backend"
  echo "  $0 http://your-cloud.run.app  # Cloud Run (v2)"
  echo ""
  echo "After running, sync native projects:"
  echo "  cd apps/mobile && npx cap sync android ios"
  exit 1
fi

echo "=== Photo Booth: Update Mobile Endpoint ==="
echo "API base: $API_BASE"
echo ""

cd "$MOBILE_DIR"

# Install deps if needed
if [[ ! -d node_modules ]]; then
  echo "Installing dependencies..."
  npm install
fi

# Re-run prepare-www with the new endpoint
export PHOTOBOOTH_API_BASE="$API_BASE"

# Carry forward any existing env.build settings (printer, debug, etc.)
ENV_FILE="$MOBILE_DIR/env.build"
if [[ -f "$ENV_FILE" ]]; then
  echo "Loading existing env.build settings..."
  set -a
  source "$ENV_FILE"
  set +a
  # Override API base with the argument
  export PHOTOBOOTH_API_BASE="$API_BASE"
fi

npm run prepare-www

echo ""
echo "=== Done ==="
echo "www/index.html updated with API base: $API_BASE"
echo ""
echo "Next steps:"

if [[ -d android ]] || [[ -d ios ]]; then
  echo "  1. Sync native projects:"
  echo "     cd apps/mobile && npx cap sync android ios"
  echo ""
  echo "  2. Build:"
  echo "     Android: Open android/ in Android Studio → Build APK"
  echo "     iOS:     Open ios/App/App.xcworkspace in Xcode → Run"
else
  echo "  1. Add native platform (first time only):"
  echo "     cd apps/mobile"
  echo "     npx cap add android    # and/or"
  echo "     npx cap add ios"
  echo ""
  echo "  2. Then sync and build:"
  echo "     npx cap sync android ios"
fi
echo ""
echo "  Verify endpoint baked in:"
echo "    grep PHOTOBOOTH_API_BASE apps/mobile/www/index.html"
