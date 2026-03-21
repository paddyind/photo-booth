# Photo Booth mobile — build the bundled web app (end-to-end)

The native shell is **Capacitor**; the UI is the same as `apps/web/src/index.html`, copied into `www/` by **`prepare-www`** with mobile-specific injection (API URL, save paths, printer flags).

## 1. One-time: Node + native tooling

- **Node.js 18+** and **npm**
- **Android:** Android Studio (SDK), then `npx cap add android` from this folder if `android/` does not exist yet
- **iOS (Mac only):** Xcode, then `npx cap add ios` if `ios/` does not exist yet

`android/` and `ios/` are gitignored; they are created on your machine when you add platforms.

## 2. Configure booth PC URL

On the **phone**, the app must call the **booth PC’s LAN IP**, not `127.0.0.1`.

1. Start **`run-api-standalone`** on the PC and note the **`LAN:`** line (e.g. `http://192.168.0.50:8001`).
2. Copy **`env.build.example` → `env.build`** (same folder as this file).
3. Edit **`env.build`** and set:
   - **`PHOTOBOOTH_API_BASE`** = that full URL (scheme + IP + port **8001** for standalone).
4. Keep **`PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT=1`** so the **physical printer** on the PC is used (print-queue + `print_watcher`) instead of opening a browser print tab on the phone.

`env.build` is listed in `.gitignore` so your LAN URL stays local.

## 3. Build `www/` and sync native projects

**Mac / Linux**

```bash
cd apps/mobile
chmod +x build-booth.sh
./build-booth.sh
```

**Windows (Command Prompt from `apps\mobile`)**

```bat
build-booth.bat
```

**Manual (same as the scripts)**

```bash
cd apps/mobile
npm install
export PHOTOBOOTH_API_BASE=http://192.168.x.x:8001
export PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT=1
npm run prepare-www
npx cap sync android ios
```

## 4. Produce APK / IPA

- **Android:** open `android/` in Android Studio → **Build** → **Build Bundle(s) / APK(s)**.
- **iOS:** open `ios/App/App.xcworkspace` in Xcode → run on a device or **Archive** for TestFlight/App Store.

CI can also run **`npm run prepare-www`** and **`npx cap sync`** — see `.github/workflows/mobile-build.yml`.

## 5. Booth checklist (end-to-end)

| Step | Where |
|------|--------|
| API + watcher | PC: `run-api-standalone`, `.env.standalone` with printer + optional dropzone |
| Mobile bundle | This doc: `env.build` + `./build-booth.sh` |
| Phone | Same Wi‑Fi as PC; install new APK; open app → should reach **`/health`** |

Optional: **`PHOTOBOOTH_CONNECTIVITY_DEBUG=1`** in `env.build` to show the connectivity panel until everything is stable.
