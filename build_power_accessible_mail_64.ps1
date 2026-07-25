param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$AppName = "Power Accessible Mail"
$BuildRoot = Join-Path $PSScriptRoot "build"
$DistRoot = Join-Path $PSScriptRoot "dist"
$ReleaseRoot = Join-Path $PSScriptRoot "release"
$ReleaseDir = Join-Path $ReleaseRoot "win-x64"
$AppDistDir = Join-Path $DistRoot $AppName
$PackageDir = Join-Path $ReleaseRoot "package-win-x64"
$PackageAppDir = Join-Path $PackageDir $AppName
$OAuthClients = Join-Path $PSScriptRoot ". النسخة الكاملة\oauth_clients.json"
$VersionInfo = Join-Path $PSScriptRoot "windows_version_info.txt"
$AppIcon = Join-Path $PSScriptRoot "assets\branding\power_accessible_mail.ico"
$LoginLogo = Join-Path $PSScriptRoot "assets\branding\power_accessible_mail_oauth_120.png"
$NvdaVendor = Join-Path $PSScriptRoot "accessible_mail\vendor\nvda"
$NvdaController = Join-Path $NvdaVendor "nvdaControllerClient.dll"
$NvdaLicense = Join-Path $NvdaVendor "LICENSE-LGPL-2.1.txt"
$NvdaReadme = Join-Path $NvdaVendor "NVDA-CONTROLLER-README.md"
$NvdaSource = Join-Path $NvdaVendor "SOURCE.txt"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "PythonPath not found: $PythonPath"
}

if (-not (Test-Path -LiteralPath $OAuthClients)) {
    throw "The full edition oauth_clients.json is required: $OAuthClients"
}

if (-not (Test-Path -LiteralPath $VersionInfo)) {
    throw "Windows version information is required: $VersionInfo"
}

if (-not (Test-Path -LiteralPath $AppIcon)) {
    throw "Application icon is required: $AppIcon"
}

if (-not (Test-Path -LiteralPath $LoginLogo)) {
    throw "Application login logo is required: $LoginLogo"
}

foreach ($nvdaFile in @($NvdaController, $NvdaLicense, $NvdaReadme, $NvdaSource)) {
    if (-not (Test-Path -LiteralPath $nvdaFile)) {
        throw "NVDA Controller Client file is required: $nvdaFile"
    }
}
$expectedNvdaControllerHash = "2FE60CF00BE929AAE32E95C1E1507A20ADA4902C8FEC273B3CC2D3BF5472932A"
$actualNvdaControllerHash = (Get-FileHash -LiteralPath $NvdaController -Algorithm SHA256).Hash
if ($actualNvdaControllerHash -ne $expectedNvdaControllerHash) {
    throw "The NVDA Controller Client SHA-256 does not match the approved official file."
}
$nvdaControllerSignature = Get-AuthenticodeSignature -LiteralPath $NvdaController
if ($nvdaControllerSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
    $nvdaControllerSignature.SignerCertificate.Subject -notlike "CN=NV Access Limited,*") {
    throw "The NVDA Controller Client does not have a valid NV Access Limited signature."
}

try {
    $oauthConfig = Get-Content -LiteralPath $OAuthClients -Raw | ConvertFrom-Json
}
catch {
    throw "The full edition oauth_clients.json is not valid JSON: $($_.Exception.Message)"
}
$oauthKeys = @($oauthConfig.PSObject.Properties.Name)
if ($oauthKeys -contains "google_gmail_api" -or $oauthKeys -notcontains "google") {
    throw "The full OAuth file must contain google and must not contain google_gmail_api."
}
if ([string]::IsNullOrWhiteSpace([string]$oauthConfig.google.client_id)) {
    throw "The full Google OAuth client_id is required for the full release."
}

$is64 = & $PythonPath -c "import platform; print(platform.architecture()[0])"
if ($is64.Trim() -ne "64bit") {
    throw "This build requires a 64-bit Python. Current Python reports: $is64"
}

if (Test-Path -LiteralPath $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
if (Test-Path -LiteralPath $DistRoot) {
    Remove-Item -LiteralPath $DistRoot -Recurse -Force
}
if (Test-Path -LiteralPath $ReleaseDir) {
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
}

$dataArgs = @(
    "--add-data", ($OAuthClients + ";.")
)

if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "backgrounds")) {
    $dataArgs += @("--add-data", ((Join-Path $PSScriptRoot "backgrounds") + ";backgrounds"))
}
$dataArgs += @("--add-data", ($AppIcon + ";assets\branding"))
$dataArgs += @("--add-data", ($LoginLogo + ";assets\branding"))
$dataArgs += @("--add-binary", ($NvdaController + ";accessible_mail\vendor\nvda"))
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

$bundledOAuth = @(Get-ChildItem -LiteralPath $AppDistDir -Recurse -File -Filter "oauth_clients.json")
if ($bundledOAuth.Count -ne 1) {
    throw "Expected exactly one bundled full oauth_clients.json, found $($bundledOAuth.Count)."
}
$bundledOAuthConfig = Get-Content -LiteralPath $bundledOAuth[0].FullName -Raw | ConvertFrom-Json
$bundledOAuthKeys = @($bundledOAuthConfig.PSObject.Properties.Name)
if ($bundledOAuthKeys -contains "google_gmail_api" -or
    $bundledOAuthKeys -notcontains "google" -or
    [string]::IsNullOrWhiteSpace([string]$bundledOAuthConfig.google.client_id)) {
    throw "The bundled full OAuth file does not contain the expected full Google client."
}
$bundledLogo = @(Get-ChildItem -LiteralPath $AppDistDir -Recurse -File -Filter "power_accessible_mail_oauth_120.png")
if ($bundledLogo.Count -ne 1) {
    throw "Expected exactly one bundled login logo, found $($bundledLogo.Count)."
}
$bundledNvdaController = @(Get-ChildItem -LiteralPath $AppDistDir -Recurse -File -Filter "nvdaControllerClient.dll")
if ($bundledNvdaController.Count -ne 1) {
    throw "Expected exactly one bundled NVDA Controller Client, found $($bundledNvdaController.Count)."
}

New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
Copy-Item -LiteralPath $AppDistDir -Destination $ReleaseDir -Recurse -Force
if (Test-Path -LiteralPath $PackageDir) {
    if (Test-Path -LiteralPath $PackageAppDir) {
        Remove-Item -LiteralPath $PackageAppDir -Recurse -Force
    }
    Copy-Item -LiteralPath $AppDistDir -Destination $PackageAppDir -Recurse -Force
}

$forbidden = @("accounts.json", "messages.sqlite3", ".mail_store")
foreach ($name in $forbidden) {
    $matches = Get-ChildItem -LiteralPath $ReleaseDir -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $name }
    if ($matches) {
        throw "Forbidden private file found in release: $name"
    }
}

Write-Output "Build complete: $ReleaseDir"
if (Test-Path -LiteralPath $PackageDir) {
    Write-Output "Package app folder updated: $PackageAppDir"
}
