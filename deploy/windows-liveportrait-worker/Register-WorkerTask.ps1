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

function Assert-EffectiveFirewallProfiles {
    $service = Get-Service -Name MpsSvc -ErrorAction Stop
    if ($service.Status -ne "Running") {
        throw "Windows Defender Firewall service must be running"
    }
    $profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
    if ($profiles.Count -eq 0) {
        throw "No effective Windows Defender Firewall profiles were returned"
    }
    $unsafe = @($profiles | Where-Object {
        [string]$_.Enabled -ne "True" -or
        [string]$_.DefaultInboundAction -ne "Block"
    })
    if ($unsafe.Count -gt 0) {
        $details = ($unsafe | ForEach-Object {
            "$($_.Name): enabled=$($_.Enabled), inbound=$($_.DefaultInboundAction)"
        }) -join "; "
        throw "Every effective firewall profile must be enabled with default inbound Block: $details"
    }
}

function Resolve-PrincipalSid {
    param([Parameter(Mandatory = $true)][string]$UserId)
    try {
        if ($UserId -match "^S-\d-(?:\d+-)+\d+$") {
            return ([Security.Principal.SecurityIdentifier]::new($UserId)).Value
        }
        return ([Security.Principal.NTAccount]::new($UserId)).Translate(
            [Security.Principal.SecurityIdentifier]
        ).Value
    } catch {
        throw "Could not resolve scheduled-task principal: $UserId"
    }
}

function Get-TaskXmlDocument {
    param([Parameter(Mandatory = $true)][string]$XmlText)
    $document = New-Object Xml.XmlDocument
    $document.PreserveWhitespace = $true
    $document.LoadXml($XmlText)
    if ($document.DocumentElement.NamespaceURI -ne "http://schemas.microsoft.com/windows/2004/02/mit/task") {
        throw "Scheduled-task XML uses an unexpected namespace"
    }
    return ,$document
}

function Get-TaskXmlNamespaceManager {
    param([Parameter(Mandatory = $true)][Xml.XmlDocument]$Document)
    $manager = New-Object Xml.XmlNamespaceManager($Document.NameTable)
    $manager.AddNamespace("t", $Document.DocumentElement.NamespaceURI)
    return ,$manager
}

