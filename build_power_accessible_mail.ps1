param(
    [ValidateSet("x64", "x86")]
    [string]$Architecture = "x64",
    [string]$PythonPath = $(if ($Architecture -eq "x64") {
        ".\.venv\Scripts\python.exe"
    }
    else {
        ".\.venv-x86\Scripts\python.exe"
    })
)

$ErrorActionPreference = "Stop"

$AppName = "Power Accessible Mail"
$BuildRoot = Join-Path $PSScriptRoot "build-$Architecture"
$DistRoot = Join-Path $PSScriptRoot "dist-$Architecture"
$ReleaseRoot = Join-Path $PSScriptRoot "release"
$ReleaseDir = Join-Path $ReleaseRoot "win-$Architecture"
$AppDistDir = Join-Path $DistRoot $AppName
$AppDistExe = Join-Path $AppDistDir "$AppName.exe"
$PackageDir = Join-Path $ReleaseRoot "package-win-$Architecture"
$PackageAppDir = Join-Path $PackageDir $AppName
$OAuthClients = Join-Path $PSScriptRoot "oauth_clients.json"
$VersionInfo = Join-Path $PSScriptRoot "windows_version_info.txt"
$AppIcon = Join-Path $PSScriptRoot "assets\branding\power_accessible_mail.ico"
$LoginLogo = Join-Path $PSScriptRoot "assets\branding\power_accessible_mail_oauth_120.png"
$NvdaVendor = Join-Path $PSScriptRoot "accessible_mail\vendor\nvda"
$NvdaController = Join-Path $NvdaVendor "$Architecture\nvdaControllerClient.dll"
$NvdaLicense = Join-Path $NvdaVendor "LICENSE-LGPL-2.1.txt"
$NvdaReadme = Join-Path $NvdaVendor "NVDA-CONTROLLER-README.md"
$NvdaSource = Join-Path $NvdaVendor "SOURCE.txt"
$ExpectedNvdaHashes = @{
    x64 = "2FE60CF00BE929AAE32E95C1E1507A20ADA4902C8FEC273B3CC2D3BF5472932A"
    x86 = "AB824A1126FEF9135F5E7FEDC4DDEB8EBCE73A5BFCB6086E1799971D92DCA8B4"
}

function Remove-ProjectDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $resolvedRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $resolvedPath.StartsWith(
        $resolvedRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to remove a directory outside the project root: $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

foreach ($required in @(
    $PythonPath,
    $OAuthClients,
    $VersionInfo,
    $AppIcon,
    $LoginLogo,
    $NvdaController,
    $NvdaLicense,
    $NvdaReadme,
    $NvdaSource
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required build input was not found: $required"
    }
}

$expectedBits = if ($Architecture -eq "x64") { 64 } else { 32 }
$pythonBits = & $PythonPath -c "import struct; print(struct.calcsize('P') * 8)"
if ([int]$pythonBits -ne $expectedBits) {
    throw "The $Architecture build requires $expectedBits-bit Python. Current Python reports: $pythonBits"
}
$expectedMachine = if ($Architecture -eq "x64") { 0x8664 } else { 0x014C }
$bootloaderFolder = if ($Architecture -eq "x64") {
    "Windows-64bit-intel"
}
else {
    "Windows-32bit-intel"
}
$bootloaderMachine = & $PythonPath -c @"
from pathlib import Path
import pefile
import PyInstaller
path = Path(PyInstaller.__file__).resolve().parent / "bootloader" / "$bootloaderFolder" / "runw.exe"
print(pefile.PE(str(path), fast_load=True).FILE_HEADER.Machine)
"@
if ($LASTEXITCODE -ne 0 -or [int]$bootloaderMachine -ne $expectedMachine) {
    throw (
        "The $Architecture PyInstaller bootloader has the wrong PE architecture. " +
        "Force-reinstall PyInstaller with $PythonPath before building."
    )
}

$actualNvdaControllerHash = (
    Get-FileHash -LiteralPath $NvdaController -Algorithm SHA256
).Hash
if ($actualNvdaControllerHash -ne $ExpectedNvdaHashes[$Architecture]) {
    throw "The $Architecture NVDA Controller Client SHA-256 is not approved."
}
$nvdaControllerSignature = Get-AuthenticodeSignature -LiteralPath $NvdaController
if ($nvdaControllerSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
    $nvdaControllerSignature.SignerCertificate.Subject -notlike "CN=NV Access Limited,*") {
    throw "The $Architecture NVDA Controller Client signature is not valid."
}

try {
    $oauthConfig = Get-Content -LiteralPath $OAuthClients -Raw | ConvertFrom-Json
}
catch {
    throw "oauth_clients.json is not valid JSON: $($_.Exception.Message)"
}
$oauthKeys = @($oauthConfig.PSObject.Properties.Name)
$unexpectedOAuthKeys = @(
    $oauthKeys | Where-Object { $_ -notin @("google_gmail_api", "microsoft") }
)
if ($unexpectedOAuthKeys.Count -gt 0 -or
    $oauthKeys -notcontains "google_gmail_api" -or
    $oauthKeys -notcontains "microsoft") {
    throw "The unified OAuth file must contain only google_gmail_api and microsoft."
}
if ([string]::IsNullOrWhiteSpace([string]$oauthConfig.google_gmail_api.client_id)) {
    throw "The Google Gmail API client_id is required."
}
if ([string]::IsNullOrWhiteSpace([string]$oauthConfig.microsoft.client_id)) {
    throw "The Microsoft client_id is required."
}

foreach ($directory in @($BuildRoot, $DistRoot, $ReleaseDir, $PackageDir)) {
    Remove-ProjectDirectory -Path $directory
}

$dataArgs = @(
    "--add-data", ($OAuthClients + ";.")
)
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "backgrounds")) {
    $dataArgs += @(
        "--add-data",
        ((Join-Path $PSScriptRoot "backgrounds") + ";backgrounds")
    )
}
$dataArgs += @("--add-data", ($AppIcon + ";assets\branding"))
$dataArgs += @("--add-data", ($LoginLogo + ";assets\branding"))
$dataArgs += @(
    "--add-binary",
    ($NvdaController + ";accessible_mail\vendor\nvda\$Architecture")
)
$dataArgs += @("--add-data", ($NvdaLicense + ";accessible_mail\vendor\nvda"))
$dataArgs += @("--add-data", ($NvdaReadme + ";accessible_mail\vendor\nvda"))
$dataArgs += @("--add-data", ($NvdaSource + ";accessible_mail\vendor\nvda"))

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--noupx",
    "--windowed",
    "--version-file", $VersionInfo,
    "--icon", $AppIcon,
    "--name", $AppName,
    "--distpath", $DistRoot,
    "--workpath", $BuildRoot,
    "--specpath", $BuildRoot
) + $dataArgs + @("main.py")

