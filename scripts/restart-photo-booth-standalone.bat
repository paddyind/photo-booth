@echo off
REM ========================================================================
REM  Photo Booth — FORCE STOP then START (Windows)
REM  Use this if the server is frozen, the port seems stuck, or after errors.
REM ========================================================================
setlocal EnableExtensions
cd /d "%~dp0.."
if not exist "apps\api\requirements.txt" (
  echo Run this from inside the photo-booth project.
  exit /b 1
)

echo.
echo  Step 1 of 2: Stopping any old Photo Booth server for this folder...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-photo-booth-standalone.ps1" -RepoRoot "%CD%"

echo.
echo  Step 2 of 2: Waiting 2 seconds, then starting the server...
timeout /t 2 /nobreak >nul
echo.

call "%~dp0run-api-standalone.bat"
exit /b %ERRORLEVEL%
