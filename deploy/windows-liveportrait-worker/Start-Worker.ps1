[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker"),
    [string]$Flux2StateRoot = (Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"),
    [switch]$PreflightOnly,
    [switch]$Benchmark
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Windows does not automatically terminate a process's descendants when its
# parent exits. Keep both worker roots and every ffmpeg/Python child in one Job
# Object whose close semantics are enforced by the kernel. Closing the handle
# in the supervisor's finally block therefore cannot leave GPU/file-owning
# descendants behind for the scheduled-task restart.
if (-not ("ContentWorkerJob" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class ContentWorkerJob
{
    private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;

    private enum JOBOBJECTINFOCLASS
    {
        JobObjectExtendedLimitInformation = 9
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateJobObject(
        IntPtr jobAttributes,
        string name
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(
        SafeFileHandle job,
        JOBOBJECTINFOCLASS informationClass,
        IntPtr information,
        uint informationLength
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(
        SafeFileHandle job,
        IntPtr process
    );

    public static SafeFileHandle CreateKillOnCloseJob()
    {
        SafeFileHandle job = CreateJobObject(IntPtr.Zero, null);
        if (job.IsInvalid)
        {
            throw new Win32Exception(
                Marshal.GetLastWin32Error(),
                "Could not create the worker process Job Object"
            );
        }

        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits =
            new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        int length = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr buffer = Marshal.AllocHGlobal(length);
        try
        {
            Marshal.StructureToPtr(limits, buffer, false);
            if (!SetInformationJobObject(
                    job,
                    JOBOBJECTINFOCLASS.JobObjectExtendedLimitInformation,
                    buffer,
                    (uint)length))
            {
                int error = Marshal.GetLastWin32Error();
                job.Dispose();
                throw new Win32Exception(
                    error,
                    "Could not enable kill-on-close for the worker Job Object"
                );
            }
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
        return job;
    }

    public static void AssignProcess(SafeFileHandle job, IntPtr process)
    {
        if (job == null || job.IsInvalid || job.IsClosed)
        {
            throw new InvalidOperationException("The worker Job Object is unavailable");
        }
        if (!AssignProcessToJobObject(job, process))
        {
            throw new Win32Exception(
                Marshal.GetLastWin32Error(),
                "Could not bind the worker process to its kill-on-close Job Object"
            );
        }
    }
}
"@
}

function Quote-ProcessArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains('"')) { throw "Process arguments may not contain a quote" }
    $trailingBackslashes = 0
    for ($index = $Value.Length - 1; $index -ge 0 -and $Value[$index] -eq '\'; $index--) {
        $trailingBackslashes++
    }
    $body = if ($trailingBackslashes) {
        $Value.Substring(0, $Value.Length - $trailingBackslashes) + (('\' * (2 * $trailingBackslashes)) -join '')
    } else {
        $Value
    }
    return '"' + $body + '"'
}

function Quote-PowerShellLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Start-LoggedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$LogPrefix,
        [Parameter(Mandatory = $true)]$WorkerJob,
        [hashtable]$Environment = @{}
    )
    $stdoutPath = "$LogPrefix.stdout.log"
    $stderrPath = "$LogPrefix.stderr.log"
    # Start-Process creates a running process, so assigning the target directly
    # would leave a small interval in which it could create an unowned child.
    # Launch a same-user wrapper behind a named gate, assign that wrapper to the
    # Job Object, and only then release it to create the real worker process.
    $launchGateName = "Local\ContentWorkerLaunch-$([Guid]::NewGuid().ToString('N'))"
    $readyGateName = "Local\ContentWorkerReady-$([Guid]::NewGuid().ToString('N'))"
    $launchGate = [Threading.EventWaitHandle]::new(
        $false,
        [Threading.EventResetMode]::ManualReset,
        $launchGateName
    )
    $readyGate = [Threading.EventWaitHandle]::new(
        $false,
        [Threading.EventResetMode]::ManualReset,
        $readyGateName
    )
    $literalArguments = ($Arguments | ForEach-Object {
        "    " + (Quote-PowerShellLiteral $_)
    }) -join ",`r`n"
    $launchScript = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = "Stop"
`$gate = [Threading.EventWaitHandle]::OpenExisting($(Quote-PowerShellLiteral $launchGateName))
`$ready = [Threading.EventWaitHandle]::OpenExisting($(Quote-PowerShellLiteral $readyGateName))
try {
    `$ready.Set() | Out-Null
    if (-not `$gate.WaitOne(30000)) { throw "Worker launch gate timed out" }
} finally {
    `$ready.Dispose()
    `$gate.Dispose()
}
`$workerExecutable = $(Quote-PowerShellLiteral $Executable)
`$workerArguments = @(
$literalArguments
)
& `$workerExecutable @workerArguments
exit `$LASTEXITCODE
"@
    $encodedLaunchScript = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($launchScript)
    )
    $wrapperArguments = @(
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-EncodedCommand", $encodedLaunchScript
    )
    $argumentString = (($wrapperArguments | ForEach-Object {
        Quote-ProcessArgument $_
    }) -join " ")
    $previousEnvironment = @{}
    foreach ($entry in $Environment.GetEnumerator()) {
        $environmentPath = "Env:$($entry.Key)"
        $previousEnvironment[$entry.Key] = @{
            Exists = Test-Path -LiteralPath $environmentPath
            Value = if (Test-Path -LiteralPath $environmentPath) {
                (Get-Item -LiteralPath $environmentPath).Value
            } else {
                $null
            }
        }
        Set-Item -LiteralPath $environmentPath -Value $entry.Value
    }
    try {
        # Start-Process owns redirection without invoking PowerShell script blocks
        # on .NET worker threads. That keeps Windows PowerShell 5.1 stable and
        # gives every child a durable stdout/stderr record.
        $process = Start-Process `
            -FilePath (Join-Path $PSHOME "powershell.exe") `
            -ArgumentList $argumentString `
            -WorkingDirectory $WorkingDirectory `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath
        try {
            [ContentWorkerJob]::AssignProcess($WorkerJob, $process.Handle)
            if (-not $readyGate.WaitOne(10000)) {
                throw "Worker launch wrapper did not reach its guarded wait state"
            }
            $launchGate.Set() | Out-Null
        } catch {
            # A process that cannot enter the kill-on-close job is unsafe to
            # supervise: stop it immediately rather than launch an orphanable
            # worker and hope a later tree walk finds all descendants.
            if (-not $process.HasExited) {
                $process.Kill()
                $process.WaitForExit(10000) | Out-Null
            }
            throw
        }
        return $process
    } finally {
        $readyGate.Dispose()
        $launchGate.Dispose()
        foreach ($entry in $Environment.GetEnumerator()) {
            $environmentPath = "Env:$($entry.Key)"
            $previous = $previousEnvironment[$entry.Key]
            if ($previous.Exists) {
                Set-Item -LiteralPath $environmentPath -Value $previous.Value
            } else {
                Remove-Item -LiteralPath $environmentPath -ErrorAction SilentlyContinue
            }
        }
    }
}

function Stop-LoggedProcess {
    param($Process)
    if ($null -eq $Process) { return }
    if (-not $Process.HasExited) {
        $Process.Kill()
        $Process.WaitForExit(10000) | Out-Null
    }
    $Process.WaitForExit()
}

$mutex = New-Object Threading.Mutex($false, "Local\ContentLivePortraitWorker")
if (-not $mutex.WaitOne(0)) { throw "Another Content LivePortrait worker supervisor is running" }

$packageRoot = Join-Path $InstallRoot "package"
$comfyRoot = Join-Path $InstallRoot "sources\ComfyUI"
$python = Join-Path $InstallRoot "venv\Scripts\python.exe"
$stateRoot = Join-Path $InstallRoot "state"
$sentinel = Join-Path $stateRoot "ready.json"
$lastPreflight = Join-Path $stateRoot "last-preflight.json"
$inputRoot = Join-Path $InstallRoot "input"
$outputRoot = Join-Path $InstallRoot "output"
$tempRoot = Join-Path $InstallRoot "temp"
$logRoot = Join-Path $InstallRoot "logs"
$userRoot = Join-Path $InstallRoot "user"
$cacheRoot = Join-Path $InstallRoot "cache"
$probeContract = Join-Path $InstallRoot "probes\probe.json"
$comfyProcess = $null
$gatewayProcess = $null
$workerJob = $null

try {
    if ($PreflightOnly -and $Benchmark) {
        throw "PreflightOnly and Benchmark are mutually exclusive"
    }
    $workerJob = [ContentWorkerJob]::CreateKillOnCloseJob()
    foreach ($required in @($python, $comfyRoot, $packageRoot)) {
        if (-not (Test-Path $required)) { throw "Worker installation is incomplete: $required" }
    }
    New-Item -ItemType Directory -Path $stateRoot, $inputRoot, $outputRoot, $tempRoot, $logRoot, $userRoot, $cacheRoot -Force | Out-Null
    Remove-Item -LiteralPath $sentinel -Force -ErrorAction SilentlyContinue

    $comfyArguments = @(
        (Join-Path $comfyRoot "main.py"),
        "--listen", "127.0.0.1",
        "--port", "8188",
        "--disable-auto-launch",
        "--input-directory", $inputRoot,
        "--output-directory", $outputRoot,
        "--temp-directory", $tempRoot,
        "--user-directory", $userRoot
    )
    if ($Benchmark) {
        # Benchmark evidence is invalid if ComfyUI reuses the warm-up graph.
        # The pinned runtime exposes this explicit full-execution mode.
        $comfyArguments += "--cache-none"
    }
    $comfyProcess = Start-LoggedProcess `
        -Executable $python `
        -Arguments $comfyArguments `
        -WorkingDirectory $comfyRoot `
        -LogPrefix (Join-Path $logRoot "comfyui") `
        -WorkerJob $workerJob `
        -Environment @{
            "PYTHONDONTWRITEBYTECODE" = "1"
            "HF_HOME" = (Join-Path $cacheRoot "huggingface")
            "TORCH_HOME" = (Join-Path $cacheRoot "torch")
            "XDG_CACHE_HOME" = $cacheRoot
        }

    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    $online = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($comfyProcess.HasExited) {
            $comfyProcess.WaitForExit()
            throw "ComfyUI exited during startup with code $($comfyProcess.ExitCode); inspect logs"
        }
        try {
            $stats = Invoke-RestMethod -Uri "http://127.0.0.1:8188/system_stats" -TimeoutSec 2
            if ($null -ne $stats.system) { $online = $true; break }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $online) { throw "ComfyUI did not become reachable on loopback" }

    $preflightArguments = @(
        (Join-Path $packageRoot "preflight.py"),
        "--install-root", $InstallRoot,
        "--revisions", (Join-Path $packageRoot "revisions.json"),
        "--models", (Join-Path $packageRoot "models.json"),
        "--model-root", (Join-Path $comfyRoot "models"),
        "--probe-contract", $probeContract,
        "--input-root", $inputRoot,
        "--output-root", $outputRoot,
        "--sentinel", $sentinel,
        "--comfy-url", "http://127.0.0.1:8188"
    )
    & $python "-B" @preflightArguments
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $sentinel)) {
        throw "Readiness preflight failed; gateway will not start"
    }

    if ($PreflightOnly -or $Benchmark) {
        Copy-Item -LiteralPath $sentinel -Destination $lastPreflight -Force
    }

    if ($Benchmark) {
        $benchmarkResult = Join-Path $stateRoot "benchmark.json"
        & $python "-B" `
            (Join-Path $packageRoot "benchmark.py") `
            "--install-root" $InstallRoot `
            "--comfy-url" "http://127.0.0.1:8188" `
            "--worker-supervisor-pid" $comfyProcess.Id `
            "--result" $benchmarkResult
        if ($LASTEXITCODE -ne 0) {
            throw "Worker benchmark failed; inspect durable benchmark evidence"
        }
        Write-Host "Sequential LivePortrait benchmark passed. No gateway was started."
        return
    }

    if ($PreflightOnly) {
        Write-Host "Full one-frame expression preflight passed. No gateway was started."
        return
    }

    # Keep the at-logon worker lightweight while other desktop GPU work is
    # active. The execution proof remains durable; models reload on demand.
    Invoke-RestMethod `
        -Uri "http://127.0.0.1:8188/free" `
        -Method Post `
        -ContentType "application/json" `
        -Body '{"unload_models":true,"free_memory":true}' `
        -TimeoutSec 15 | Out-Null

    $secretPath = Join-Path $stateRoot "gateway-token.dpapi"
    if (-not (Test-Path $secretPath)) { throw "DPAPI gateway token is not configured" }
    $secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = $null
    try {
        $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ($plainToken.Length -lt 32) { throw "Decrypted gateway token is invalid" }
        $gatewayProcess = Start-LoggedProcess `
            -Executable $python `
            -Arguments @(
                (Join-Path $packageRoot "gateway.py"),
                "--listen", "127.0.0.1",
                "--port", "8189",
                "--upstream", "http://127.0.0.1:8188",
                "--sentinel", $sentinel,
                "--revisions", (Join-Path $packageRoot "revisions.json"),
                "--models", (Join-Path $packageRoot "models.json"),
                "--probe-contract", $probeContract,
                "--flux2-state-root", $Flux2StateRoot
            ) `
            -WorkingDirectory $packageRoot `
            -LogPrefix (Join-Path $logRoot "gateway") `
            -WorkerJob $workerJob `
            -Environment @{
                "COMFYUI_API_KEY" = $plainToken
                "PYTHONDONTWRITEBYTECODE" = "1"
            }
    } finally {
        if ($null -ne $plainToken) { $plainToken = $null }
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }

    while (-not $comfyProcess.HasExited -and -not $gatewayProcess.HasExited) {
        Start-Sleep -Seconds 2
    }
    throw "A worker process exited; inspect logs"
} finally {
    Remove-Item -LiteralPath $sentinel -Force -ErrorAction SilentlyContinue
    if ($null -ne $workerJob -and -not $workerJob.IsClosed) {
        # The kernel terminates every assigned descendant before the scheduled
        # task can restart this supervisor. Parent Process objects are waited
        # below so redirected log handles are also closed deterministically.
        $workerJob.Dispose()
    }
    foreach ($process in @($gatewayProcess, $comfyProcess)) {
        Stop-LoggedProcess -Process $process
    }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
