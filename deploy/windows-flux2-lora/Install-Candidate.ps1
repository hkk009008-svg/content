param()

$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'

$python = (Get-Command py.exe -ErrorAction Stop).Source
& $python -3.12 (Join-Path $PSScriptRoot 'install.py')
if ($LASTEXITCODE -ne 0) {
    throw "LoRA candidate installation failed closed (exit $LASTEXITCODE)"
}
