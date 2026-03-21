================================================================================
  Photo Booth — Standalone API on Windows (run-api-standalone.bat)
================================================================================

TWO-PART SETUP — PHONE APP + LAPTOP (NO EXTRA STARTUP SCRIPTS)
  • You do NOT merge these into one installer. They stay separate on purpose:
      (1) Phone or tablet: install the Photo Booth APK (built with PHOTOBOOTH_API_BASE = this PC’s LAN URL).
      (2) Laptop: clone/open the repo and run  scripts\run-api-standalone.bat  — same script as always.
  • The phone only talks to the API over Wi‑Fi. The PRINTER is used by the LAPTOP: install the
    printer in Windows on that machine, then set PHOTOBOOTH_PRINTER_NAME in .env.standalone to the
    exact queue name (see scripts\list-printers.ps1). Nothing on the phone connects to the printer.
  • For folder-based printing (recommended with the mobile “suppress browser print” build), use
    queue mode in .env.standalone: PHOTOBOOTH_PRINT_WATCH_MODE=queue and
    PHOTOBOOTH_COPY_FINAL_TO_PRINT_QUEUE=1 — the API copies finals to DATA_DIR\print-queue and
    print_watcher prints them. Start order: run run-api-standalone.bat first (or restart it after
    changing .env.standalone); the app on the phone can be opened anytime after /health works.

WHERE TO RUN
  • Open Command Prompt (cmd) or PowerShell.
  • cd to the photo-booth folder (the one that contains "apps" and "scripts").
  • Run:   scripts\run-api-standalone.bat
  • Leave the window OPEN while the booth runs. Ctrl+C stops it.

FORCE STOP / RESTART (if frozen or errors)
  • scripts\restart-photo-booth-standalone.bat   ← stop this booth + start again (easiest)
  • scripts\stop-photo-booth-standalone.bat    ← stop only; then run run-api-standalone.bat
  • Plain-English guide:  scripts\PHOTO-BOOTH-END-USER-START.txt

PORT 8001 (DEFAULT API_PORT) — STAYS ON 8001
  • By default the script STOPS whatever is listening on API_PORT (8001), then binds there.
    Your phone URL can stay http://YOUR-PC-IP:8001 — no silent switch to 8002+.
  • Legacy: set PHOTOBOOTH_PORT_FALLBACK=1 in .env.standalone to scan 8002, 8003, … (then match that port on the phone).
  • After it starts, read the box in the window:
      Local:  http://127.0.0.1:PORT
      LAN:    http://YOUR-PC-IP:PORT
  • On the phone, set PHOTOBOOTH_API_BASE to the LAN line (same Wi-Fi as the PC).

WINERROR 10013 / “access permissions” ON BIND (NOT THE PRINTER)
  • If Python crashes with PermissionError or WinError 10013 on socket bind, Windows is blocking
    that port — often NOT because another app has it, but because Hyper-V, WSL2, or Docker Desktop
    reserved an “excluded port range” that includes 8001 (sometimes many ports in the 79xx–81xx range).
  • Pinned mode keeps retrying API_PORT; it cannot “un-reserve” an excluded range. If it still fails, try:
      set API_PORT=18080
      scripts\run-api-standalone.bat
  • Inspect excluded ranges (cmd or PowerShell):
      netsh interface ipv4 show excludedportrange protocol=tcp
  • This is unrelated to the physical printer; printing still works once the API starts.

TEST FROM PHONE BROWSER BEFORE THE APP
  • After the server starts, on the phone open Chrome and go to:
      http://YOUR-PC-LAN-IP:PORT/health
    (Use the PORT printed in the window — same as PHOTOBOOTH_API_BASE.)
  • You should see JSON like:  "status":"ok" , "service":"photo-booth-api"
  • If that works, the mobile app can use the same base URL.

LAPTOP MOBILE HOTSPOT (phone joins the PC’s network)
  • This is OK — the phone and laptop are on the same private LAN. Use the same LAN: URL as for Wi‑Fi.
  • The IP is still the one shown in the server window (often 192.168.x.x). Open /health on the phone.
  • Windows Firewall: allow inbound TCP on your API PORT for Python (see FIREWALL section below).

COMMON TYPO — ERR_ADDRESS_UNREACHABLE
  • Private LAN addresses almost always start with  192.168.   (192 — one nine two)
  • If you type  198.168.…   (198 — one nine eight) the phone cannot reach the PC. Fix the first octet.

PHONE URL RULES
  • Use the PC’s IPv4 address (shown as LAN), e.g. http://192.168.1.50:8001
  • Do NOT use 127.0.0.1 on the phone (that means “the phone itself”).

WINDOWS FIREWALL (if the phone cannot connect but the PC browser can)
  • Allow inbound TCP on the API port for Python (the process running uvicorn).
  • Example (PowerShell as Administrator, port 8001 — change if your window shows another port):
      New-NetFirewallRule -DisplayName "Photo Booth API 8001" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
  • Or: Windows Security → Firewall → Advanced settings → Inbound Rules → New Rule → Port → TCP → 8001 → Allow.
  • Test from another machine:  curl http://YOUR-PC-IP:8001/health

OPTIONAL: LEGACY — SCAN 8002+ OR STRICT SINGLE PORT
  • PHOTOBOOTH_PORT_FALLBACK=1  — if API_PORT is busy, try 8002, 8003, …
  • With fallback on: PHOTOBOOTH_STRICT_PORT=1  — fail if API_PORT busy (no scan).

OPTIONAL: PICK A DIFFERENT FIXED PORT
  • set API_PORT=8010
  • scripts\run-api-standalone.bat
  • (Default: clears listeners on that port; with PHOTOBOOTH_PORT_FALLBACK=1 it may scan upward if still busy.)

OPTIONAL: FREE A PORT MANUALLY (only if you really need to)
  • netstat -ano | findstr :8001
  • Note the PID in the last column for the LISTENING line.
  • taskkill /PID <pid> /F

GET LAN IP IN ANOTHER WINDOW (while server runs)
  • cd to photo-booth
  • .venv\Scripts\activate
  • python scripts\standalone_preflight.py lan-ip

CONFIG FILE (optional)
  • Copy .env.standalone.example to .env.standalone in the repo root.
  • Same folder as "apps" and "scripts".

================================================================================
