#!/usr/bin/env bash
# Deploy the Photo Booth API to Google Cloud Run.
#
# Prerequisites:
#   brew install --cask google-cloud-sdk
#   gcloud auth login
#   gcloud config set project <your-project-id>
#
# Usage:
#   ./scripts/deploy-cloudrun.sh                    # Uses default project
#   ./scripts/deploy-cloudrun.sh my-project-id      # Specify project
#
# After first deploy, the script prints the service URL.
set -euo pipefail

# Ensure gcloud CLI is in PATH (Homebrew install path)
export PATH="/opt/homebrew/share/google-cloud-sdk/bin:/opt/homebrew/bin:$PATH"

PROJECT="${1:-$(gcloud config get-value project 2>/dev/null || echo "")}"
REGION="${CLOUDRUN_REGION:-asia-south1}"
SERVICE="photo-booth-api"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "$PROJECT" ]]; then
  echo "ERROR: No GCP project set."
  echo "Run: gcloud config set project <your-project-id>"
  echo "Or:  $0 <project-id>"
  exit 1
fi

echo "=== Photo Booth: Deploy to Cloud Run ==="
echo "Project:  $PROJECT"
echo "Region:   $REGION"
echo "Service:  $SERVICE"
echo ""

# Enable required APIs (idempotent)
echo "Enabling required APIs..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project="$PROJECT" --quiet

# Deploy using Cloud Build (builds + pushes + deploys in one step)
echo ""
echo "Building and deploying..."
gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source="$DIR" \
  --dockerfile="$DIR/Dockerfile.cloudrun" \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --set-env-vars="DATA_DIR=/tmp/data,FRAMES_DIR=/app/shared/frames" \
  --quiet

echo ""
echo "=== Deployment Complete ==="
SERVICE_URL=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format="value(status.url)")
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  API URL:  $SERVICE_URL"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Test it:"
echo "  curl $SERVICE_URL/health"
echo ""
echo "Use in mobile builds:"
echo "  ./scripts/update-mobile-endpoint.sh $SERVICE_URL"
echo ""
echo "Or trigger GHA workflow with:"
echo "  api_base_url: $SERVICE_URL"
echo ""
echo "Note: Photos are stored in /tmp (ephemeral — lost on cold start)."
echo "For persistent storage, add Cloud Storage in Phase 2 Step 8."
