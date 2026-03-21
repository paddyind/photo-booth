# Stop Photo Booth standalone (API + print watcher) for THIS repo copy only.
# Called from stop-photo-booth-standalone.bat with -RepoRoot "C:\path\to\photo-booth"
param(
    [Parameter(Mandatory = $true)]
    [string] $RepoRoot
)

$ErrorActionPreference = "Continue"
$normalized = [System.IO.Path]::GetFullPath($RepoRoot.TrimEnd('\', '/'))
$rootCompare = $normalized.ToLowerInvariant().Replace('\', '/')

Write-Host ""
Write-Host "Photo Booth — stopping processes for this folder:" -ForegroundColor Cyan
Write-Host "  $normalized"
Write-Host ""

$names = @("python.exe", "python3.exe", "pythonw.exe")
$stopped = 0

try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $names -contains $_.Name }
} catch {
    $procs = @()
}

foreach ($p in $procs) {
    $cmd = [string]$p.CommandLine
    if ([string]::IsNullOrWhiteSpace($cmd)) { continue }

    $cmdNorm = $cmd.ToLowerInvariant().Replace('\', '/')
    if (-not $cmdNorm.Contains($rootCompare)) { continue }

    $isOurs = $cmd -match 'photo_booth_standalone\.py' -or
              $cmd -match 'print_watcher\.py' -or
              $cmd -match 'uvicorn.*apps\.api\.app\.main'

    if (-not $isOurs) { continue }

    Write-Host "  Stopping PID $($p.ProcessId) ($($p.Name))"
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        $stopped++
    } catch {
        Write-Host "    (could not stop: $($_.Exception.Message))" -ForegroundColor Yellow
    }
}

if ($stopped -eq 0) {
    Write-Host "  No running Photo Booth Python processes found for this folder." -ForegroundColor DarkGray
    Write-Host "  (If the server is still open in another window, close that window or press Ctrl+C there.)"
} else {
    Write-Host ""
    Write-Host "  Stopped $stopped process(es)." -ForegroundColor Green
}

Write-Host ""
