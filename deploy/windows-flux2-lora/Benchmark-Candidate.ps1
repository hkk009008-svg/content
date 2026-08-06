param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{32}$')]
    [string]$JobId
)

$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$stateRoot = Join-Path $env:ProgramData 'Content\IdentityLab\flux2-lora'
$python = Join-Path $stateRoot 'runtime\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Pinned LoRA runtime is not installed'
}

& $python (Join-Path $PSScriptRoot 'benchmark.py') $JobId
if ($LASTEXITCODE -ne 0) {
    throw "LoRA inference benchmark did not pass; inspect immutable job evidence (exit $LASTEXITCODE)"
}
