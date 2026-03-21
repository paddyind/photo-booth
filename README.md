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
- `scripts/`: **`run-api-standalone.sh`** / **`.bat`** — self-contained **Python 3.10+**, **`.venv`**, **`apps/api/requirements.txt`**, API on **`0.0.0.0:8001`**. Optional **`setup-standalone-venv.*`** = venv only.
  - **Printer / folder watcher:** copy **`.env.standalone.example` → `.env.standalone`** (gitignored) and set **`PHOTOBOOTH_ENABLE_PRINT_WATCHER=1`** plus optional **`PHOTOBOOTH_PRINTER_NAME`**. The script installs watcher deps, starts **`print_watcher.py`** on the **same `DATA_DIR`**, and stops the watcher when you stop the API (**Mac/Linux**); **Windows** starts the watcher in the background (close the console or end the `PhotoBoothPrintWatcher` process if it keeps running). Discover names: **`scripts/list-printers.sh`** / **`list-printers.ps1`**.
- **`scripts/run-print-watcher.*`**: run the watcher **alone** (e.g. Docker host where the API is only in a container).

## Quick Start

1. Copy environment:
   - `cp .env.example .env`
2. Start stack:
   - `docker compose up --build`
3. Open:
   - Web UI: `http://localhost:3000`
   - API: `http://localhost:8000/docs`

