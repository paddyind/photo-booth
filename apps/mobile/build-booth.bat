@echo off
REM Build mobile www + cap sync (Windows). From repo: apps\mobile\
REM 1) Copy env.build.example to env.build and set PHOTOBOOTH_API_BASE
REM 2) Run:  build-booth.bat

cd /d "%~dp0"

if not exist "env.build" (
  echo Missing env.build — copy env.build.example to env.build and set PHOTOBOOTH_API_BASE.
  exit /b 1
)

REM Load KEY=value lines (skip # comments and blanks)
for /f "usebackq eol=# delims=" %%L in ("env.build") do (
  if not "%%L"=="" set "%%L"
)

if "%PHOTOBOOTH_API_BASE%"=="" (
  echo PHOTOBOOTH_API_BASE is empty. Edit env.build ^(e.g. http://192.168.0.50:8001^).
  exit /b 1
)

if "%PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT%"=="" set PHOTOBOOTH_SUPPRESS_REAR_BROWSER_PRINT=1

echo API base: %PHOTOBOOTH_API_BASE%
call npm install
call npm run prepare-www

if exist "android\" goto sync
if exist "ios\" goto sync
echo.
echo www\ is ready. First time: npx cap add android   then npx cap add ios   then run this again.
exit /b 0

:sync
call npx cap sync android ios
echo.
echo Done. Open android\ in Android Studio to build APK.
