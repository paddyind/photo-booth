# Photo Booth

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
- `data`: Runtime storage when using **Docker** backend (host-mounted).
- `data-standalone`: Optional runtime storage for **standalone** uvicorn (default; gitignored) when running beside Docker.
- `scripts/`: `run-api-standalone.*` and `setup-standalone-venv.*` for host-based API (default port **8001**).

## Quick Start

1. Copy environment:
   - `cp .env.example .env`
2. Start stack:
   - `docker compose up --build`
3. Open:
   - Web UI: `http://localhost:3000`
   - API: `http://localhost:8000/docs`

## API: Docker (port 8000) + standalone (port 8001) on one machine

Use **Docker** for the normal stack and **standalone** for a second API process (e.g. compare behavior or run without Docker). Both listen on **`0.0.0.0`**, work **offline on a LAN**, and can run **at the same time** on different ports.

| Mode | Port (default) | Data directory | How |
|------|----------------|----------------|-----|
| **Docker** `backend` | **8000** (`API_PORT` in `.env`) | Host `./data` → container `/app/data` | `docker compose up -d` |
| **Standalone** (host Python) | **8001** | `./data-standalone` | Scripts below |

**Why two data folders?** If both APIs run together, sharing one `./data` can mix uploads/previews. Standalone defaults to **`data-standalone/`** (gitignored) so they stay isolated.

### macOS / Linux

```bash
chmod +x scripts/*.sh
./scripts/setup-standalone-venv.sh    # once
./scripts/run-api-standalone.sh       # API on http://0.0.0.0:8001
```

Optional overrides:

```bash
API_PORT=8002 DATA_DIR="$PWD/data-alt" ./scripts/run-api-standalone.sh
```

### Windows (cmd)

```bat
scripts\setup-standalone-venv.bat
scripts\run-api-standalone.bat
```

Optional: `set API_PORT=8002` before `run-api-standalone.bat`, or `set DATA_DIR=D:\pb-data`.

### Run Docker and standalone together

1. Terminal A: `docker compose up -d` → API **`http://<LAN-IP>:8000`**
2. Terminal B: `./scripts/run-api-standalone.sh` → API **`http://<LAN-IP>:8001`**
3. Health checks (on the host or another device on the same network):
   - `curl http://127.0.0.1:8000/health`
   - `curl http://127.0.0.1:8001/health`

No internet required; phones only need the same Wi‑Fi / hotspot as the computer.

### Mobile APK: point at Docker **8000** vs standalone **8001**

The app’s API URL is baked in at **`prepare-www`** / CI time (`PHOTOBOOTH_API_BASE`).

- **Docker backend:** build with `api_base_url` = `http://<your-pc-LAN-ip>:8000`
- **Standalone backend:** build with `api_base_url` = `http://<your-pc-LAN-ip>:8001`

Same GitHub **Run workflow** twice with different `api_base_url`, or locally:

```bash
cd apps/mobile
PHOTOBOOTH_API_BASE=http://192.168.12.34:8000 npm run prepare-www && npx cap sync android
# vs
PHOTOBOOTH_API_BASE=http://192.168.12.34:8001 npm run prepare-www && npx cap sync android
```

Install the matching APK for whichever server you started. **One APK** only talks to **one** base URL unless you add a future in-app setting.

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
   - `docker compose restart backend web`

The frame will then appear automatically in the frame dropdown after selecting the matching size.

## Preview / Final Behavior

- After capturing an image, the app generates a **preview** for the current selection `(size, orientation, frame)`.
- If the user changes `(size, orientation, frame)` and then returns to a previous selection, the system reuses the existing preview file (it will not re-render if already cached on disk).
- When the user clicks **Prepare Final** (PNG or PDF), the backend generates the final output and then **deletes all preview images** for that `image_id`.
- Camera mode behavior:
  - Mobile devices can switch between **Front** and **Rear** camera.
  - **Rear mode** is locked to `4x6` + `portrait` + `story-memories` (if present).
  - **Front mode** keeps full interactive options (size/orientation/frame).
  - On laptops/desktops, camera mode is forced to front.
