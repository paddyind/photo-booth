# Photo Booth — Roadmap & Next Steps Guide

This document captures the current project status, immediate testing procedures, and step-by-step implementation guide for cloud deployment, multi-tenancy, and subscriptions.

---

## 1. Current State & What Was Achieved

* **Phase 1 Complete (Standalone & Multi-Device Local Testing)**:
  * Full webcam capture $\rightarrow$ frame selection $\rightarrow$ canvas composition $\rightarrow$ preview $\rightarrow$ final download works end-to-end.
  * Local HTTPS proxy script (`scripts/start-https-proxy.sh`) created to allow mobile devices (Android & iPad) on local Wi-Fi to use the camera (`getUserMedia` requires secure context).
  * Web UI smart port detection automatically maps Docker ports (`3200` $\rightarrow$ `3201`), HTTPS proxy (`3443` $\rightarrow$ `3444`), standalone (`8001`), and co-located origins.
* **Cloud Run Preparation**:
  * `gcloud` CLI (Google Cloud SDK 586.0.0) installed on laptop.
  * Single-container Dockerfile ([`Dockerfile.cloudrun`](./Dockerfile.cloudrun)) created bundling API, frames, and Web UI.
  * Deployment script ([`scripts/deploy-cloudrun.sh`](./scripts/deploy-cloudrun.sh)) created for automated one-click GCP deploy.
  * API backend ([`apps/api/app/main.py`](./apps/api/app/main.py)) updated to mount static web UI at root `/` when `WEB_DIR` is set.
  * Web UI ([`apps/web/src/index.html`](./apps/web/src/index.html)) updated to support root co-located Cloud Run origin.

---

## 2. Immediate Mobile Testing (Local LAN)

Test from your phone or iPad right now over the local Wi-Fi network without building an app package:

```bash
# 1. Start Docker stack (if not already running)
docker compose up -d

# 2. Start the HTTPS proxy for camera support
./scripts/start-https-proxy.sh
# Outputs:
#   Web UI:  https://192.168.1.2:3443
#   API:     https://192.168.1.2:3444
```

### Android (Chrome)
1. Ensure phone is on the **same Wi-Fi** as your laptop.
2. Open `https://192.168.1.2:3444/health` $\rightarrow$ tap **Advanced** $\rightarrow$ **Proceed** (accepts self-signed cert for API).
3. Open `https://192.168.1.2:3443` $\rightarrow$ accept cert $\rightarrow$ allow camera when prompted.
4. Capture photos and test composition.

### iPad / iPhone (Safari)
1. Ensure iPad is on the **same Wi-Fi**.
2. Open `https://192.168.1.2:3444/health` $\rightarrow$ tap **Show Details** $\rightarrow$ **Visit this website**.
3. Open `https://192.168.1.2:3443` $\rightarrow$ accept cert $\rightarrow$ allow camera.
4. Capture photos and test composition.

---

## 3. Phase 2: Deploy to Google Cloud Run (Free Tier)

Deploying to Cloud Run gives you a permanent, global HTTPS URL (`https://photo-booth-api-*.a.run.app`) for both the web UI and mobile apps.

> [!IMPORTANT]
> Ensure you use your **personal Google account** when running `gcloud` to keep personal projects separate from work accounts.

### Step 2.1: Authenticate with Personal Account
```bash
# 1. Login with your personal Google account (opens browser)
gcloud auth login

# 2. Create a new personal GCP project (or select existing)
gcloud projects create photobooth-personal --name="Photo Booth"
# Or if you already have a project:
gcloud config set project <your-personal-project-id>

# 3. Link a billing account (required for Cloud Run free tier, won't charge if within free limits)
# Set a budget alert at ₹0 or $0 in Google Cloud Console -> Billing -> Budgets & alerts
```

### Step 2.2: Execute Deployment
```bash
# Deploy to Asia South (Mumbai) or your preferred region:
CLOUDRUN_REGION=asia-south1 ./scripts/deploy-cloudrun.sh
```

The script will:
1. Enable `run.googleapis.com`, `artifactregistry.googleapis.com`, and `cloudbuild.googleapis.com`.
2. Build the container image via Cloud Build.
3. Deploy to Cloud Run with public unauthenticated access enabled.
4. Print your permanent Service URL: `https://photo-booth-api-<hash>.a.run.app`.

### Step 2.3: Verify Cloud Endpoint
* Open `https://photo-booth-api-<hash>.a.run.app` in any browser on any phone/tablet/laptop.
* The web app and API are co-located on the same URL:
  * No certificate warnings.
  * No separate ports.
  * No local Wi-Fi required (works over cellular/4G/5G).

