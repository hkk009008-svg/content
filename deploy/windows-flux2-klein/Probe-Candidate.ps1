[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ComfyRoot,
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"),
    [string]$Endpoint = "http://127.0.0.1:8188"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& python "$PSScriptRoot\runtime.py" probe `
    --comfy-root $ComfyRoot `
    --state-root $StateRoot `
    --endpoint $Endpoint
if ($LASTEXITCODE -ne 0) {
    throw "FLUX.2 Klein fixed probe failed or is UNKNOWN; do not retry until evidence is inspected"
}
