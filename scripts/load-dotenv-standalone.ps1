# Load KEY=value lines into current process environment (used by run-api-standalone.bat).
param(
    [Parameter(Mandatory = $true)]
    [string] $Path
)
if (-not (Test-Path -LiteralPath $Path)) { exit 0 }
Get-Content -LiteralPath $Path | ForEach-Object {
    $t = $_.Trim()
    if ($t -match '^\s*#' -or $t -eq '') { return }
    if ($t -match '^export\s+') { $t = $t -replace '^export\s+', '' }
    if ($t -match '^([^=]+)=(.*)$') {
        $k = $matches[1].Trim()
        $v = $matches[2].Trim()
        if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }
}
