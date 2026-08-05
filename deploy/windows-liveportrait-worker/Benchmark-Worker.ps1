[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$startScript = Join-Path $InstallRoot "package\Start-Worker.ps1"
$python = Join-Path $InstallRoot "venv\Scripts\python.exe"
$normalizer = Join-Path $InstallRoot "package\normalize_benchmark.py"
$resultPath = Join-Path $InstallRoot "state\benchmark.json"
$normalizedPath = Join-Path $InstallRoot "state\benchmark.normalized.json"
$resultTempPath = "$resultPath.tmp"
$lastPreflight = Join-Path $InstallRoot "state\last-preflight.json"

foreach ($required in @($startScript, $python, $normalizer)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Run Install-Worker.ps1 first: missing $required" }
}
Remove-Item -LiteralPath $resultPath, $resultTempPath, $normalizedPath -Force -ErrorAction SilentlyContinue

try {
    & $startScript -InstallRoot $InstallRoot -Benchmark
    if (-not (Test-Path -LiteralPath $resultPath)) {
        throw "Benchmark returned without durable evidence"
    }
    $record = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if (
        $record.status -ne "benchmark_passed_restart_pending" -or
        $record.role -ne "performance-liveportrait" -or
        $record.schema_version -ne 3 -or
        $record.frame_count -ne 200 -or
        $record.clip_seconds -ne 8 -or
        $record.measured_jobs -ne 10 -or
        $record.max_concurrency -ne 1 -or
        $record.comfy_cache_mode -ne "none" -or
        $record.all_outputs_decoded -ne $true
    ) {
        throw "Benchmark evidence is incomplete"
    }

    # A second clean supervisor cycle proves that the worker can release the
    # GPU, restart, and execute again after the measured batch.
    & $startScript -InstallRoot $InstallRoot -PreflightOnly
    if (-not (Test-Path -LiteralPath $lastPreflight)) {
        throw "Restart recovery returned without preflight evidence"
    }
    $restart = Get-Content -LiteralPath $lastPreflight -Raw | ConvertFrom-Json
    if (
        $restart.status -ne "ready" -or
        $restart.role -ne "performance-liveportrait" -or
        $restart.execution_canary.state -ne "passed"
    ) {
        throw "Restart recovery evidence is incomplete"
    }

    $record.status = "passed"
    $record.restart_recovery = [ordered]@{
        state = "passed"
        checked_at_unix = $restart.checked_at_unix
        prompt_id = $restart.execution_canary.prompt_id
    }
    $record | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $resultTempPath -Encoding UTF8
    Move-Item -LiteralPath $resultTempPath -Destination $resultPath -Force
    & $python "-B" $normalizer --raw $resultPath --output $normalizedPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $normalizedPath)) {
        throw "Benchmark normalization or validation failed"
    }
    Write-Output "WORKER_BENCHMARK_PASSED"
    exit 0
} catch {
    if (Test-Path -LiteralPath $resultPath) {
        try {
            $failed = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
            $failed.status = "failed"
            $failed.restart_recovery = [ordered]@{
                state = "failed"
                error = $_.Exception.Message
            }
            $failed | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $resultTempPath -Encoding UTF8
            Move-Item -LiteralPath $resultTempPath -Destination $resultPath -Force
        } catch {
            # Preserve the original benchmark record if failure annotation fails.
        }
    }
    Write-Error ("WORKER_BENCHMARK_FAILED: " + $_.Exception.Message)
    exit 1
}
