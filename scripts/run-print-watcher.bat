@echo off
setlocal
cd /d "%~dp0\.."

if not defined PHOTOBOOTH_DATA_DIR set "PHOTOBOOTH_DATA_DIR=%CD%\data-standalone"

py -3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYEXE=py -3"
) else (
  set "PYEXE=python"
)

%PYEXE% -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul || (
  echo Python 3.10+ required.
  exit /b 1
)

%PYEXE% -c "import watchdog" 2>nul || (
  echo Installing print-watcher dependencies...
  %PYEXE% -m pip install -q -r "%CD%\scripts\requirements-print-watcher.txt"
)

echo PHOTOBOOTH_DATA_DIR=%PHOTOBOOTH_DATA_DIR%
%PYEXE% "%CD%\scripts\print_watcher.py" --data-dir "%PHOTOBOOTH_DATA_DIR%" %*
