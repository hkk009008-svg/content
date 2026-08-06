[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MacIPAddress,
    [Parameter(Mandatory = $true)][string]$TunnelPublicKey,
    [Parameter(Mandatory = $true)][string]$ControlPublicKey,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker"),
    [string]$Flux2StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"),
    [string]$TaskName = "Content LivePortrait Worker"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AdministratorsSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
$SystemSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
$AclSections = (
    [Security.AccessControl.AccessControlSections]::Access -bor
    [Security.AccessControl.AccessControlSections]::Owner
)

function Assert-PlainPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet("File", "Directory")][string]$Kind
    )
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Path must not be a reparse point"
    }
    if ($Kind -eq "File" -and $item.PSIsContainer) { throw "$Path must be a regular file" }
    if ($Kind -eq "Directory" -and -not $item.PSIsContainer) { throw "$Path must be a directory" }
    $expected = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $actual = [IO.Path]::GetFullPath($item.FullName).TrimEnd('\')
    if (-not $actual.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Path resolved to an unexpected filesystem object"
    }
}

function Assert-ExactAdminAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet("File", "Directory")][string]$Kind
    )
    $acl = if ($Kind -eq "Directory") {
        [IO.Directory]::GetAccessControl($Path, $AclSections)
    } else {
        [IO.File]::GetAccessControl($Path, $AclSections)
    }
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -ne $AdministratorsSid.Value -or -not $acl.AreAccessRulesProtected) {
        throw "$Path owner or inheritance protection is not exact"
    }
    $rules = @($acl.GetAccessRules(
        $true,
        $true,
        [Security.Principal.SecurityIdentifier]
    ))
    if ($rules.Count -ne 2) { throw "$Path ACL has unexpected entries" }
    $expectedInheritance = if ($Kind -eq "Directory") {
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    foreach ($sid in @($AdministratorsSid, $SystemSid)) {
        $matching = @($rules | Where-Object {
            $_.IdentityReference.Value -eq $sid.Value -and
            $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
            -not $_.IsInherited -and
            $_.InheritanceFlags -eq $expectedInheritance -and
            $_.PropagationFlags -eq [Security.AccessControl.PropagationFlags]::None -and
            ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq
                [Security.AccessControl.FileSystemRights]::FullControl
        })
        if ($matching.Count -ne 1) { throw "$Path ACL is missing an exact protected principal" }
    }
}

function Set-ExactAdminAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet("File", "Directory")][string]$Kind
    )
    & (Join-Path $env:SystemRoot "System32\takeown.exe") /F $Path /A | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not take trusted ownership of $Path" }
    $security = if ($Kind -eq "Directory") {
        New-Object Security.AccessControl.DirectorySecurity
    } else {
        New-Object Security.AccessControl.FileSecurity
    }
    $security.SetOwner($AdministratorsSid)
    $security.SetAccessRuleProtection($true, $false)
    $inheritance = if ($Kind -eq "Directory") {
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    foreach ($sid in @($AdministratorsSid, $SystemSid)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            $inheritance,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$security.AddAccessRule($rule)
    }
    if ($Kind -eq "Directory") {
        [IO.Directory]::SetAccessControl($Path, $security)
    } else {
        [IO.File]::SetAccessControl($Path, $security)
    }
    Assert-ExactAdminAcl -Path $Path -Kind $Kind
}

function Write-ProtectedTextFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Value, $encoding)
    Assert-PlainPath -Path $Path -Kind File
    Set-ExactAdminAcl -Path $Path -Kind File
}

