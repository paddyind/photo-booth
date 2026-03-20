# Photo Booth v2

Consumer-friendly photo booth platform for phone/tablet capture, frame overlays, preview saves, and managed printing.

## Goals

- Keep legacy `photobooth` implementation as stable backup.
- Build a new modular project for collaboration and enhancements.
- Support iOS/Android browser-based capture on same WiFi network.
- Add frame packs, preview workflow, print queue, and admin operations.

## Architecture

- `apps/api`: FastAPI service for frame listing, preview composition, and job management.
- `apps/web`: Mobile-first web app (PWA-ready) for capture, frame selection, and preview flow.
- `apps/print-agent`: Local machine printer worker (Windows friendly).
- `shared/frames`: Frame packs and metadata (`meta.json`) by print size.
- `data`: Runtime storage for uploads, previews, finals, and archive.

## Quick Start

1. Copy environment:
   - `cp .env.example .env`
2. Start stack:
   - `docker compose up --build`
3. Open:
   - Web UI: `http://localhost:3000`
   - API: `http://localhost:8000/docs`

## Notes

- Printing is intentionally kept in `print-agent` to avoid printer driver issues in Linux containers.
- Existing legacy script remains untouched in the original `photobooth` project.
- This repository is the new collaboration baseline.

## Frame Management (Project Folder Based)

Frames are loaded from the repository folders (no external upload required).

- Base path: `shared/frames/<size>/<frame-id>/frame.png`
- Supported sizes right now (initial options): `4x6`, `5x7`
- Additional size supported by the backend/compositor (frames can be added): `8x11` (mobile UI opt-in via `PHOTOBOOTH_ENABLE_8X11`)
- Example:
  - `shared/frames/4x6/story-memories/frame.png`
  - `shared/frames/5x7/story-memories/frame.png`

### Add a New Frame

1. Create a new folder for each target size:
   - `shared/frames/4x6/my-new-frame/`
2. Place your PNG as:
   - `shared/frames/4x6/my-new-frame/frame.png`
3. If you want the same visual for other sizes, copy to:
   - `shared/frames/5x7/my-new-frame/frame.png`
   - `shared/frames/8x11/my-new-frame/frame.png`
4. Restart services:
   - `docker compose restart api web`

The frame will then appear automatically in the frame dropdown after selecting the matching size.

## Preview / Final Behavior

- After capturing an image, the app generates a **preview** for the current selection `(size, orientation, frame)`.
- If the user changes `(size, orientation, frame)` and then returns to a previous selection, the system reuses the existing preview file (it will not re-render if already cached on disk).
- When the user clicks **Prepare Final** (PNG or PDF), the backend generates the final output and then **deletes all preview images** for that `image_id`.

This makes the preview responsive and ensures the final file matches exactly what the user saw before printing.

## CI/CD (Mobile APK + IPA)

This repo includes a GitHub Actions workflow: `.github/workflows/mobile-build.yml`.

It expects you to add a Capacitor mobile app scaffold at:

- `apps/mobile/` (must contain `package.json` and a `cap:sync` script)

### How to run

In GitHub UI: Actions -> “Mobile Build (APK + IPA)” -> `Run workflow`.

Inputs:
- `build_apk` (default `true`)
- `build_ios_simulator_app` (default `true`)
- `build_ipa` (default `false`)
- `enable_8x11` (default `false`) to opt-in to showing `8x11` in the mobile UI
- `api_base_url` controls `PHOTOBOOTH_API_BASE` injection used by the mobile web bundle.

Automatic CI on `push` / `pull_request` uses repository variables (if set):
- `PHOTOBOOTH_API_BASE` (fallback: `http://YOUR_LAN_IP:8000`)
- `PHOTOBOOTH_ENABLE_8X11` (fallback: `false`)

CI warm-up:
- Before `cap sync` builds Android/iOS artifacts, the workflow starts `backend` + `web` using `docker-compose.ci.yml` and waits for `GET /health` and `GET /options`.

Local Docker Desktop:
- When you test mobile apps locally, run `docker compose up -d backend web` first so the phone/tablet can reach the latest API.

### Notes about iOS IPA

Producing a signed `.ipa` requires signing credentials. The workflow includes a dedicated job for `build_ipa`, but you must provide the required secrets:
- `IOS_CERT_P12_BASE64`
- `IOS_PROVISIONING_PROFILE_BASE64`
- `IOS_BUNDLE_ID`

Until those signing details are wired to your exact Xcode/Capacitor project, iOS Simulator artifacts are the reliable option for testing.
