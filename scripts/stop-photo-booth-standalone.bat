@echo off
REM ========================================================================
REM  Photo Booth — FORCE STOP (Windows)
REM  Stops Python processes running THIS photo-booth folder only (API + watcher).
REM  Safe to run anytime. Then start again with: scripts\run-api-standalone.bat
REM ========================================================================
setlocal EnableExtensions
cd /d "%~dp0.."
if not exist "apps\api\requirements.txt" (
  echo Run this from inside the photo-booth project ^(missing apps\api\requirements.txt^).
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-photo-booth-standalone.ps1" -RepoRoot "%CD%"
echo.
echo Next step: double-click or run  scripts\run-api-standalone.bat  to start fresh.
echo.
pause
endlocal