function Assert-EffectiveForwardingBoundary {
    param(
        [Parameter(Mandatory = $true)][string]$Sshd,
        [Parameter(Mandatory = $true)][string]$Config,
        [Parameter(Mandatory = $true)][string]$SshUser,
        [Parameter(Mandatory = $true)][string]$MacAddress,
        [Parameter(Mandatory = $true)][string]$LocalAddress,
        [Parameter(Mandatory = $true)][string]$AuthorizedKeys
    )
    $criteria = (
        "user=$SshUser,addr=$MacAddress,host=$MacAddress," +
        "laddr=$LocalAddress,lport=22"
    )
    $effective = @(& $Sshd -T -f $Config -C $criteria 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Could not evaluate the managed sshd policy" }
    $settings = @{}
    foreach ($line in $effective) {
        $parts = @(([string]$line).Trim() -split "\s+", 2)
        if ($parts.Count -eq 2 -and -not $settings.ContainsKey($parts[0])) {
            $settings[$parts[0]] = $parts[1]
        }
    }
    if ($settings["allowtcpforwarding"] -ne "local") {
        throw "Effective sshd policy does not forbid remote TCP forwarding"
    }
    if ($settings["allowstreamlocalforwarding"] -ne "no") {
        throw "Effective sshd policy does not forbid stream-local forwarding"
    }
    if ($settings["permitopen"] -ne "127.0.0.1:8189") {
        throw "Effective sshd policy does not pin the worker tunnel destination"
    }
    if ($settings["gatewayports"] -ne "no") {
        throw "Effective sshd policy does not keep forwarding loopback-scoped"
    }
    $authorizedValue = ([string]$settings["authorizedkeysfile"]).Trim('"').Replace('\', '/')
    $expectedAuthorizedValues = @(
        "__PROGRAMDATA__/ssh/administrators_authorized_keys",
        $AuthorizedKeys.Replace('\', '/')
    )
    if (-not ($expectedAuthorizedValues | Where-Object {
        $_.Equals($authorizedValue, [StringComparison]::OrdinalIgnoreCase)
    })) {
        throw "Effective sshd policy does not use the protected administrator key file"
    }
}

function Assert-SshdServiceContract {
    param([Parameter(Mandatory = $true)][string]$Sshd)
    $service = Get-CimInstance -ClassName Win32_Service -Filter "Name='sshd'" -ErrorAction Stop
    if ($null -eq $service) { throw "The Windows sshd service is not installed" }
    $actualImage = ([string]$service.PathName).Trim()
    $acceptedImages = @($Sshd, ('"' + $Sshd + '"'))
    if (-not ($acceptedImages | Where-Object {
        $_.Equals($actualImage, [StringComparison]::OrdinalIgnoreCase)
    })) {
        throw "The sshd service must use the fixed system binary and default configuration"
    }
    $startName = [string]$service.StartName
    if ($startName -notin @("LocalSystem", "NT AUTHORITY\LocalSystem")) {
        throw "The sshd service must run as LocalSystem"
    }
}

function Stop-SshdCleanly {
    $service = Get-Service -Name sshd -ErrorAction Stop
    if ($service.Status -ne "Stopped") {
        Stop-Service -Name sshd -Force -ErrorAction Stop
        $service.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(15))
    }
    Get-Process -Name sshd -ErrorAction SilentlyContinue | Stop-Process -Force
    if (@(Get-Process -Name sshd -ErrorAction SilentlyContinue).Count -ne 0) {
        throw "Could not terminate every pre-policy sshd session"
    }
}

function Start-SshdCleanly {
    Start-Service -Name sshd -ErrorAction Stop
    (Get-Service -Name sshd).WaitForStatus("Running", [TimeSpan]::FromSeconds(15))
}

function Test-Rfc1918IPv4 {
    param([Parameter(Mandatory = $true)][Net.IPAddress]$Address)
    if ($Address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        return $false
    }
    $octets = $Address.GetAddressBytes()
    return (
        $octets[0] -eq 10 -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168)
    )
}

function Get-NormalizedPublicKey {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $parts = @($Value.Trim() -split "\s+")
    if (
        $parts.Count -lt 2 -or
        $parts[0] -ne "ssh-ed25519" -or
        $parts[1] -notmatch "^[A-Za-z0-9+/]+={0,3}$"
    ) {
        throw "$Label must be one ssh-ed25519 public key"
    }
    try {
        $decoded = [Convert]::FromBase64String($parts[1])
    } catch {
        throw "$Label contains invalid base64"
    }
    $keyType = if ($decoded.Length -ge 15) {
        [Text.Encoding]::ASCII.GetString($decoded, 4, 11)
    } else {
        ""
    }
    if (
        $decoded.Length -ne 51 -or
        $decoded[0] -ne 0 -or $decoded[1] -ne 0 -or
        $decoded[2] -ne 0 -or $decoded[3] -ne 11 -or
        $keyType -ne "ssh-ed25519" -or
        $decoded[15] -ne 0 -or $decoded[16] -ne 0 -or
        $decoded[17] -ne 0 -or $decoded[18] -ne 32
    ) {
        throw "$Label is not a structurally valid Ed25519 public key"
    }
    return [pscustomobject]@{
        normalized = "$($parts[0]) $($parts[1])"
        blob = $parts[1]
    }
}

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from an elevated administrator session"
}
if (
    -not [string]::IsNullOrWhiteSpace([string]$env:SSH_CONNECTION) -or
    -not [string]::IsNullOrWhiteSpace([string]$env:SSH_CLIENT)
) {
    throw "Run this installer locally; an SSH-hosted process cannot survive the required session shutdown"
}

