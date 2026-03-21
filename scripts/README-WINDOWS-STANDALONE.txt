================================================================================
  Photo Booth — Standalone API on Windows (run-api-standalone.bat)
================================================================================

WHERE TO RUN
  • Open Command Prompt (cmd) or PowerShell.
  • cd to the photo-booth folder (the one that contains "apps" and "scripts").
  • Run:   scripts\run-api-standalone.bat

PORT 8001 “ALREADY IN USE” — YOU USUALLY DO NOTHING
  • The script automatically tries 8001, then 8002, 8003, … until one is free.
  • After it starts, read the box in the window:
      Local:  http://127.0.0.1:PORT
      LAN:    http://YOUR-PC-IP:PORT
  • On the phone, set PHOTOBOOTH_API_BASE to the LAN line (same Wi-Fi as the PC).
  • If the PORT is 8002 (or higher), use that number — not always 8001.

PHONE URL RULES
  • Use the PC’s IPv4 address (shown as LAN), e.g. http://192.168.1.50:8002
  • Do NOT use 127.0.0.1 on the phone (that means “the phone itself”).

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
