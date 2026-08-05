[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ComfyRoot,
    [Parameter(Mandatory = $true)][string]$ProbeEvidence,
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"),
    [string]$Endpoint = "http://127.0.0.1:8188"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& python "$PSScriptRoot\runtime.py" benchmark `
    --comfy-root $ComfyRoot `
    --state-root $StateRoot `
    --endpoint $Endpoint `
    --probe-evidence $ProbeEvidence
if ($LASTEXITCODE -ne 0) { throw "FLUX.2 Klein 1/2/10-reference benchmark failed" }
