#!/usr/bin/env bash
# List printer names for PHOTOBOOTH_PRINTER_NAME (CUPS / lp).
if command -v lpstat >/dev/null 2>&1; then
  echo "Printers (use exact name for PHOTOBOOTH_PRINTER_NAME):"
  lpstat -p 2>/dev/null | sed -n 's/^printer //p' | sed 's/ is.*//' | while read -r n; do
    [[ -n "$n" ]] && echo "  $n"
  done
else
  echo "lpstat not found. On macOS/Linux install/use CUPS; on Windows run: powershell -File scripts/list-printers.ps1"
fi
