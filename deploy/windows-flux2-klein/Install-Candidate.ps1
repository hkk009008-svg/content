[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ComfyRoot,
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& python "$PSScriptRoot\preflight.py"
if ($LASTEXITCODE -ne 0) { throw "Static FLUX.2 Klein candidate preflight failed" }

& python "$PSScriptRoot\install.py" `
    --comfy-root $ComfyRoot `
    --state-root $StateRoot
if ($LASTEXITCODE -ne 0) { throw "FLUX.2 Klein candidate install failed" }

Write-Host "Installed exact candidate artifacts. Readiness remains needs execution probe."
