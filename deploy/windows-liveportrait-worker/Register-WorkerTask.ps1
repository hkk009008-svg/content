[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker"),
    [string]$Flux2StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"),
    [Parameter(Mandatory = $true)][string]$MacIPAddress,
    [string]$TaskName = "Content LivePortrait Worker"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PortFilterCoversSsh {
    param([Parameter(Mandatory = $true)]$Filter)
    foreach ($candidate in @($Filter)) {
        $protocol = [string]$candidate.Protocol
        if ($protocol -notin @("TCP", "6", "Any", "256")) { continue }
        foreach ($rawPort in @($candidate.LocalPort)) {
            foreach ($port in ([string]$rawPort -split ",")) {
                $value = $port.Trim()
                if ($value -eq "Any" -or $value -eq "22") { return $true }
                if ($value -match "^(\d+)-(\d+)$") {
                    $lower = [int]$Matches[1]
                    $upper = [int]$Matches[2]
                    if ($lower -le 22 -and $upper -ge 22) { return $true }
                }
            }
        }
    }
    return $false
}

function Test-Rfc1918IPv4 {
    param([Parameter(Mandatory = $true)][Net.IPAddress]$Address)
    if (
        $Address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        [Net.IPAddress]::IsLoopback($Address) -or
        $Address.Equals([Net.IPAddress]::Any) -or
        $Address.Equals([Net.IPAddress]::Broadcast) -or
        $Address.Equals([Net.IPAddress]::None)
    ) {
        return $false
    }
    $octets = $Address.GetAddressBytes()
    return (
        $octets[0] -eq 10 -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168)
    )
}

function Test-RuleCouldApplyToSshd {
    param([Parameter(Mandatory = $true)]$Rule)
    $applications = @($Rule | Get-NetFirewallApplicationFilter)
    $services = @($Rule | Get-NetFirewallServiceFilter)
    if ($applications.Count -ne 1 -or $services.Count -ne 1) { return $false }
    $program = [Environment]::ExpandEnvironmentVariables(
        ([string]$applications[0].Program).Trim('"')
    )
    $package = [string]$applications[0].Package
    $service = [string]$services[0].Service
    $owner = [string]$Rule.Owner
    $programMatches = (
        $program -eq "Any" -or
        $program.EndsWith("\OpenSSH\sshd.exe", [StringComparison]::OrdinalIgnoreCase)
    )
    $packageMatches = [string]::IsNullOrWhiteSpace($package) -or $package -eq "Any"
    $serviceMatches = $service -in @("Any", "sshd")
    # Packaged-app ServerCapability rules can present as Program/Service/Port
    # Any, but a non-empty owner SID scopes them to that app identity; they do
    # not authorize the separately-owned sshd.exe process.
    $ownerMatches = [string]::IsNullOrWhiteSpace($owner)
    return $programMatches -and $packageMatches -and $serviceMatches -and $ownerMatches
}

function Test-RuleExactlyAllowsMacSsh {
    param(
        [Parameter(Mandatory = $true)]$Rule,
        [Parameter(Mandatory = $true)][string]$MacIPAddress
    )
    $ports = @($Rule | Get-NetFirewallPortFilter)
    $addresses = @($Rule | Get-NetFirewallAddressFilter)
    if ($ports.Count -ne 1 -or $addresses.Count -ne 1) { return $false }
    $protocol = [string]$ports[0].Protocol
    $localPorts = @($ports[0].LocalPort | ForEach-Object { [string]$_ })
    $remoteAddresses = @($addresses[0].RemoteAddress | ForEach-Object { [string]$_ })
    return (
        $protocol -in @("TCP", "6") -and
        $localPorts.Count -eq 1 -and
        $localPorts[0] -eq "22" -and
        $remoteAddresses.Count -eq 1 -and
        $remoteAddresses[0] -eq $MacIPAddress
    )
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this registration script from an elevated PowerShell window"
}
$parsedAddress = $null
if (-not [Net.IPAddress]::TryParse($MacIPAddress, [ref]$parsedAddress) -or
    -not (Test-Rfc1918IPv4 -Address $parsedAddress)) {
    throw "MacIPAddress must be one concrete RFC1918 IPv4 address"
}

