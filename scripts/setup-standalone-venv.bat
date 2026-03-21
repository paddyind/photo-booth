@echo off
REM One-time setup: venv + API deps for standalone mode (Windows).
setlocal
cd /d "%~dp0.."
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.11+ and ensure it is on PATH.
  exit /b 1
)
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r apps\api\requirements.txt
echo Done. Run: scripts\run-api-standalone.bat
endlocal
