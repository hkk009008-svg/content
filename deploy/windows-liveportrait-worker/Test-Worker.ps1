[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$startScript = Join-Path $InstallRoot "package\Start-Worker.ps1"
if (-not (Test-Path $startScript)) { throw "Run Install-Worker.ps1 first" }
$evidence = Join-Path $InstallRoot "state\last-preflight.json"
Remove-Item -LiteralPath $evidence -Force -ErrorAction SilentlyContinue
try {
    & $startScript -InstallRoot $InstallRoot -PreflightOnly
    if (-not (Test-Path $evidence)) {
        throw "Worker preflight returned without durable execution evidence"
    }
    $record = Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json
    if (
        $record.status -ne "ready" -or
        $record.role -ne "performance-liveportrait" -or
        $record.execution_proven -ne $true -or
        $record.execution_canary.state -ne "passed"
    ) {
        throw "Worker preflight evidence is incomplete"
    }
    Write-Output "WORKER_PREFLIGHT_PASSED"
    exit 0
} catch {
    Write-Error ("WORKER_PREFLIGHT_FAILED: " + $_.Exception.Message)
    exit 1
}
