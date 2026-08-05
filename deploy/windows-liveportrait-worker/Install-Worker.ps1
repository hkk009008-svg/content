[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

function Assert-PinnedRepositoryClean {
    param(
        [Parameter(Mandatory = $true)]$Component,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    $statusLines = @(& git -C $Destination status --ignored --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect source status: $Destination" }
    $allowedUntracked = @()
    if ([string]$Component.id -eq "comfyui") {
        $allowedUntracked = @(
            "?? custom_nodes/ComfyUI-LivePortraitKJ/",
            "?? custom_nodes/ComfyUI-LivePortraitKJ",
            "?? custom_nodes/ComfyUI-VideoHelperSuite/",
            "?? custom_nodes/ComfyUI-VideoHelperSuite",
            "!! custom_nodes/ComfyUI-LivePortraitKJ/",
            "!! custom_nodes/ComfyUI-LivePortraitKJ",
            "!! custom_nodes/ComfyUI-VideoHelperSuite/",
            "!! custom_nodes/ComfyUI-VideoHelperSuite",
            # The shared FLUX.2 candidate installs only these three exact,
            # manifest-bound model destinations. Do not permit either whole
            # model directories or a filename prefix here.
            "!! models/diffusion_models/flux-2-klein-4b-fp8.safetensors",
            "!! models/text_encoders/qwen_3_4b.safetensors",
            "!! models/vae/flux2-klein-vae-bf16.safetensors"
        )
    }
    $unexpected = @($statusLines | Where-Object {
        $_ -and
        $_ -notin $allowedUntracked -and
        -not (
            [string]$Component.id -eq "comfyui" -and
            ($_ -eq "!! models/liveportrait" -or $_.StartsWith("!! models/liveportrait/"))
        )
    })
    if ($unexpected.Count -gt 0) {
        throw "Refusing to alter source with tracked or untracked changes: $Destination :: $($unexpected -join '; ')"
    }
}

function Sync-PinnedRepository {
    param(
        [Parameter(Mandatory = $true)]$Component,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $destination = Join-Path $Root ([string]$Component.path)
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $freshClone = $false
    if (-not (Test-Path (Join-Path $destination ".git"))) {
        if ((Test-Path $destination) -and (Get-ChildItem -LiteralPath $destination -Force | Select-Object -First 1)) {
            throw "Refusing to replace non-repository path: $destination"
        }
        Invoke-Checked -Command "git" -Arguments @("clone", "--no-checkout", [string]$Component.repository, $destination)
        $freshClone = $true
    }
    $origin = (& git -C $destination remote get-url origin).Trim().TrimEnd("/").Replace(".git", "")
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect origin for $destination" }
    $expectedOrigin = ([string]$Component.repository).TrimEnd("/").Replace(".git", "")
    if ($origin -ne $expectedOrigin) {
        throw "Origin mismatch for $($Component.id): $origin"
    }
    # Existing installs are audited before any fetch/checkout mutation. A new
    # --no-checkout clone has an empty worktree by design, so audit it only
    # after the pinned commit has first been populated.
    if (-not $freshClone) {
        Assert-PinnedRepositoryClean -Component $Component -Destination $destination
    }
    Invoke-Checked -Command "git" -Arguments @("-C", $destination, "fetch", "--depth", "1", "origin", [string]$Component.commit)
    Invoke-Checked -Command "git" -Arguments @("-C", $destination, "checkout", "--detach", [string]$Component.commit)
    $actual = (& git -C $destination rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne [string]$Component.commit) {
        throw "Revision mismatch for $($Component.id)"
    }
    Assert-PinnedRepositoryClean -Component $Component -Destination $destination
}

function Install-VerifiedModels {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$ModelRoot
    )
    foreach ($artifact in $Manifest.artifacts) {
        $destination = Join-Path $ModelRoot ([string]$artifact.destination)
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        if (Test-Path $destination) {
            $existing = Get-Item -LiteralPath $destination
            $existingHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($existing.Length -ne [int64]$artifact.expected_bytes -or $existingHash -ne [string]$artifact.sha256) {
                throw "Existing model failed verification; remove it explicitly before retrying: $destination"
            }
            Write-Host "Verified existing model $($artifact.id)"
            continue
        }
        $temporary = "$destination.partial"
        if (Test-Path $temporary) { Remove-Item -LiteralPath $temporary -Force }
        Invoke-WebRequest -Uri ([string]$artifact.source.url) -OutFile $temporary -UseBasicParsing
        $downloaded = Get-Item -LiteralPath $temporary
        $downloadedHash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($downloaded.Length -ne [int64]$artifact.expected_bytes -or $downloadedHash -ne [string]$artifact.sha256) {
            Remove-Item -LiteralPath $temporary -Force
            throw "Downloaded model failed verification: $($artifact.id)"
        }
        Move-Item -LiteralPath $temporary -Destination $destination
        Write-Host "Installed verified model $($artifact.id)"
    }
    $expectedFiles = @(
        $Manifest.artifacts | ForEach-Object {
            [IO.Path]::GetFullPath((Join-Path $ModelRoot ([string]$_.destination)))
        }
    )
    $livePortraitRoot = Join-Path $ModelRoot "liveportrait"
    $allEntries = @(Get-ChildItem -LiteralPath $livePortraitRoot -Recurse -Force)
    $actualFiles = @($allEntries | Where-Object { -not $_.PSIsContainer })
    $linkedEntries = @($allEntries | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    })
    if ($linkedEntries.Count -gt 0) {
        throw "LivePortrait model directory may not contain links: $($linkedEntries.FullName -join '; ')"
    }
    $extraFiles = @($actualFiles | Where-Object {
        [IO.Path]::GetFullPath($_.FullName) -notin $expectedFiles
    })
    if ($extraFiles.Count -gt 0 -or $actualFiles.Count -ne $expectedFiles.Count) {
        throw "LivePortrait model inventory contains unexpected or missing files"
    }
}

function Install-ProbeAssets {
    param(
        [Parameter(Mandatory = $true)][string]$PackageRoot,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $packageProbeRoot = Join-Path $PackageRoot "probes"
    $targetProbeRoot = Join-Path $Root "probes"
    $targetInputRoot = Join-Path $Root "input"
    $contractSource = Join-Path $packageProbeRoot "probe.json"
    $contract = Get-Content -LiteralPath $contractSource -Raw | ConvertFrom-Json
    $workflowSource = Join-Path $packageProbeRoot ([string]$contract.workflow)
    $workflowHash = (Get-FileHash -LiteralPath $workflowSource -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($workflowHash -ne [string]$contract.workflow_sha256) {
        throw "Tracked expression workflow failed its SHA-256 contract"
    }
    foreach ($source in @($contractSource, $workflowSource)) {
        $destination = Join-Path $targetProbeRoot (Split-Path -Leaf $source)
        if (Test-Path $destination) {
            $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
            $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
            if ($sourceHash -ne $destinationHash) {
                throw "Existing probe file differs from the tracked contract: $destination"
            }
        } else {
            Copy-Item -LiteralPath $source -Destination $destination
        }
    }
    foreach ($fixture in $contract.fixtures) {
        $destination = Join-Path $targetInputRoot ([string]$fixture.path)
        if (-not (Test-Path $destination)) {
            $payload = Join-Path $PackageRoot ("fixtures\" + [string]$fixture.path + ".b64")
            if (-not (Test-Path $payload)) { throw "Fixture payload is missing: $payload" }
            $temporary = "$destination.partial"
            [IO.File]::WriteAllBytes(
                $temporary,
                [Convert]::FromBase64String((Get-Content -LiteralPath $payload -Raw))
            )
            $temporaryFile = Get-Item -LiteralPath $temporary
            $temporaryHash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($temporaryFile.Length -ne [int64]$fixture.expected_bytes -or $temporaryHash -ne [string]$fixture.sha256) {
                Remove-Item -LiteralPath $temporary -Force
                throw "Decoded probe fixture failed verification: $($fixture.path)"
            }
            Move-Item -LiteralPath $temporary -Destination $destination
        }
        $installed = Get-Item -LiteralPath $destination
        $installedHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($installed.Length -ne [int64]$fixture.expected_bytes -or $installedHash -ne [string]$fixture.sha256) {
            throw "Installed probe fixture failed verification: $destination"
        }
    }
}

function Get-ExactPackageInventory {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootItem = Get-Item -LiteralPath $Root -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Worker package root may not be a link: $Root"
    }
    $rootPrefix = $rootItem.FullName.TrimEnd("\") + "\"
    $inventory = @()
    foreach ($entry in @(Get-ChildItem -LiteralPath $Root -Recurse -Force)) {
        if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Worker package may not contain links: $($entry.FullName)"
        }
        if ($entry.PSIsContainer) { continue }
        if (-not $entry.FullName.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Worker package inventory escaped its root: $($entry.FullName)"
        }
        $relativePath = $entry.FullName.Substring($rootPrefix.Length)
        $segments = @($relativePath -split "[\\/]")
        if ($segments -contains "__pycache__" -or $entry.Extension -ieq ".pyc") {
            continue
        }
        $inventory += [PSCustomObject]@{
            RelativePath = $relativePath
            FullName = $entry.FullName
            Sha256 = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return @($inventory | Sort-Object -Property RelativePath)
}

function Remove-PythonBytecode {
    param([Parameter(Mandatory = $true)][string]$Root)
    # Inventory first so no recursive removal is attempted in a linked tree.
    @(Get-ExactPackageInventory -Root $Root) | Out-Null
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File | Where-Object {
        $_.Extension -ieq ".pyc"
    })) {
        Remove-Item -LiteralPath $file.FullName -Force
    }
    $cacheDirectories = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory | Where-Object {
        $_.Name -ieq "__pycache__"
    } | Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $cacheDirectories) {
        Remove-Item -LiteralPath $directory.FullName -Recurse -Force
    }
}

function Install-ExactPackage {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePackage,
        [Parameter(Mandatory = $true)][string]$InstalledPackage,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $sourceResolved = (Resolve-Path -LiteralPath $SourcePackage).Path
    if ((Test-Path -LiteralPath $InstalledPackage) -and
        $sourceResolved -ieq (Resolve-Path -LiteralPath $InstalledPackage).Path) {
        Remove-PythonBytecode -Root $InstalledPackage
        return
    }

    $sourceInventory = @(Get-ExactPackageInventory -Root $SourcePackage)
    if ($sourceInventory.Count -eq 0) { throw "Worker source package is empty" }
    if (Test-Path -LiteralPath $InstalledPackage) {
        # Audit before moving or recursively removing the old package.
        @(Get-ExactPackageInventory -Root $InstalledPackage) | Out-Null
    }

    $identifier = [Guid]::NewGuid().ToString("N")
    $stagingPackage = Join-Path $Root "package-stage-$identifier"
    $backupPackage = Join-Path $Root "package-backup-$identifier"
    New-Item -ItemType Directory -Path $stagingPackage | Out-Null
    try {
        foreach ($source in $sourceInventory) {
            $destination = Join-Path $stagingPackage ([string]$source.RelativePath)
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath ([string]$source.FullName) -Destination $destination
        }

        $stagedInventory = @(Get-ExactPackageInventory -Root $stagingPackage)
        if ($stagedInventory.Count -ne $sourceInventory.Count) {
            throw "Staged worker package inventory is incomplete"
        }
        $stagedByPath = @{}
        foreach ($entry in $stagedInventory) {
            $stagedByPath[[string]$entry.RelativePath] = [string]$entry.Sha256
        }
        foreach ($source in $sourceInventory) {
            if ($stagedByPath[[string]$source.RelativePath] -ne [string]$source.Sha256) {
                throw "Staged worker package differs from source: $($source.RelativePath)"
            }
        }

        $backedUp = $false
        if (Test-Path -LiteralPath $InstalledPackage) {
            Move-Item -LiteralPath $InstalledPackage -Destination $backupPackage
            $backedUp = $true
        }
        try {
            Move-Item -LiteralPath $stagingPackage -Destination $InstalledPackage
        } catch {
            if ($backedUp -and -not (Test-Path -LiteralPath $InstalledPackage)) {
                Move-Item -LiteralPath $backupPackage -Destination $InstalledPackage
            }
            throw
        }
        if ($backedUp) {
            Remove-Item -LiteralPath $backupPackage -Recurse -Force
        }
    } finally {
        if (Test-Path -LiteralPath $stagingPackage) {
            Remove-Item -LiteralPath $stagingPackage -Recurse -Force
        }
    }
}

$caption = (Get-CimInstance Win32_OperatingSystem).Caption
if ($caption -notmatch "Windows 11") { throw "This profile requires Windows 11; found $caption" }
if (-not [Environment]::Is64BitOperatingSystem) { throw "This profile requires 64-bit Windows" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git for Windows is required" }
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "The Python launcher is required" }
$pythonVersion = (& py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.12") { throw "CPython 3.12 x64 is required" }

$sourcePackage = $PSScriptRoot
$revisions = Get-Content -LiteralPath (Join-Path $sourcePackage "revisions.json") -Raw | ConvertFrom-Json
$models = Get-Content -LiteralPath (Join-Path $sourcePackage "models.json") -Raw | ConvertFrom-Json
if ($revisions.schema_version -ne 1 -or $models.schema_version -ne 1) {
    throw "Unsupported deployment manifest schema"
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
foreach ($directory in @("cache", "input", "logs", "output", "probes", "state", "temp", "user")) {
    New-Item -ItemType Directory -Path (Join-Path $InstallRoot $directory) -Force | Out-Null
}
$installedPackage = Join-Path $InstallRoot "package"
Install-ExactPackage `
    -SourcePackage $sourcePackage `
    -InstalledPackage $installedPackage `
    -Root $InstallRoot

foreach ($component in $revisions.components) {
    Sync-PinnedRepository -Component $component -Root $InstallRoot
}

$comfyRoot = Join-Path $InstallRoot "sources\ComfyUI"
$venvRoot = Join-Path $InstallRoot "venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Invoke-Checked -Command "py" -Arguments @("-3.12", "-m", "venv", $venvRoot)
}
Invoke-Checked -Command $venvPython -Arguments @(
    "-m", "pip", "install", "--disable-pip-version-check",
    "--requirement", (Join-Path $installedPackage "requirements.lock")
)
Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "check")

Install-ProbeAssets -PackageRoot $installedPackage -Root $InstallRoot
Install-VerifiedModels -Manifest $models -ModelRoot (Join-Path $comfyRoot "models")
& $venvPython -m pip freeze | Set-Content -LiteralPath (Join-Path $InstallRoot "state\pip-freeze.txt") -Encoding UTF8
if ($LASTEXITCODE -ne 0) { throw "Could not record installed Python environment" }

Write-Host "Installation complete at $InstallRoot"
Write-Host "No worker was started or registered. Set the DPAPI secret before validation and registration."