### Step 2.4: Bake Cloud URL into Native Mobile Apps (APK / IPA)
Once you have the Cloud Run URL, build mobile packages via GitHub Actions:
1. Go to **GitHub $\rightarrow$ Actions $\rightarrow$ "Mobile Build (APK + IPA)" $\rightarrow$ Run workflow**.
2. Set:
   * `api_base_url`: `https://photo-booth-api-<hash>.a.run.app`
   * `build_apk`: `true`
   * `build_ios_simulator_app`: `true`
3. Download the built APK from GHA artifacts and install on Android phone.
4. The mobile app will always connect to your cloud backend anywhere.

---

## 4. Phase 3: Persistent Storage with Google Cloud Storage (GCS)

Cloud Run containers are ephemeral (files written locally disappear when instances scale down). We will integrate Google Cloud Storage (5 GB free tier).

### Storage Layout for Multi-Tenancy
```
gs://<bucket-name>/
  ├── frames/
  │   └── default/                    # Standard frames available to all users
  └── tenants/
      └── {tenant_id}/
          ├── frames/                 # Custom branding / overlay frames
          └── events/
              └── {event_id}/
                  ├── originals/      # High-res raw camera captures
                  └── finals/         # Composed photostrips and prints
```

### Implementation Tasks
1. Create bucket: `gsutil mb -l asia-south1 gs://<project-id>-storage`
2. Add `google-cloud-storage` to `apps/api/requirements.txt`.
3. Implement `StorageService` abstraction in `apps/api/app/services/storage.py`:
   * `LocalStorageService`: Uses local disk (`./data`) when running offline or locally.
   * `GCSStorageService`: Uploads to GCS and generates signed URLs for downloads when running on Cloud Run (`PHOTOBOOTH_STORAGE=gcs`).

---

## 5. Phase 4: Authentication & Multi-Tenancy (Demo & Quotas)

To showcase prototypes to different prospective clients with tenant isolation:

### Architecture
* **Auth Provider**: Firebase Authentication (Free tier: unlimited Email/Password, Google Sign-In).
* **Database**: Cloud Firestore (Free tier: 1 GiB storage, 50k reads/day).
* **Token Verification**: `firebase-admin` in FastAPI validates incoming `Authorization: Bearer <id_token>`.

### Data Schema (Firestore)
```
tenants/
  └── {tenant_uid}/
      ├── profile: { name, email, createdAt }
      ├── subscription: { tier: "free" | "pro", status: "active", expiresAt }
      ├── settings: { brandName, primaryColor }
      └── events/
          └── {event_id}/
              ├── name: "Wedding Reception"
              ├── photoCount: 42
              └── frames: ["frame1.png"]
```

### Authorization Rules in FastAPI
```python
# Free Tier Limits:
MAX_PHOTOS_PER_EVENT = 50
ALLOW_CUSTOM_FRAMES = False

# Pro Tier Limits:
MAX_PHOTOS_PER_EVENT = 10000
ALLOW_CUSTOM_FRAMES = True
```

---

## 6. Phase 5: Subscriptions & Payments (Razorpay)

For monetizing the platform in India / internationally:

| Tier | Price | Features |
|------|-------|----------|
| **Free / Demo** | ₹0 | 1 active event, up to 50 photos, default frames only |
| **Single Event** | ₹999 / event | 1 event (valid 7 days), unlimited photos, custom frames |
| **Pro Monthly** | ₹1,499 / mo | Unlimited events, custom branding, high-res downloads |
| **Pro Annual** | ₹11,999 / yr | All Pro features + priority support + watermark removal |

### Implementation Flow
1. Integrate Razorpay Checkout on Web/Mobile frontend.
2. FastAPI webhook endpoint `/api/billing/webhook/razorpay` verifies payment signature.
3. Automatically updates tenant's subscription status in Firestore.

---

## 7. Quick Command Reference

```bash
# === Local LAN Testing ===
./scripts/start-https-proxy.sh                   # Launch HTTPS camera proxy
./scripts/update-mobile-endpoint.sh https://...  # Quick-update mobile www/ endpoint

# === Google Cloud Run Deployment ===
gcloud auth login                               # Authenticate personal account
gcloud config set project <project-id>          # Set active project
./scripts/deploy-cloudrun.sh                    # Build & deploy to Cloud Run

# === Git Workflow ===
git status
git pull origin main
git push origin main
```