$parsedAddress = $null
if (
    -not [Net.IPAddress]::TryParse($MacIPAddress, [ref]$parsedAddress) -or
    -not (Test-Rfc1918IPv4 -Address $parsedAddress)
) {
    throw "MacIPAddress must be one concrete RFC1918 IPv4 address"
}
$MacIPAddress = $parsedAddress.ToString()
if (
    [string]::IsNullOrWhiteSpace($TaskName) -or
    $TaskName -cne "Content LivePortrait Worker" -or
    $TaskName -ne $TaskName.Trim() -or
    $TaskName.IndexOfAny([char[]]"\/") -ge 0
) {
    throw "TaskName must be one exact task name in the Task Scheduler root"
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$Flux2StateRoot = [IO.Path]::GetFullPath($Flux2StateRoot).TrimEnd('\')

$tunnel = Get-NormalizedPublicKey -Value $TunnelPublicKey -Label "TunnelPublicKey"
$control = Get-NormalizedPublicKey -Value $ControlPublicKey -Label "ControlPublicKey"
if ($tunnel.blob -eq $control.blob) {
    throw "Tunnel and control keys must be different"
}

$sshUser = [string]$env:USERNAME
if ($sshUser -notmatch "^[A-Za-z0-9_.-]{1,64}$") {
    throw "The current Windows user cannot be represented safely in an sshd Match rule"
}
$commonApplicationData = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::CommonApplicationData
).TrimEnd('\')
$environmentProgramData = [IO.Path]::GetFullPath([string]$env:ProgramData).TrimEnd('\')
if (
    [string]::IsNullOrWhiteSpace($commonApplicationData) -or
    -not $commonApplicationData.Equals(
        $environmentProgramData,
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "ProgramData does not match the system CommonApplicationData path"
}
$sshRoot = Join-Path $commonApplicationData "ssh"
Assert-PlainPath -Path $sshRoot -Kind Directory
$sshd = Join-Path $env:SystemRoot "System32\OpenSSH\sshd.exe"
$sshdConfig = Join-Path $sshRoot "sshd_config"
Assert-PlainPath -Path $sshd -Kind File
Assert-PlainPath -Path $sshdConfig -Kind File
# Validate the service identity before narrowing an ACL that the service must
# traverse. A rejected non-LocalSystem configuration must remain untouched.
Assert-SshdServiceContract -Sshd $sshd
Set-ExactAdminAcl -Path $sshRoot -Kind Directory
# This ACL narrowing is deliberate one-way hardening. Even a failed later
# preflight must not restore untrusted write/delete authority over sshd inputs.
Set-ExactAdminAcl -Path $sshdConfig -Kind File
$connections = @(Get-NetTCPConnection `
    -State Established `
    -LocalPort 22 `
    -RemoteAddress $MacIPAddress `
    -ErrorAction SilentlyContinue)
$localAddresses = @($connections | ForEach-Object { [string]$_.LocalAddress } | Sort-Object -Unique)
if ($localAddresses.Count -ne 1 -or $localAddresses[0] -notmatch "^\d+\.\d+\.\d+\.\d+$") {
    throw "Keep the Mac worker tunnel connected while installing the exact sshd boundary"
}
$localAddress = $localAddresses[0]

$ControlRoot = Join-Path $commonApplicationData "ContentWorkerControl"
$sourceControl = Join-Path $PSScriptRoot "Control-Worker.ps1"
if (-not (Test-Path -LiteralPath $sourceControl -PathType Leaf)) {
    throw "Control-Worker.ps1 is missing beside the installer"
}
Assert-PlainPath -Path $sourceControl -Kind File
$packageRoot = Join-Path $InstallRoot "package"
$startScript = Join-Path $packageRoot "Start-Worker.ps1"
Assert-PlainPath -Path $packageRoot -Kind Directory
Assert-PlainPath -Path $startScript -Kind File
$taskExecutable = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
Assert-PlainPath -Path $taskExecutable -Kind File
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskArguments = (
    "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" " +
    "-InstallRoot `"$InstallRoot`" -Flux2StateRoot `"$Flux2StateRoot`""
)
$contractPayload = [ordered]@{
    schema_version = 1
    task_name = $TaskName
    task_path = "\"
    install_root = $InstallRoot
    flux2_state_root = $Flux2StateRoot
    executable = $taskExecutable
    arguments = $taskArguments
    working_directory = $packageRoot
    principal_sid = $identity.User.Value
    logon_type = 3
    run_level = 0
    multiple_instances = 2
    execution_time_limit = "PT0S"
    start_script = $startScript
    start_script_sha256 = (Get-FileHash -LiteralPath $startScript -Algorithm SHA256).Hash.ToLowerInvariant()
}
$contractText = (($contractPayload | ConvertTo-Json -Compress -Depth 3) + [Environment]::NewLine)
New-Item -ItemType Directory -Path $ControlRoot -Force | Out-Null
Assert-PlainPath -Path $ControlRoot -Kind Directory
Set-ExactAdminAcl -Path $ControlRoot -Kind Directory
$installedControl = Join-Path $ControlRoot "Control-Worker.ps1"
$installedContract = Join-Path $ControlRoot "worker-control-contract.json"
$unexpectedControlEntries = @(Get-ChildItem -LiteralPath $ControlRoot -Force | Where-Object {
    $_.Name -notin @("Control-Worker.ps1", "worker-control-contract.json")
})
if ($unexpectedControlEntries.Count -gt 0) {
    throw "The dedicated control directory contains unexpected entries"
}
if (Test-Path -LiteralPath $installedControl) {
    Assert-PlainPath -Path $installedControl -Kind File
    Set-ExactAdminAcl -Path $installedControl -Kind File
}
$controlExisted = Test-Path -LiteralPath $installedControl
if (Test-Path -LiteralPath $installedContract) {
    Assert-PlainPath -Path $installedContract -Kind File
    Set-ExactAdminAcl -Path $installedContract -Kind File
}
$contractExisted = Test-Path -LiteralPath $installedContract

$authorizedKeys = Join-Path $sshRoot "administrators_authorized_keys"
$authorizedKeysExisted = Test-Path -LiteralPath $authorizedKeys
if ($authorizedKeysExisted) {
    Assert-PlainPath -Path $authorizedKeys -Kind File
    Set-ExactAdminAcl -Path $authorizedKeys -Kind File
}
$existing = if ($authorizedKeysExisted) {
    @(Get-Content -LiteralPath $authorizedKeys -ErrorAction Stop)
} else {
    @()
}
$reservedMarker = "(?:^|\s)(?:content-tunnel|content-worker-control)\s*$"
$filtered = @($existing | Where-Object {
    $_ -notmatch $reservedMarker -and
    $_ -notmatch "(^|\s)$([regex]::Escape($tunnel.blob))(\s|$)" -and
    $_ -notmatch "(^|\s)$([regex]::Escape($control.blob))(\s|$)"
})

$controlCommand = $installedControl.Replace('\', '/')
if ($controlCommand -notmatch "^[A-Za-z]:/[A-Za-z0-9._ /-]+$") {
    throw "The installed control path cannot be represented safely as a forced command"
}
$quotedControlCommand = '\"' + $controlCommand + '\"'
$tunnelOptions = (
    "from=`"$MacIPAddress`",command=`"cmd.exe /d /c exit 0`"," +
    "restrict,port-forwarding,permitopen=`"127.0.0.1:8189`""
)
$controlOptions = (
    "from=`"$MacIPAddress`",command=`"powershell.exe -NoProfile -NonInteractive " +
    "-ExecutionPolicy Bypass -File $quotedControlCommand`",restrict"
)
$next = @(
    $filtered
    "$tunnelOptions $($tunnel.normalized) content-tunnel"
    "$controlOptions $($control.normalized) content-worker-control"
)
$authorizedText = (($next -join [Environment]::NewLine) + [Environment]::NewLine)

$configText = [IO.File]::ReadAllText($sshdConfig)
$beginMarker = "# BEGIN CONTENT WORKER FORWARDING"
$endMarker = "# END CONTENT WORKER FORWARDING"
$managedPattern = (
    "(?ms)^" + [regex]::Escape($beginMarker) + "\r?\n.*?^" +
    [regex]::Escape($endMarker) + "\r?\n?"
)
$managedMatches = [regex]::Matches($configText, $managedPattern)
if ($managedMatches.Count -gt 1) { throw "sshd_config contains duplicate Content boundaries" }
if (
    ($configText.Contains($beginMarker) -or $configText.Contains($endMarker)) -and
    $managedMatches.Count -ne 1
) {
    throw "sshd_config contains a malformed Content boundary"
}
$baseConfig = [regex]::Replace($configText, $managedPattern, "")
$managedBlock = @(
    $beginMarker
    "Match User $sshUser Address $MacIPAddress"
    "    AllowTcpForwarding local"
    "    AllowStreamLocalForwarding no"
    "    PermitOpen 127.0.0.1:8189"
    "    GatewayPorts no"
    $endMarker
) -join [Environment]::NewLine
$firstMatch = [regex]::Match($baseConfig, "(?im)^[ \t]*Match\s+")
if ($firstMatch.Success) {
    # Match-only directives must follow every global-only directive. Insert
    # immediately before the first existing Match so this boundary is also
    # the first user-specific forwarding policy evaluated.
    $nextConfig = (
        $baseConfig.Substring(0, $firstMatch.Index).TrimEnd([char[]]"`r`n") +
        [Environment]::NewLine +
        $managedBlock +
        [Environment]::NewLine +
        $baseConfig.Substring($firstMatch.Index)
    )
} else {
    $nextConfig = (
        $baseConfig.TrimEnd([char[]]"`r`n") +
        [Environment]::NewLine +
        $managedBlock +
        [Environment]::NewLine
    )
}

$transactionId = [Guid]::NewGuid().ToString("N")
$controlTemp = Join-Path $ControlRoot ".Control-Worker.$transactionId.tmp"
$controlBackup = Join-Path $ControlRoot ".Control-Worker.$transactionId.bak"
$contractTemp = Join-Path $ControlRoot ".worker-control-contract.$transactionId.tmp"
$contractBackup = Join-Path $ControlRoot ".worker-control-contract.$transactionId.bak"
$keysTemp = Join-Path $sshRoot ".administrators_authorized_keys.$transactionId.tmp"
$keysBackup = Join-Path $sshRoot ".administrators_authorized_keys.$transactionId.bak"
$configTemp = Join-Path $sshRoot ".sshd_config.$transactionId.tmp"
$configBackup = Join-Path $sshRoot ".sshd_config.$transactionId.bak"
$controlReplaced = $false
$contractReplaced = $false
$keysReplaced = $false
$configReplaced = $false
$sshdTransactionStarted = $false
$preserveRecoveryArtifacts = $false
try {
    Copy-Item -LiteralPath $sourceControl -Destination $controlTemp
    Assert-PlainPath -Path $controlTemp -Kind File
    Set-ExactAdminAcl -Path $controlTemp -Kind File
    if ((Get-FileHash -LiteralPath $sourceControl -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $controlTemp -Algorithm SHA256).Hash) {
        throw "Staged worker control differs from its source"
    }
    Write-ProtectedTextFile -Path $contractTemp -Value $contractText
    $stagedContract = Get-Content -LiteralPath $contractTemp -Raw | ConvertFrom-Json
    if (
        [int]$stagedContract.schema_version -ne 1 -or
        [string]$stagedContract.task_name -ne $TaskName -or
        [string]$stagedContract.start_script_sha256 -ne $contractPayload.start_script_sha256
    ) { throw "Staged worker-control contract differs from its source" }
    Write-ProtectedTextFile -Path $keysTemp -Value $authorizedText
    Write-ProtectedTextFile -Path $configTemp -Value $nextConfig
    & $sshd -t -f $configTemp
    if ($LASTEXITCODE -ne 0) { throw "Managed sshd configuration failed its syntax check" }
    Assert-EffectiveForwardingBoundary `
        -Sshd $sshd `
        -Config $configTemp `
        -SshUser $sshUser `
        -MacAddress $MacIPAddress `
        -LocalAddress $localAddress `
        -AuthorizedKeys $authorizedKeys

    # Keep sshd stopped across the entire policy/control/key replacement. The
    # restrictive server policy is committed first and new authorities last,
    # so even a reboot between atomic operations cannot expose a new key under
    # the prior, broader server policy.
    $sshdTransactionStarted = $true
    Stop-SshdCleanly

    [IO.File]::Replace($configTemp, $sshdConfig, $configBackup, $true)
    $configReplaced = $true
    Set-ExactAdminAcl -Path $sshdConfig -Kind File
    & $sshd -t -f $sshdConfig
    if ($LASTEXITCODE -ne 0) { throw "Installed sshd configuration failed its syntax check" }

    if (Test-Path -LiteralPath $installedControl) {
        [IO.File]::Replace($controlTemp, $installedControl, $controlBackup, $true)
    } else {
        [IO.File]::Move($controlTemp, $installedControl)
    }
    $controlReplaced = $true
    Set-ExactAdminAcl -Path $installedControl -Kind File

    # Install the fail-closed controller before its contract. If a reboot lands
    # between these atomic replacements, the new controller refuses to launch.
    if (Test-Path -LiteralPath $installedContract) {
        [IO.File]::Replace($contractTemp, $installedContract, $contractBackup, $true)
    } else {
        [IO.File]::Move($contractTemp, $installedContract)
    }
    $contractReplaced = $true
    Set-ExactAdminAcl -Path $installedContract -Kind File

    if ($authorizedKeysExisted) {
        [IO.File]::Replace($keysTemp, $authorizedKeys, $keysBackup, $true)
    } else {
        [IO.File]::Move($keysTemp, $authorizedKeys)
    }
    $keysReplaced = $true
    Set-ExactAdminAcl -Path $authorizedKeys -Kind File

    Start-SshdCleanly
    Assert-SshdServiceContract -Sshd $sshd
    Assert-EffectiveForwardingBoundary `
        -Sshd $sshd `
        -Config $sshdConfig `
        -SshUser $sshUser `
        -MacAddress $MacIPAddress `
        -LocalAddress $localAddress `
        -AuthorizedKeys $authorizedKeys

    if ((Get-FileHash -LiteralPath $sourceControl -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $installedControl -Algorithm SHA256).Hash) {
        throw "Installed worker control differs from its source"
    }
    if ([IO.File]::ReadAllText($installedContract) -cne $contractText) {
        throw "Installed worker-control contract differs from its source"
    }
    Assert-ExactAdminAcl -Path $ControlRoot -Kind Directory
    Assert-ExactAdminAcl -Path $sshRoot -Kind Directory
    Assert-ExactAdminAcl -Path $installedControl -Kind File
    Assert-ExactAdminAcl -Path $installedContract -Kind File
    Assert-ExactAdminAcl -Path $authorizedKeys -Kind File
    Assert-ExactAdminAcl -Path $sshdConfig -Kind File
    $sshdTransactionStarted = $false
} catch {
    $failure = $_
    $rollbackFailures = New-Object Collections.Generic.List[string]
    if ($sshdTransactionStarted) {
        try {
            Stop-SshdCleanly
        } catch {
            $rollbackFailures.Add("stop sshd: $($_.Exception.Message)")
        }
    }
    $authorityRollbackSucceeded = $true
    # Undo authorities before policy. This is the inverse of the install order
    # and keeps a reboot during rollback from exposing a new authority under
    # the restored broader policy.
    if ($keysReplaced) {
        try {
            if ($authorizedKeysExisted) {
                if (-not (Test-Path -LiteralPath $keysBackup)) {
                    throw "authorized-keys backup is missing"
                }
                [IO.File]::Replace($keysBackup, $authorizedKeys, $null, $true)
                Set-ExactAdminAcl -Path $authorizedKeys -Kind File
            } elseif (Test-Path -LiteralPath $authorizedKeys) {
                Remove-Item -LiteralPath $authorizedKeys -Force
            }
        } catch {
            $authorityRollbackSucceeded = $false
            $rollbackFailures.Add("restore administrator keys: $($_.Exception.Message)")
        }
    }
    if ($controlReplaced) {
        try {
            if ($controlExisted) {
                if (-not (Test-Path -LiteralPath $controlBackup)) {
                    throw "worker-control backup is missing"
                }
                [IO.File]::Replace($controlBackup, $installedControl, $null, $true)
                Set-ExactAdminAcl -Path $installedControl -Kind File
            } elseif (Test-Path -LiteralPath $installedControl) {
                Remove-Item -LiteralPath $installedControl -Force
            }
        } catch {
            $rollbackFailures.Add("restore worker control: $($_.Exception.Message)")
        }
    }
    if ($contractReplaced) {
        try {
            if ($contractExisted) {
                if (-not (Test-Path -LiteralPath $contractBackup)) {
                    throw "worker-contract backup is missing"
                }
                [IO.File]::Replace($contractBackup, $installedContract, $null, $true)
                Set-ExactAdminAcl -Path $installedContract -Kind File
            } elseif (Test-Path -LiteralPath $installedContract) {
                Remove-Item -LiteralPath $installedContract -Force
            }
        } catch {
            $rollbackFailures.Add("restore worker contract: $($_.Exception.Message)")
        }
    }
    if ($configReplaced -and $authorityRollbackSucceeded) {
        try {
            if (-not (Test-Path -LiteralPath $configBackup)) {
                throw "configuration backup is missing"
            }
            [IO.File]::Replace($configBackup, $sshdConfig, $null, $true)
            Set-ExactAdminAcl -Path $sshdConfig -Kind File
        } catch {
            $rollbackFailures.Add("restore sshd_config: $($_.Exception.Message)")
        }
    }
    if ($sshdTransactionStarted -and $rollbackFailures.Count -eq 0) {
        try {
            & $sshd -t -f $sshdConfig
            if ($LASTEXITCODE -ne 0) { throw "restored sshd configuration is invalid" }
            Start-SshdCleanly
            $sshdTransactionStarted = $false
        } catch {
            $rollbackFailures.Add("restart restored sshd: $($_.Exception.Message)")
        }
    }
    if ($rollbackFailures.Count -gt 0) {
        $preserveRecoveryArtifacts = $true
        $recoveryPaths = @(
            $controlTemp, $controlBackup,
            $contractTemp, $contractBackup,
            $keysTemp, $keysBackup,
            $configTemp, $configBackup
        ) | Where-Object { Test-Path -LiteralPath $_ }
        $recoveryLabel = if ($recoveryPaths.Count) {
            $recoveryPaths -join ", "
        } else {
            "no recovery artifact remains; use the original package and local console"
        }
        throw (
            "Worker-control installation failed and rollback was incomplete. " +
            "Original failure: $failure. Rollback failures: " +
            (($rollbackFailures | ForEach-Object { [string]$_ }) -join "; ") +
            ". Preserved recovery paths: $recoveryLabel"
        )
    }
    throw $failure
} finally {
    if (-not $preserveRecoveryArtifacts) {
        foreach ($path in @(
            $controlTemp, $controlBackup,
            $contractTemp, $contractBackup,
            $keysTemp, $keysBackup,
            $configTemp, $configBackup
        )) {
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

Write-Host "Installed separate restricted tunnel and worker-control SSH authorities."
Write-Host "Statically validated local-only TCP forwarding for $sshUser from $MacIPAddress and restarted sshd cleanly."
Write-Host "External Mac control-key and local-tunnel checks are required before deployment acceptance."
