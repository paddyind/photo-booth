# List Windows printer queue names (use exact string for PHOTOBOOTH_PRINTER_NAME).
Write-Host "Installed printers:" -ForegroundColor Cyan
Get-Printer | ForEach-Object { Write-Host "  $($_.Name)" }