**Web UI (default):** debug logging and the **Debug logs** panel are **off**; **Clean saved files** is hidden in the browser (it only applies to native app storage — enable with `PHOTOBOOTH_SHOW_CLEANUP=1` in `prepare-www` for mobile). Developers: add **`?debug=1`** to the page URL (or `#debug`) or set **`window.PHOTOBOOTH_DEBUG=true`** before load to show logs + console detail. **Standalone (Mac/Windows):** run **`./scripts/run-api-standalone.sh`** or **`scripts\run-api-standalone.bat`**, open the web app pointed at **`http://<this-pc>:8001`** (or use Docker web + API on 8000).

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
cp .env.standalone.example .env.standalone   # optional: printer + watcher config
./scripts/run-api-standalone.sh       # creates .venv + installs deps on first run, then starts API on :8001
# Optional: ./scripts/setup-standalone-venv.sh  (same venv setup without starting the server)
```

**`.env.standalone`** (optional): `PHOTOBOOTH_ENABLE_PRINT_WATCHER=1`, `PHOTOBOOTH_PRINTER_NAME="Exact Queue Name"`, optional `PHOTOBOOTH_DATA_DIR` (defaults to `DATA_DIR`). List CUPS printers: `./scripts/list-printers.sh`.

Optional overrides (shell env instead of file):

```bash
API_PORT=8002 DATA_DIR="$PWD/data-alt" ./scripts/run-api-standalone.sh
PHOTOBOOTH_ENABLE_PRINT_WATCHER=1 PHOTOBOOTH_PRINTER_NAME="EPSON L3250 Series" ./scripts/run-api-standalone.sh
```

### Windows (cmd)

```bat
copy .env.standalone.example .env.standalone
REM Edit .env.standalone: PHOTOBOOTH_ENABLE_PRINT_WATCHER=1 and optional PHOTOBOOTH_PRINTER_NAME
scripts\run-api-standalone.bat
REM Optional: scripts\setup-standalone-venv.bat  (venv only, no server)
```

List printer names: `powershell -File scripts\list-printers.ps1`

Optional: `set API_PORT=8002`, `set DATA_DIR=D:\pb-data`, or set `PHOTOBOOTH_*` before `run-api-standalone.bat`.

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
  - **Rear mode** is locked to `4x6` + `portrait` + `story-memories` (if present). Output is **JPEG** only; **Prepare Final** is skipped — after capture the API composes the final automatically, then **auto-print** runs after the configured delay (default **10s**). Above the preview, **Capture again** retakes (cancels the timer); the banner shows **Printing in N s…** (or folder-print wording) until the timer elapses, then **Print opened** / **Sent to folder printer**. **Print Final** still opens immediately and cancels the countdown. Delay: inject **`PHOTOBOOTH_REAR_PRINT_DELAY_MS`** (ms).
  - **Front mode** keeps full interactive options (size/orientation/frame).
  - On laptops/desktops, camera mode is forced to front.
- **Rear + physical printer (no double browser print):** run the host **`print_watcher`** (below) and build mobile with **`PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT=1`** so only the watcher prints; or rely on the browser print tab only (no watcher).
- **Optional delay override (mobile bundle):** `PHOTOBOOTH_REAR_PRINT_DELAY_MS` (e.g. `15000`) via `prepare-www` / CI env.
- File save behavior:
  - Original capture and final output use a **short basename**: sanitized **Name** (or `NO_NAME`) **+ timestamp** (`YYYYMMDD_HHMMSS`), e.g. `Jane_20260314_153045_original.jpg`, `Jane_20260314_153045_final.png`.
  - **Dated event folder** `PhotoBooth_DDMMYYYY` (e.g. `PhotoBooth_14032026` for 14 Mar 2026) is created on **first app open** and **stored in `localStorage`** (`photobooth_event_sync_folder_v2`) — the **same folder is reused** after APK updates until you **clear app storage** (then a new folder name is created for that day).
  - **Parent path** comes from `PHOTOBOOTH_SAVE_PATH` (default **`Download`**) under `PHOTOBOOTH_FS_DIRECTORY` (default **`EXTERNAL_STORAGE`**). Full relative path example: **`Download/PhotoBooth_14032026`** → on many phones that is **`/storage/emulated/0/Download/PhotoBooth_14032026/`** — use that (or **My Files → Download → PhotoBooth_…**) as the **Syncthing** folder on the phone.
  - For **My Files → Documents** instead, set `PHOTOBOOTH_SAVE_PATH=Documents`. For **app-private** storage only, use `PHOTOBOOTH_FS_DIRECTORY=DOCUMENTS` and set `PHOTOBOOTH_SAVE_PATH` empty when running `prepare-www` (see `.env.example`).
  - **Laptop / browser**: downloads use the same path shape (`Download/PhotoBooth_DDMMYYYY/…` or dated-only) under the browser’s download location.

## Backend data persistence (Docker)

- `docker-compose.yml` mounts **`./data` on the host → `/app/data` in the container** and sets `DATA_DIR=/app/data`, `FRAMES_DIR=/app/shared/frames`.
- **Restarting or recreating the container does not delete** uploads/previews/finals as long as the host `./data` directory is kept.
- To reset disk state, remove or archive the host folder `./data` (with services stopped).

## Backend data persistence (standalone)

- Standalone scripts set **`DATA_DIR`** to **`./data-standalone`** by default (override with env).
- That directory is **gitignored**; create it automatically on first run.
- **Per-day layout** (local server date, **DDMMYYYY**):  
  `data-standalone/PhotoBooth_DDMMYYYY/originals/`, `…/previews/`, `…/finals/`.  
  Files use the **Name** field + timestamp (same pattern as the web UI), e.g. `Jane_20260314_153045.jpg` (original), preview `Jane_20260314_153045__story-memories.jpg`, final `Jane_20260314_153045_final.png`.
- **Docker / legacy** flat folders (`./data/originals`, `./data/previews`, `./data/finals`) are still readable for older captures (long `uuid__fit3__…` filenames).

## Host print watcher (Docker + standalone)

The API writes finals under **`DATA_DIR/PhotoBooth_DDMMYYYY/finals/`** (or legacy **`DATA_DIR/finals/`**). A small Python process on the **host** (where the printer is installed) can print those files automatically — same workflow whether you use **Docker** or **standalone**, as long as **`PHOTOBOOTH_DATA_DIR`** points at the **host** folder that backs `DATA_DIR`.

**Integrated with standalone:** enable **`PHOTOBOOTH_ENABLE_PRINT_WATCHER`** in **`.env.standalone`** (see above) so you do not need a second terminal.

**Docker-only API on the host:** install deps once (`pip install -r scripts/requirements-print-watcher.txt`; on Windows add **`pywin32`**), then run the watcher only (defaults to **`./data-standalone`**):

```bash
chmod +x scripts/run-print-watcher.sh
./scripts/run-print-watcher.sh
# Or Docker host data:
PHOTOBOOTH_DATA_DIR="$PWD/data" ./scripts/run-print-watcher.sh
```

```bat
REM Windows (cmd), default .\data-standalone
scripts\run-print-watcher.bat
REM Docker volume on host:
set PHOTOBOOTH_DATA_DIR=D:\path\to\photo-booth\data
scripts\run-print-watcher.bat
```

Optional: **`PHOTOBOOTH_PRINTER_NAME`** or **`--printer "Your Printer"`** (Windows: exact queue name; Mac/Linux: `lp -d` destination).

**Why not inside the container?** Linux containers do not see Windows/macOS printer drivers; the watcher must run on the OS that owns the printer.

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
- `fs_directory` (default `EXTERNAL_STORAGE`) — use with `save_path` `Download` for a user-visible Syncthing path.
- `save_path` (default `Download`) — parent only; the app adds `PhotoBooth_DDMMYYYY` inside it.

Repository variables (optional defaults when running the workflow):
- `PHOTOBOOTH_API_BASE`, `PHOTOBOOTH_ENABLE_8X11`, `PHOTOBOOTH_FS_DIRECTORY`, `PHOTOBOOTH_SAVE_PATH`

Local `prepare-www` example:

```bash
cd apps/mobile
PHOTOBOOTH_FS_DIRECTORY=EXTERNAL_STORAGE \
PHOTOBOOTH_SAVE_PATH=Download \
PHOTOBOOTH_API_BASE=http://192.168.1.10:8000 \
PHOTOBOOTH_REAR_PRINT_DELAY_MS=10000 \
PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT=0 \
PHOTOBOOTH_DEBUG=0 \
PHOTOBOOTH_SHOW_CLEANUP=0 \
npm run prepare-www
```

Set **`PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT=1`** when using **`run-print-watcher`** so rear mode does not open a browser print tab after the delay (watcher prints from `**/finals/` instead).

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
