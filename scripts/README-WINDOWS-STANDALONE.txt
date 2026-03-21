================================================================================
  Photo Booth — Standalone API on Windows (run-api-standalone.bat)
================================================================================

WHERE TO RUN
  • Open Command Prompt (cmd) or PowerShell.
  • cd to the photo-booth folder (the one that contains "apps" and "scripts").
  • Run:   scripts\run-api-standalone.bat
  • Leave the window OPEN while the booth runs. Ctrl+C stops it.

FORCE STOP / RESTART (if frozen or errors)
  • scripts\restart-photo-booth-standalone.bat   ← stop this booth + start again (easiest)
  • scripts\stop-photo-booth-standalone.bat    ← stop only; then run run-api-standalone.bat
  • Plain-English guide:  scripts\PHOTO-BOOTH-END-USER-START.txt

PORT 8001 “ALREADY IN USE” — YOU USUALLY DO NOTHING
  • The script automatically tries 8001, then 8002, 8003, … until one is free.
  • After it starts, read the box in the window:
      Local:  http://127.0.0.1:PORT
      LAN:    http://YOUR-PC-IP:PORT
  • On the phone, set PHOTOBOOTH_API_BASE to the LAN line (same Wi-Fi as the PC).
  • If the PORT is 8002 (or higher), use that number — not always 8001.

WINERROR 10013 / “access permissions” ON BIND (NOT THE PRINTER)
  • If Python crashes with PermissionError or WinError 10013 on socket bind, Windows is blocking
    that port — often NOT because another app has it, but because Hyper-V, WSL2, or Docker Desktop
    reserved an “excluded port range” that includes 8001 (sometimes many ports in the 79xx–81xx range).
  • The script now skips blocked ports and tries 8002, 8003, … automatically. If ALL fail, try:
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

PHONE URL RULES
  • Use the PC’s IPv4 address (shown as LAN), e.g. http://192.168.1.50:8002
  • Do NOT use 127.0.0.1 on the phone (that means “the phone itself”).

WINDOWS FIREWALL (if the phone cannot connect but the PC browser can)
  • Allow inbound TCP on the API port for Python (the process running uvicorn).
  • Example (PowerShell as Administrator, port 8001 — change if your window shows another port):
      New-NetFirewallRule -DisplayName "Photo Booth API 8001" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
  • Or: Windows Security → Firewall → Advanced settings → Inbound Rules → New Rule → Port → TCP → 8001 → Allow.
  • Test from another machine:  curl http://YOUR-PC-IP:8001/health

OPTIONAL: FORCE EXACT PORT OR FAIL
  • set PHOTOBOOTH_STRICT_PORT=1
  • scripts\run-api-standalone.bat
  • If that port is busy, the script stops and prints how to find the process.

OPTIONAL: PICK A START PORT
  • set API_PORT=8010
  • scripts\run-api-standalone.bat
  • (Still auto-increments if 8010–8034 are all taken.)

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
