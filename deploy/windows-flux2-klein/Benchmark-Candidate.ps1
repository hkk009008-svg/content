[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ComfyRoot,
    [Parameter(Mandatory = $true)][string]$InputRoot,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [Parameter(Mandatory = $true)][string]$ProbeEvidence,
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"),
    [string]$Endpoint = "http://127.0.0.1:8188"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& python "$PSScriptRoot\runtime.py" benchmark `
    --comfy-root $ComfyRoot `
    --state-root $StateRoot `
    --input-root $InputRoot `
    --output-root $OutputRoot `
    --endpoint $Endpoint `
    --probe-evidence $ProbeEvidence
if ($LASTEXITCODE -ne 0) { throw "FLUX.2 Klein 1/2/4-reference benchmark failed" }
