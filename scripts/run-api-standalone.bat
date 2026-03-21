@echo off
REM FastAPI on host, default port 8001 (Docker uses 8000). Offline / LAN OK.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo No .venv found. Run: scripts\setup-standalone-venv.bat
  exit /b 1
)
set "PYTHONPATH=%CD%"
if not defined DATA_DIR set "DATA_DIR=%CD%\data-standalone"
if not defined FRAMES_DIR set "FRAMES_DIR=%CD%\shared\frames"
if not defined API_PORT set "API_PORT=8001"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
echo Standalone API: http://0.0.0.0:%API_PORT%  (LAN: http://^<this-pc-ip^>:%API_PORT%)
echo DATA_DIR=%DATA_DIR%
echo FRAMES_DIR=%FRAMES_DIR%
call .venv\Scripts\activate.bat
uvicorn apps.api.app.main:app --host 0.0.0.0 --port %API_PORT%
endlocal
