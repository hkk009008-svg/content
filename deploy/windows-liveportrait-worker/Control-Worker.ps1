Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# This script is a forced SSH command. It deliberately accepts no PowerShell
# parameters: the only input is the exact SSH original command, and the only
# mutating operation is running one contract-bound Task Scheduler definition.
$TaskName = "Content LivePortrait Worker"
$GpuMemoryBusyThresholdMiB = 4096
$GpuUtilizationBusyThreshold = 50
$GpuSampleCount = 3
$GpuSampleIntervalMilliseconds = 250
$AdministratorsSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
$SystemSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
$AclSections = (
    [Security.AccessControl.AccessControlSections]::Access -bor
    [Security.AccessControl.AccessControlSections]::Owner
)
$CommonApplicationData = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::CommonApplicationData
).TrimEnd('\')
$ControlRoot = Join-Path $CommonApplicationData "ContentWorkerControl"
$ContractPath = Join-Path $ControlRoot "worker-control-contract.json"

function Write-ControlPayload {
    param([Parameter(Mandatory = $true)]$Payload)
    $Payload | ConvertTo-Json -Compress -Depth 4
}

function Assert-ProtectedPath {
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
    $security = if ($Kind -eq "Directory") {
        [IO.Directory]::GetAccessControl($Path, $AclSections)
    } else {
        [IO.File]::GetAccessControl($Path, $AclSections)
    }
    $owner = $security.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -ne $AdministratorsSid.Value -or -not $security.AreAccessRulesProtected) {
        throw "$Path owner or inheritance protection is not exact"
    }
    $rules = @($security.GetAccessRules(
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

function Resolve-PrincipalSid {
    param([Parameter(Mandatory = $true)][string]$UserId)
    if ($UserId -match "^S-\d-(?:\d+-)+\d+$") {
        return ([Security.Principal.SecurityIdentifier]::new($UserId)).Value
    }
    return ([Security.Principal.NTAccount]::new($UserId)).Translate(
        [Security.Principal.SecurityIdentifier]
    ).Value
}

function Test-PathEquals {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )
    return [string]::Equals(
        [IO.Path]::GetFullPath($Left).TrimEnd('\'),
        [IO.Path]::GetFullPath($Right).TrimEnd('\'),
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Get-WorkerContract {
    Assert-ProtectedPath -Path $ControlRoot -Kind Directory
    Assert-ProtectedPath -Path $ContractPath -Kind File
    $contract = [IO.File]::ReadAllText($ContractPath) | ConvertFrom-Json
    $expectedProperties = @(
        "arguments", "executable", "execution_time_limit", "flux2_state_root",
        "install_root", "logon_type", "multiple_instances", "principal_sid",
        "run_level", "schema_version", "start_script", "start_script_sha256",
        "task_name", "task_path", "working_directory"
    ) | Sort-Object
    $actualProperties = @($contract.PSObject.Properties.Name | Sort-Object)
    if (($actualProperties -join "`n") -cne ($expectedProperties -join "`n")) {
        throw "Worker-control contract properties are not exact"
    }
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if (
        [int]$contract.schema_version -ne 1 -or
        [string]$contract.task_name -cne $TaskName -or
        [string]$contract.task_path -cne "\" -or
        [string]$contract.principal_sid -cne $currentSid -or
        [int]$contract.logon_type -ne 3 -or
        [int]$contract.run_level -ne 0 -or
        [int]$contract.multiple_instances -ne 2 -or
        [string]$contract.execution_time_limit -cne "PT0S"
    ) { throw "Worker-control contract identity or settings are invalid" }

    $installRoot = [IO.Path]::GetFullPath([string]$contract.install_root).TrimEnd('\')
    $flux2StateRoot = [IO.Path]::GetFullPath([string]$contract.flux2_state_root).TrimEnd('\')
    $workingDirectory = Join-Path $installRoot "package"
    $startScript = Join-Path $workingDirectory "Start-Worker.ps1"
    $executable = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $arguments = (
        "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" " +
        "-InstallRoot `"$installRoot`" -Flux2StateRoot `"$flux2StateRoot`""
    )
    if (
        -not (Test-PathEquals -Left ([string]$contract.working_directory) -Right $workingDirectory) -or
        -not (Test-PathEquals -Left ([string]$contract.start_script) -Right $startScript) -or
        -not (Test-PathEquals -Left ([string]$contract.executable) -Right $executable) -or
        [string]$contract.arguments -cne $arguments -or
        [string]$contract.start_script_sha256 -notmatch "^[0-9a-f]{64}$"
    ) { throw "Worker-control contract paths or arguments are invalid" }
    $scriptItem = Get-Item -LiteralPath $startScript -Force -ErrorAction Stop
    if ($scriptItem.PSIsContainer -or ($scriptItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Worker start script must be a regular non-link file"
    }
    $scriptHash = (Get-FileHash -LiteralPath $startScript -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($scriptHash -cne [string]$contract.start_script_sha256) {
        throw "Worker start script differs from the protected control contract"
    }
    return $contract
}

function Get-VerifiedWorkerTask {
    $contract = Get-WorkerContract
    $service = New-Object -ComObject "Schedule.Service"
    $service.Connect()
    $registered = $service.GetFolder("\").GetTask($TaskName)
    $definition = $registered.Definition
    if (
        -not [bool]$registered.Enabled -or
        [int]$definition.Triggers.Count -ne 0 -or
        [int]$definition.Actions.Count -ne 1 -or
        [int]$definition.Settings.RestartCount -ne 0 -or
        [int]$definition.Settings.MultipleInstances -ne [int]$contract.multiple_instances -or
        [string]$definition.Settings.ExecutionTimeLimit -cne [string]$contract.execution_time_limit -or
        -not [bool]$definition.Settings.AllowDemandStart -or
        [bool]$definition.Settings.StartWhenAvailable -or
        [bool]$definition.Settings.WakeToRun
    ) { throw "Worker task scheduling settings differ from the protected contract" }
    if (
        (Resolve-PrincipalSid -UserId ([string]$definition.Principal.UserId)) -cne
            [string]$contract.principal_sid -or
        [int]$definition.Principal.LogonType -ne [int]$contract.logon_type -or
        [int]$definition.Principal.RunLevel -ne [int]$contract.run_level
    ) { throw "Worker task principal differs from the protected contract" }
    $action = $definition.Actions.Item(1)
    if (
        [int]$action.Type -ne 0 -or
        -not (Test-PathEquals -Left ([string]$action.Path) -Right ([string]$contract.executable)) -or
        [string]$action.Arguments -cne [string]$contract.arguments -or
        -not (Test-PathEquals `
            -Left ([string]$action.WorkingDirectory) `
            -Right ([string]$contract.working_directory)
        )
    ) { throw "Worker task action differs from the protected contract" }

    $xml = New-Object Xml.XmlDocument
    $xml.LoadXml([string]$registered.Xml)
    if ($xml.DocumentElement.NamespaceURI -ne "http://schemas.microsoft.com/windows/2004/02/mit/task") {
        throw "Worker task XML namespace is invalid"
    }
    $namespace = New-Object Xml.XmlNamespaceManager($xml.NameTable)
    $namespace.AddNamespace("t", $xml.DocumentElement.NamespaceURI)
    $triggers = @($xml.SelectNodes("/t:Task/t:Triggers/*", $namespace))
    $restart = @($xml.SelectNodes("/t:Task/t:Settings/t:RestartOnFailure", $namespace))
    $execNodes = @($xml.SelectNodes("/t:Task/t:Actions/t:Exec", $namespace))
    if ($triggers.Count -ne 0 -or $restart.Count -ne 0 -or $execNodes.Count -ne 1) {
        throw "Worker task XML contains a trigger, restart policy, or unexpected action"
    }
    $exec = $execNodes[0]
    if (
        -not (Test-PathEquals -Left ([string]$exec.Command) -Right ([string]$contract.executable)) -or
        [string]$exec.Arguments -cne [string]$contract.arguments -or
        -not (Test-PathEquals `
            -Left ([string]$exec.WorkingDirectory) `
            -Right ([string]$contract.working_directory)
        ) -or
        (Resolve-PrincipalSid -UserId ([string]$xml.Task.Principals.Principal.UserId)) -cne
            [string]$contract.principal_sid -or
        [string]$xml.Task.Principals.Principal.LogonType -cne "InteractiveToken" -or
        [string]$xml.Task.Principals.Principal.RunLevel -cne "LeastPrivilege" -or
        [string]$xml.Task.Settings.MultipleInstancesPolicy -cne "IgnoreNew" -or
        [string]$xml.Task.Settings.ExecutionTimeLimit -cne "PT0S" -or
        [string]$xml.Task.Settings.Enabled -cne "true" -or
        [string]$xml.Task.Settings.StartWhenAvailable -cne "false" -or
        [string]$xml.Task.Settings.WakeToRun -cne "false"
    ) { throw "Worker task XML differs from the protected contract" }
    return [pscustomobject]@{
        task_service = $service
        registered_task = $registered
        state = [int]$registered.State
        last_task_result = [long]$registered.LastTaskResult
    }
}

function Get-GpuSnapshot {
    $memorySamples = @()
    $utilizationSamples = @()
    try {
        for ($sample = 0; $sample -lt $GpuSampleCount; $sample++) {
            $raw = @(& nvidia-smi `
                --query-gpu=memory.used,utilization.gpu `
                --format=csv,noheader,nounits 2>$null)
            if ($raw.Count -ne 1) { throw "unexpected GPU inventory" }
            $parts = @([string]$raw[0] -split "," | ForEach-Object { $_.Trim() })
            if ($parts.Count -ne 2) { throw "unexpected GPU fields" }
            $memorySamples += [int]::Parse(
                $parts[0],
                [Globalization.CultureInfo]::InvariantCulture
            )
            $utilizationSamples += [int]::Parse(
                $parts[1],
                [Globalization.CultureInfo]::InvariantCulture
            )
            if ($sample + 1 -lt $GpuSampleCount) {
                Start-Sleep -Milliseconds $GpuSampleIntervalMilliseconds
            }
        }
    } catch {
        return [pscustomobject]@{
            available = $false
            used_mib = $null
            utilization_percent = $null
            busy = $true
        }
    }
    $used = [int](($memorySamples | Measure-Object -Maximum).Maximum)
    $utilization = [int][Math]::Round(
        ($utilizationSamples | Measure-Object -Average).Average
    )
    $sustainedUtilization = @($utilizationSamples | Where-Object {
        $_ -ge $GpuUtilizationBusyThreshold
    }).Count -eq $GpuSampleCount
    $unrealActive = @(Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue).Count -gt 0
    return [pscustomobject]@{
        available = $true
        used_mib = $used
        utilization_percent = $utilization
        busy = (
            $unrealActive -or
            $used -ge $GpuMemoryBusyThresholdMiB -or
            $sustainedUtilization
        )
    }
}

function Get-ControlStatus {
    $verified = Get-VerifiedWorkerTask
    $gpu = Get-GpuSnapshot
    $state = "unknown"
    $canStart = $false
    $message = "The Windows worker task is in an unknown state."
    if ($verified.state -eq 4) {
        $state = "running"
        $message = "The Windows worker task is running; readiness is checked separately."
    } elseif ($verified.state -eq 3) {
        $state = "stopped"
        $canStart = -not $gpu.busy
        if (-not $gpu.available) {
            $message = "GPU status is unavailable, so remote launch is blocked."
        } elseif ($gpu.busy) {
            $message = "The Windows GPU is busy. Stop GPU work in Unreal or another app, then refresh."
        } else {
            $message = "The Windows worker is stopped and the GPU is available to launch."
        }
    } elseif ($verified.state -eq 1) {
        $state = "unavailable"
        $message = "The Windows worker task is disabled."
    }
    return [ordered]@{
        schema_version = 1
        state = $state
        can_start = $canStart
        gpu_busy = [bool]$gpu.busy
        gpu_used_mib = $gpu.used_mib
        gpu_utilization_percent = $gpu.utilization_percent
        last_task_result = $verified.last_task_result
        message = $message
    }
}

try {
    $requested = ([string]$env:SSH_ORIGINAL_COMMAND).Trim()
    if ($requested -eq "status") {
        Write-ControlPayload (Get-ControlStatus)
        exit 0
    }
    if ($requested -ne "start") {
        Write-ControlPayload ([ordered]@{
            schema_version = 1
            state = "unavailable"
            can_start = $false
            gpu_busy = $true
            gpu_used_mib = $null
            gpu_utilization_percent = $null
            last_task_result = $null
            message = "The requested worker control action is not allowed."
        })
        exit 64
    }

    $before = Get-ControlStatus
    if ($before.state -eq "running") {
        Write-ControlPayload $before
        exit 0
    }
    if ($before.state -ne "stopped" -or -not $before.can_start) {
        Write-ControlPayload $before
        exit 0
    }

    # Re-resolve and revalidate the protected definition immediately before
    # invoking that exact COM object, rather than starting an unchecked name.
    $launch = Get-VerifiedWorkerTask
    if ($launch.state -ne 3) { throw "Worker task state changed before launch" }
    [void]$launch.registered_task.Run($null)
    $after = $null
    # Task Scheduler may briefly continue to report Ready after accepting the
    # start request. Give it a bounded window to become Running, while also
    # detecting a worker that starts and exits immediately.
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        Start-Sleep -Milliseconds 500
        $after = Get-ControlStatus
        if ($after.state -ne "stopped") { break }
    }
    if ($after.state -eq "running") {
        $after.state = "starting"
        $after.can_start = $false
        $after.message = "Windows worker launch requested; readiness is checked separately."
    } elseif ($after.state -eq "stopped") {
        $after.state = "failed"
        $after.can_start = $false
        $after.message = "The Windows worker task exited during startup; inspect its worker logs."
    }
    Write-ControlPayload $after
    exit 0
} catch {
    Write-ControlPayload ([ordered]@{
        schema_version = 1
        state = "failed"
        can_start = $false
        gpu_busy = $true
        gpu_used_mib = $null
        gpu_utilization_percent = $null
        last_task_result = $null
        message = "Windows worker control failed closed."
    })
    exit 70
}