function Assert-InstalledManualTask {
    param(
        [Parameter(Mandatory = $true)]$TaskFolder,
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$ExpectedSid,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][string]$ExpectedArguments,
        [Parameter(Mandatory = $true)][string]$ExpectedWorkingDirectory
    )
    $registered = $TaskFolder.GetTask($TaskName)
    $definition = $registered.Definition
    if (-not [bool]$registered.Enabled) { throw "Registered task is disabled" }
    if ([int]$definition.Triggers.Count -ne 0) { throw "Registered task contains an automatic trigger" }
    if ([int]$definition.Actions.Count -ne 1) { throw "Registered task must contain exactly one action" }
    $installedAction = $definition.Actions.Item(1)
    if ([int]$installedAction.Type -ne 0) { throw "Registered task action is not an executable" }
    if (-not [string]::Equals(
        [string]$installedAction.Path,
        $ExpectedExecutable,
        [StringComparison]::OrdinalIgnoreCase
    )) { throw "Registered task executable differs from the manual-worker contract" }
    if ([string]$installedAction.Arguments -cne $ExpectedArguments) {
        throw "Registered task arguments differ from the manual-worker contract"
    }
    if (-not [string]::Equals(
        [string]$installedAction.WorkingDirectory,
        $ExpectedWorkingDirectory,
        [StringComparison]::OrdinalIgnoreCase
    )) { throw "Registered task working directory differs from the manual-worker contract" }
    if ((Resolve-PrincipalSid -UserId ([string]$definition.Principal.UserId)) -ne $ExpectedSid) {
        throw "Registered task principal differs from the current Windows user"
    }
    if ([int]$definition.Principal.LogonType -ne 3 -or [int]$definition.Principal.RunLevel -ne 0) {
        throw "Registered task must use InteractiveToken at least privilege"
    }
    if (
        [int]$definition.Settings.MultipleInstances -ne 2 -or
        [string]$definition.Settings.ExecutionTimeLimit -ne "PT0S" -or
        [int]$definition.Settings.RestartCount -ne 0 -or
        [bool]$definition.Settings.StartWhenAvailable -or
        [bool]$definition.Settings.WakeToRun
    ) {
        throw "Registered task settings permit duplicate, bounded, or retried execution"
    }

    $installed = Get-ScheduledTask -TaskName $TaskName -TaskPath "\" -ErrorAction Stop
    if (@($installed.Triggers | Where-Object { $null -ne $_ }).Count -ne 0) {
        throw "ScheduledTasks CIM reports an automatic trigger"
    }
    $exportedText = Export-ScheduledTask -TaskName $TaskName -TaskPath "\" -ErrorAction Stop
    $exported = Get-TaskXmlDocument -XmlText $exportedText
    $namespace = Get-TaskXmlNamespaceManager -Document $exported
    if (@($exported.SelectNodes("/t:Task/t:Triggers/*", $namespace)).Count -ne 0) {
        throw "Exported task XML contains an automatic trigger"
    }
    $execNodes = @($exported.SelectNodes("/t:Task/t:Actions/t:Exec", $namespace))
    if ($execNodes.Count -ne 1) { throw "Exported task XML must contain one Exec action" }
    $exec = $execNodes[0]
    if (-not [string]::Equals(
        [string]$exec.Command,
        $ExpectedExecutable,
        [StringComparison]::OrdinalIgnoreCase
    ) -or [string]$exec.Arguments -cne $ExpectedArguments) {
        throw "Exported task XML action differs from the manual-worker contract"
    }
    if (-not [string]::Equals(
        [string]$exec.WorkingDirectory,
        $ExpectedWorkingDirectory,
        [StringComparison]::OrdinalIgnoreCase
    )) { throw "Exported task XML working directory differs from the manual-worker contract" }
    if ((Resolve-PrincipalSid -UserId ([string]$exported.Task.Principals.Principal.UserId)) -ne $ExpectedSid) {
        throw "Exported task XML principal differs from the current Windows user"
    }
    if (
        [string]$exported.Task.Principals.Principal.LogonType -ne "InteractiveToken" -or
        [string]$exported.Task.Principals.Principal.RunLevel -ne "LeastPrivilege" -or
        [string]$exported.Task.Settings.MultipleInstancesPolicy -ne "IgnoreNew" -or
        [string]$exported.Task.Settings.ExecutionTimeLimit -ne "PT0S" -or
        [string]$exported.Task.Settings.Enabled -ne "true" -or
        [string]$exported.Task.Settings.StartWhenAvailable -ne "false" -or
        [string]$exported.Task.Settings.WakeToRun -ne "false" -or
        @($exported.SelectNodes("/t:Task/t:Settings/t:RestartOnFailure", $namespace)).Count -ne 0
    ) {
        throw "Exported task XML settings differ from the manual-worker contract"
    }
}

