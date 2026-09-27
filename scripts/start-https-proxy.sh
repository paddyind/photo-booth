#!/usr/bin/env bash
# Launch HTTPS proxies so mobile devices on your LAN can use the camera.
#
# Mobile browsers require a secure context (HTTPS) for getUserMedia (camera).
# This script starts two local-ssl-proxy instances:
#   HTTPS :3443 → HTTP :3200  (Web UI)
#   HTTPS :3444 → HTTP :3201  (API)
#
# Usage:
#   ./scripts/start-https-proxy.sh
#
# Then open on your phone/tablet:
#   https://<LAN-IP>:3443
#
# You'll see a certificate warning the first time — tap "Advanced" → "Proceed"
# (Android) or "Continue" (iOS/Safari). This is safe on your local network.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$DIR/.certs"

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

WEB_HTTP_PORT="${WEB_PORT:-3200}"
API_HTTP_PORT="${API_PORT:-3201}"
WEB_HTTPS_PORT="${WEB_HTTPS_PORT:-3443}"
API_HTTPS_PORT="${API_HTTPS_PORT:-3444}"

# Generate self-signed cert if not present
if [[ ! -f "$CERT_DIR/cert.pem" ]] || [[ ! -f "$CERT_DIR/key.pem" ]]; then
  echo "Generating self-signed certificate for $LAN_IP ..."
  mkdir -p "$CERT_DIR"
  openssl req -x509 -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
    -days 365 -nodes \
    -subj "/CN=$LAN_IP" \
    -addext "subjectAltName=IP:$LAN_IP,DNS:localhost" 2>/dev/null
  echo "Certificate created."
fi

echo ""
echo "=== Photo Booth: HTTPS Proxy for Mobile Testing ==="
echo ""
echo "Your LAN IP:  $LAN_IP"
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Web UI:  https://$LAN_IP:$WEB_HTTPS_PORT               "
echo "║  API:     https://$LAN_IP:$API_HTTPS_PORT               "
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "On your phone/tablet:"
echo "  1. Connect to the SAME Wi-Fi as this laptop"
echo "  2. Open Safari (iPad) or Chrome (Android):"
echo "     → https://$LAN_IP:$WEB_HTTPS_PORT"
echo "  3. Accept the certificate warning (tap Advanced → Proceed)"
echo "  4. ALSO visit https://$LAN_IP:$API_HTTPS_PORT/health"
echo "     and accept that certificate too (needed for API calls)"
echo "  5. Go back to the Web UI tab — camera + full flow should work"
echo ""
echo "Press Ctrl+C to stop both proxies."
echo ""

# Trap to clean up both background processes on exit
cleanup() {
  echo ""
  echo "Stopping HTTPS proxies..."
  kill "$WEB_PID" "$API_PID" 2>/dev/null || true
  wait "$WEB_PID" "$API_PID" 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

# Start Web UI proxy
npx -y local-ssl-proxy \
  --hostname 0.0.0.0 \
  --source "$WEB_HTTPS_PORT" \
  --target "$WEB_HTTP_PORT" \
  --cert "$CERT_DIR/cert.pem" \
  --key "$CERT_DIR/key.pem" &
WEB_PID=$!

# Start API proxy
npx -y local-ssl-proxy \
  --hostname 0.0.0.0 \
  --source "$API_HTTPS_PORT" \
  --target "$API_HTTP_PORT" \
  --cert "$CERT_DIR/cert.pem" \
  --key "$CERT_DIR/key.pem" &
API_PID=$!

echo "Web UI proxy (PID $WEB_PID): https://0.0.0.0:$WEB_HTTPS_PORT → http://localhost:$WEB_HTTP_PORT"
echo "API proxy    (PID $API_PID): https://0.0.0.0:$API_HTTPS_PORT → http://localhost:$API_HTTP_PORT"
echo ""

# Wait for either to exit
wait
