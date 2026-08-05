[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$stateRoot = Join-Path $InstallRoot "state"
$secretPath = Join-Path $stateRoot "gateway-token.dpapi"
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
$secureToken = Read-Host "Enter a random gateway token (at least 32 characters)" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $plainLength = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Length
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
if ($plainLength -lt 32) { throw "Gateway token must contain at least 32 characters" }

# Without -Key, ConvertFrom-SecureString uses Windows DPAPI for the current user.
$secureToken | ConvertFrom-SecureString | Set-Content -LiteralPath $secretPath -Encoding ASCII
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl = New-Object Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object Security.AccessControl.FileSystemAccessRule(
    $identity,
    "FullControl",
    "Allow"
)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $secretPath -AclObject $acl
Write-Host "Gateway token stored with current-user DPAPI protection at $secretPath"