function Restore-PreviousTaskDisabled {
    param(
        [Parameter(Mandatory = $true)]$TaskService,
        [Parameter(Mandatory = $true)]$TaskFolder,
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$PreviousXml,
        [Parameter(Mandatory = $true)][string]$ExpectedSid
    )
    $restore = $TaskService.NewTask(0)
    $restore.XmlText = $PreviousXml
    if ((Resolve-PrincipalSid -UserId ([string]$restore.Principal.UserId)) -ne $ExpectedSid) {
        throw "Refusing to restore a task owned by another principal"
    }
    if ([int]$restore.Principal.LogonType -ne 3 -or [int]$restore.Principal.RunLevel -ne 0) {
        throw "Refusing to restore a task with broader execution authority"
    }
    [void]$TaskFolder.RegisterTaskDefinition(
        $TaskName,
        $restore,
        (0x6 -bor 0x8 -bor 0x20),
        $ExpectedSid,
        $null,
        3,
        $null
    )
    $restored = $TaskFolder.GetTask($TaskName)
    if ([bool]$restored.Enabled -or [int]$restored.State -ne 1) {
        throw "Previous task was not restored in a disabled state"
    }
    if ([int]$restored.Definition.Triggers.Count -ne [int]$restore.Triggers.Count) {
        throw "Restored task trigger inventory differs from the saved definition"
    }
    if ([int]$restored.Definition.Actions.Count -ne [int]$restore.Actions.Count) {
        throw "Restored task action inventory differs from the saved definition"
    }
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this registration script from an elevated PowerShell window"
}
if (
    [string]::IsNullOrWhiteSpace($TaskName) -or
    $TaskName -ne $TaskName.Trim() -or
    $TaskName.IndexOfAny([char[]]"\/") -ge 0
) {
    throw "TaskName must be one exact task name in the Task Scheduler root"
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$Flux2StateRoot = [IO.Path]::GetFullPath($Flux2StateRoot).TrimEnd('\')
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
Assert-EffectiveFirewallProfiles

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$account = $identity.Name
$accountSid = $identity.User.Value
$startScript = Join-Path $packageRoot "Start-Worker.ps1"
$taskExecutable = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = (
    "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" " +
    "-InstallRoot `"$InstallRoot`" -Flux2StateRoot `"$Flux2StateRoot`""
)
$taskService = New-Object -ComObject "Schedule.Service"
$taskService.Connect()
$taskFolder = $taskService.GetFolder("\")
$taskDefinition = $taskService.NewTask(0)
$taskDefinition.RegistrationInfo.Author = $account
$taskDefinition.RegistrationInfo.Description = "Manual-only Content LivePortrait worker"
$taskDefinition.Principal.UserId = $accountSid
$taskDefinition.Principal.LogonType = 3
$taskDefinition.Principal.RunLevel = 0
$taskDefinition.Settings.Enabled = $true
$taskDefinition.Settings.AllowDemandStart = $true
$taskDefinition.Settings.MultipleInstances = 2
$taskDefinition.Settings.ExecutionTimeLimit = "PT0S"
$taskDefinition.Settings.StartWhenAvailable = $false
$taskDefinition.Settings.WakeToRun = $false
$taskDefinition.Triggers.Clear()
if ([int]$taskDefinition.Triggers.Count -ne 0) { throw "Candidate task contains an automatic trigger" }
$taskAction = $taskDefinition.Actions.Create(0)
$taskAction.Path = $taskExecutable
$taskAction.Arguments = $arguments
$taskAction.WorkingDirectory = $packageRoot

$previousTask = $null
$previousTaskXml = $null
$previousTaskEnabled = $false
$taskRecoveryPath = Join-Path $InstallRoot "state\task-registration-recovery.xml"
try {
    $previousTask = $taskFolder.GetTask($TaskName)
} catch {
    if ([int]$_.Exception.HResult -ne -2147024894) { throw }
}
if ($null -ne $previousTask) {
    if ([int]$previousTask.State -notin @(1, 3)) {
        throw "Existing worker task must be Ready or Disabled before registration"
    }
    if ((Resolve-PrincipalSid -UserId ([string]$previousTask.Definition.Principal.UserId)) -ne $accountSid) {
        throw "Existing worker task belongs to another principal"
    }
    if (
        [int]$previousTask.Definition.Principal.LogonType -ne 3 -or
        [int]$previousTask.Definition.Principal.RunLevel -ne 0
    ) {
        throw "Existing worker task has broader execution authority"
    }
    $previousTaskXml = [string]$previousTask.Xml
    $previousTaskEnabled = [bool]$previousTask.Enabled
    [IO.File]::WriteAllText($taskRecoveryPath, $previousTaskXml, [Text.UTF8Encoding]::new($false))
    if ([int]$previousTask.Definition.Triggers.Count -ne 0 -and $previousTaskEnabled) {
        $previousTask.Enabled = $false
        if ([bool]$taskFolder.GetTask($TaskName).Enabled) {
            throw "Could not quarantine the existing triggered worker task"
        }
        Write-Warning "Disabled the existing worker task because it contained an automatic trigger."
    }
} else {
    Remove-Item -LiteralPath $taskRecoveryPath -Force -ErrorAction SilentlyContinue
}

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

# Candidate registration is intentionally gated by the real GPU, node-schema,
# model and one-frame expression execution proof. A failed probe does not
# install the candidate or alter the firewall; a triggered legacy task
# quarantined above deliberately stays disabled.
$lastPreflight = Join-Path $InstallRoot "state\last-preflight.json"
Remove-Item -LiteralPath $lastPreflight -Force -ErrorAction SilentlyContinue
& (Join-Path $packageRoot "Start-Worker.ps1") `
    -InstallRoot $InstallRoot `
    -Flux2StateRoot $Flux2StateRoot `
    -PreflightOnly
if (-not (Test-Path -LiteralPath $lastPreflight)) {
    throw "Preflight failed; candidate task and firewall were not installed"
}
$preflight = Get-Content -LiteralPath $lastPreflight -Raw | ConvertFrom-Json
if (
    $preflight.status -ne "ready" -or
    $preflight.role -ne "performance-liveportrait" -or
    $preflight.execution_canary.state -ne "passed"
) {
    throw "Preflight evidence is incomplete; candidate task and firewall were not installed"
}

$createdFirewallRule = $null
$taskMutationAttempted = $false
try {
    if ($exactRules.Count -eq 0) {
        $createdFirewallRule = New-NetFirewallRule `
            -DisplayName $firewallName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort 22 `
            -RemoteAddress $MacIPAddress `
            -Profile Any
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
    Assert-EffectiveFirewallProfiles

    $taskMutationAttempted = $true
    [void]$taskFolder.RegisterTaskDefinition(
        $TaskName,
        $taskDefinition,
        (0x6 -bor 0x20),
        $accountSid,
        $null,
        3,
        $null
    )
    Assert-InstalledManualTask `
        -TaskFolder $taskFolder `
        -TaskName $TaskName `
        -ExpectedSid $accountSid `
        -ExpectedExecutable $taskExecutable `
        -ExpectedArguments $arguments `
        -ExpectedWorkingDirectory $packageRoot
    Remove-Item -LiteralPath $taskRecoveryPath -Force -ErrorAction SilentlyContinue
} catch {
    $registrationFailure = $_
    $rollbackFailures = New-Object Collections.Generic.List[string]
    if ($taskMutationAttempted) {
        try {
            if ($null -ne $previousTaskXml) {
                Restore-PreviousTaskDisabled `
                    -TaskService $taskService `
                    -TaskFolder $taskFolder `
                    -TaskName $TaskName `
                    -PreviousXml $previousTaskXml `
                    -ExpectedSid $accountSid
            } else {
                try {
                    $taskFolder.DeleteTask($TaskName, 0)
                } catch {
                    if ([int]$_.Exception.HResult -ne -2147024894) { throw }
                }
                try {
                    [void]$taskFolder.GetTask($TaskName)
                    throw "New task still exists after rollback"
                } catch {
                    if (
                        $_.Exception.Message -eq "New task still exists after rollback" -or
                        [int]$_.Exception.HResult -ne -2147024894
                    ) { throw }
                }
            }
        } catch {
            $rollbackFailures.Add("task: $($_.Exception.Message)")
            try {
                $failedTask = $taskFolder.GetTask($TaskName)
                $failedTask.Enabled = $false
            } catch {
                $rollbackFailures.Add("last-resort disable: $($_.Exception.Message)")
            }
        }
    }
    if ($null -ne $createdFirewallRule) {
        try {
            $createdFirewallRule | Remove-NetFirewallRule -ErrorAction Stop
        } catch {
            $rollbackFailures.Add("firewall: $($_.Exception.Message)")
        }
    }
    if ($rollbackFailures.Count -gt 0) {
        throw (
            "Worker task registration failed: $($registrationFailure.Exception.Message). " +
            "Rollback also failed: $($rollbackFailures -join '; '). " +
            "Recovery evidence remains at $taskRecoveryPath"
        )
    }
    throw $registrationFailure
}

Write-Host "Registered $TaskName for $account."
Write-Host "Verified SSH TCP/22 is restricted to $MacIPAddress; ComfyUI and its gateway remain loopback-only."
