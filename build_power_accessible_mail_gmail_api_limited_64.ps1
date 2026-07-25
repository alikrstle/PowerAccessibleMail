param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$AppName = "Power Accessible Mail"
$BuildRoot = Join-Path $PSScriptRoot "build-gmail-api-limited"
$DistRoot = Join-Path $PSScriptRoot "dist-gmail-api-limited"
$ReleaseRoot = Join-Path $PSScriptRoot "release"
$ReleaseDir = Join-Path $ReleaseRoot "win-x64-gmail-api-limited"
$AppDistDir = Join-Path $DistRoot $AppName
$OAuthClients = Join-Path $PSScriptRoot ". النسخة المحدودة\oauth_clients.json"
$PackageDir = Join-Path $ReleaseRoot "package-win-x64-gmail-api-limited"
$PackageAppDir = Join-Path $PackageDir $AppName
$VersionInfo = Join-Path $PSScriptRoot "windows_version_info_gmail_api_limited.txt"
$AppIcon = Join-Path $PSScriptRoot "assets\branding\power_accessible_mail.ico"
$LoginLogo = Join-Path $PSScriptRoot "assets\branding\power_accessible_mail_oauth_120.png"
$NvdaVendor = Join-Path $PSScriptRoot "accessible_mail\vendor\nvda"
$NvdaController = Join-Path $NvdaVendor "nvdaControllerClient.dll"
$NvdaLicense = Join-Path $NvdaVendor "LICENSE-LGPL-2.1.txt"
$NvdaReadme = Join-Path $NvdaVendor "NVDA-CONTROLLER-README.md"
$NvdaSource = Join-Path $NvdaVendor "SOURCE.txt"

function Remove-ProjectDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolvedRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a directory outside the project root: $resolvedPath"
    }

    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "PythonPath not found: $PythonPath"
}

if (-not (Test-Path -LiteralPath $OAuthClients)) {
    throw "The Gmail API limited oauth_clients.json is required: $OAuthClients"
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
    throw "The Gmail API limited oauth_clients.json is not valid JSON: $($_.Exception.Message)"
}
$oauthKeys = @($oauthConfig.PSObject.Properties.Name)
if ($oauthKeys.Count -ne 1 -or $oauthKeys[0] -ne "google_gmail_api") {
    throw "The limited OAuth file must contain only the google_gmail_api client."
}
if ([string]::IsNullOrWhiteSpace([string]$oauthConfig.google_gmail_api.client_id)) {
    throw "The google_gmail_api client_id is required for the limited release."
}

$is64 = & $PythonPath -c "import platform; print(platform.architecture()[0])"
if ($is64.Trim() -ne "64bit") {
    throw "This build requires a 64-bit Python. Current Python reports: $is64"
}

foreach ($directory in @($BuildRoot, $DistRoot, $ReleaseDir, $PackageDir)) {
    Remove-ProjectDirectory -Path $directory
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
) + $dataArgs + @("main_gmail_api_limited.py")

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
    throw "Expected exactly one bundled limited oauth_clients.json, found $($bundledOAuth.Count)."
}
$bundledOAuthConfig = Get-Content -LiteralPath $bundledOAuth[0].FullName -Raw | ConvertFrom-Json
$bundledOAuthKeys = @($bundledOAuthConfig.PSObject.Properties.Name)
if ($bundledOAuthKeys.Count -ne 1 -or
    $bundledOAuthKeys[0] -ne "google_gmail_api" -or
    [string]::IsNullOrWhiteSpace([string]$bundledOAuthConfig.google_gmail_api.client_id)) {
    throw "The bundled OAuth file is not isolated to the limited Gmail API client."
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
New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null
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

Write-Output "Build complete: $ReleaseDir"
Write-Output "Package app folder updated: $PackageAppDir"