Push-Location $PSScriptRoot
try {
    & $PythonPath $pyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $AppDistDir)) {
    throw "Expected dist folder was not created: $AppDistDir"
}
$appMachine = & $PythonPath -c @"
import pefile
print(pefile.PE(r"$AppDistExe", fast_load=True).FILE_HEADER.Machine)
"@
if ($LASTEXITCODE -ne 0 -or [int]$appMachine -ne $expectedMachine) {
    throw "The built application PE architecture does not match $Architecture."
}

$bundledOAuth = @(Get-ChildItem -LiteralPath $AppDistDir -Recurse -File -Filter "oauth_clients.json")
if ($bundledOAuth.Count -ne 1) {
    throw "Expected exactly one bundled oauth_clients.json, found $($bundledOAuth.Count)."
}
$bundledOAuthConfig = Get-Content -LiteralPath $bundledOAuth[0].FullName -Raw |
    ConvertFrom-Json
$bundledOAuthKeys = @($bundledOAuthConfig.PSObject.Properties.Name)
if ($bundledOAuthKeys.Count -ne 2 -or
    $bundledOAuthKeys -notcontains "google_gmail_api" -or
    $bundledOAuthKeys -notcontains "microsoft" -or
    [string]::IsNullOrWhiteSpace(
        [string]$bundledOAuthConfig.google_gmail_api.client_id
    ) -or
    [string]::IsNullOrWhiteSpace(
        [string]$bundledOAuthConfig.microsoft.client_id
    )) {
    throw "The bundled OAuth file is not the expected unified configuration."
}

$bundledNvdaControllers = @(
    Get-ChildItem -LiteralPath $AppDistDir -Recurse -File -Filter "nvdaControllerClient.dll"
)
if ($bundledNvdaControllers.Count -ne 1) {
    throw "Expected exactly one bundled NVDA Controller Client, found $($bundledNvdaControllers.Count)."
}
$bundledNvdaHash = (
    Get-FileHash -LiteralPath $bundledNvdaControllers[0].FullName -Algorithm SHA256
).Hash
if ($bundledNvdaHash -ne $ExpectedNvdaHashes[$Architecture]) {
    throw "The bundled NVDA Controller Client does not match $Architecture."
}

New-Item -ItemType Directory -Path $ReleaseDir,$PackageDir -Force | Out-Null
Copy-Item -LiteralPath $AppDistDir -Destination $ReleaseDir -Recurse -Force
Copy-Item -LiteralPath $AppDistDir -Destination $PackageDir -Recurse -Force

$forbidden = @("accounts.json", "messages.sqlite3", ".mail_store")
foreach ($directory in @($ReleaseDir, $PackageDir)) {
    foreach ($name in $forbidden) {
        $matches = Get-ChildItem -LiteralPath $directory -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $name }
        if ($matches) {
            throw "Forbidden private file found in release: $name"
        }
    }
}

Write-Output "Unified $Architecture build complete: $ReleaseDir"
Write-Output "Portable package folder updated: $PackageAppDir"