$packageRoot = Join-Path $InstallRoot "package"
$secretPath = Join-Path $InstallRoot "state\gateway-token.dpapi"
if (-not (Test-Path $secretPath)) { throw "Run Set-WorkerSecret.ps1 as this Windows user first" }

$ssh = Get-Service -Name sshd -ErrorAction Stop
if ($ssh.Status -ne "Running") { throw "OpenSSH sshd must already be running" }

$firewallName = "Content LivePortrait SSH from Mac"
$activeSshRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Enabled True -Action Allow | Where-Object {
    $filter = $_ | Get-NetFirewallPortFilter
    (Test-PortFilterCoversSsh -Filter $filter) -and (Test-RuleCouldApplyToSshd -Rule $_)
})
$ownedRules = @($activeSshRules | Where-Object { $_.DisplayName -eq $firewallName })
$exactRules = @($activeSshRules | Where-Object {
    Test-RuleExactlyAllowsMacSsh -Rule $_ -MacIPAddress $MacIPAddress
})
$conflictingRules = @($activeSshRules | Where-Object {
    -not (Test-RuleExactlyAllowsMacSsh -Rule $_ -MacIPAddress $MacIPAddress)
})
if ($conflictingRules.Count -gt 0) {
    $conflictingNames = ($conflictingRules | ForEach-Object { "'$($_.DisplayName)'" }) -join ", "
    throw (
        "Conflicting enabled inbound TCP/22 allow rule(s): $conflictingNames. " +
        "Review them with Get-NetFirewallRule and explicitly disable or scope them before rerunning. " +
        "This script will not mutate non-package firewall rules."
    )
}
if ($ownedRules.Count -gt 1 -or $exactRules.Count -gt 1) {
    throw "Multiple exact SSH firewall rules exist; review and remove the duplicates explicitly"
}

# Registration is intentionally gated by the real GPU, node-schema, model and
# one-frame expression execution proof. A failed probe leaves all state unchanged.
$lastPreflight = Join-Path $InstallRoot "state\last-preflight.json"
Remove-Item -LiteralPath $lastPreflight -Force -ErrorAction SilentlyContinue
& (Join-Path $packageRoot "Start-Worker.ps1") `
    -InstallRoot $InstallRoot `
    -Flux2StateRoot $Flux2StateRoot `
    -PreflightOnly
if (-not (Test-Path -LiteralPath $lastPreflight)) {
    throw "Preflight failed; scheduled task and firewall were not changed"
}
$preflight = Get-Content -LiteralPath $lastPreflight -Raw | ConvertFrom-Json
if (
    $preflight.status -ne "ready" -or
    $preflight.role -ne "performance-liveportrait" -or
    $preflight.execution_canary.state -ne "passed"
) {
    throw "Preflight evidence is incomplete; scheduled task and firewall were not changed"
}

$firewallCreated = $false
try {
    if ($exactRules.Count -eq 0) {
        New-NetFirewallRule `
            -DisplayName $firewallName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort 22 `
            -RemoteAddress $MacIPAddress `
            -Profile Any | Out-Null
        $firewallCreated = $true
    }
    $verifiedRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Enabled True -Action Allow | Where-Object {
        $filter = $_ | Get-NetFirewallPortFilter
        (Test-PortFilterCoversSsh -Filter $filter) -and (Test-RuleCouldApplyToSshd -Rule $_)
    })
    if ($verifiedRules.Count -ne 1) { throw "An exact SSH firewall rule is not unique" }
    $verifiedRule = $verifiedRules[0]
    if (-not (Test-RuleExactlyAllowsMacSsh -Rule $verifiedRule -MacIPAddress $MacIPAddress)) {
        throw "SSH firewall rule failed exact verification"
    }

    $startScript = Join-Path $packageRoot "Start-Worker.ps1"
    $arguments = (
        "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" " +
        "-InstallRoot `"$InstallRoot`" -Flux2StateRoot `"$Flux2StateRoot`""
    )
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
    $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $taskPrincipal `
        -Settings $settings `
        -Force | Out-Null
} catch {
    if ($firewallCreated) {
        Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule
    }
    throw
}

Write-Host "Registered $TaskName for $account."
Write-Host "Verified SSH TCP/22 is restricted to $MacIPAddress; ComfyUI and its gateway remain loopback-only."