- File save behavior:
  - Original capture and final output are saved with `NAME_or_NO_NAME + timestamp` in the filename.
  - On Capacitor mobile builds, **originals** and **finals** go to **separate configurable folders** (defaults: `PhotoBooth/originals` and `PhotoBooth/finals` under the Capacitor `DOCUMENTS` volume).
  - Configure via env vars consumed by `apps/mobile/scripts/prepare-www.js` (see `.env.example`): `PHOTOBOOTH_FS_DIRECTORY`, `PHOTOBOOTH_SAVE_PATH_ORIGINALS`, `PHOTOBOOTH_SAVE_PATH_FINALS`.
  - Point **Syncthing** (or similar) at the **finals** folder on the phone so PNG/JPEG/PDF sync to a laptop folder for USB printing—mirrors a “DCIM/photobooth → laptop” style workflow while keeping finals separate from camera originals.
  - In browser/laptop fallback mode, files download to the browser default Downloads location.

## Backend data persistence (Docker)

- `docker-compose.yml` mounts **`./data` on the host → `/app/data` in the container** and sets `DATA_DIR=/app/data`, `FRAMES_DIR=/app/shared/frames`.
- **Restarting or recreating the container does not delete** uploads/previews/finals as long as the host `./data` directory is kept.
- To reset disk state, remove or archive the host folder `./data` (with services stopped).

## Backend data persistence (standalone)

- Standalone scripts set **`DATA_DIR`** to **`./data-standalone`** by default (override with env).
- That directory is **gitignored**; create it automatically on first run.

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
- `fs_directory` (default `DOCUMENTS`) — Capacitor Filesystem directory for on-device saves.
- `save_path_originals` / `save_path_finals` — relative paths under that directory (e.g. point finals at a folder you sync with Syncthing).

Repository variables (optional defaults when running the workflow):
- `PHOTOBOOTH_API_BASE`, `PHOTOBOOTH_ENABLE_8X11`, `PHOTOBOOTH_FS_DIRECTORY`, `PHOTOBOOTH_SAVE_PATH_ORIGINALS`, `PHOTOBOOTH_SAVE_PATH_FINALS`

Local `prepare-www` example:

```bash
cd apps/mobile
PHOTOBOOTH_FS_DIRECTORY=DOCUMENTS \
PHOTOBOOTH_SAVE_PATH_ORIGINALS=DCIM/photobooth/camera \
PHOTOBOOTH_SAVE_PATH_FINALS=DCIM/photobooth/print_queue \
PHOTOBOOTH_API_BASE=http://192.168.1.10:8000 \
npm run prepare-www
```

CI warm-up:
- Before `cap sync` builds Android/iOS artifacts, the workflow *tries* to start `backend` + `web` using `docker-compose.ci.yml` and waits for `GET /health` and `GET /options`.
- If Docker isn’t available or warm-up fails, the workflow continues and still builds the mobile packages (warm-up is non-blocking).

Local Docker Desktop:
- When you test mobile apps locally, run `docker compose up -d backend web` first so the phone/tablet can reach the latest API.
- For mobile testing on same Wi-Fi, set `PHOTOBOOTH_API_BASE` (or workflow `api_base_url`) to `http://<your-laptop-lan-ip>:8000`.

### Notes about iOS IPA

Producing a signed `.ipa` requires signing credentials. The workflow includes a dedicated job for `build_ipa`, but you must provide the required secrets:
- `IOS_CERT_P12_BASE64`
- `IOS_PROVISIONING_PROFILE_BASE64`
- `IOS_BUNDLE_ID`

Until those signing details are wired to your exact Xcode/Capacitor project, iOS Simulator artifacts are the reliable option for testing.
