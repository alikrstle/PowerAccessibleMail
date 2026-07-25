param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$CertificateThumbprint = $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampServer = $(
        if ($env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER) {
            $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER
        }
        else {
            "http://timestamp.digicert.com"
        }
    ),
    [string]$InnoCompiler = "C:\Users\alikrstl\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Version = "1.2.9"
$AppName = "Power Accessible Mail"
$ProductName = "Power Accessible Mail"
$LockFile = Join-Path $ProjectRoot "requirements-release.lock"
$BuildScript = Join-Path $ProjectRoot "build_power_accessible_mail_64.ps1"
$SignScript = Join-Path $ProjectRoot "sign_release_file.ps1"
$InstallerScript = Join-Path $ProjectRoot "installer_power_accessible_mail.iss"
$InstallerResources = @(
    (Join-Path $ProjectRoot "installer_info_full_ar.txt"),
    (Join-Path $ProjectRoot "installer_info_full_en.txt"),
    (Join-Path $ProjectRoot "installer_readme_full_ar.txt"),
    (Join-Path $ProjectRoot "installer_readme_full_en.txt")
)
$ReleaseRoot = Join-Path $ProjectRoot "release"
$AppDir = Join-Path $ReleaseRoot "win-x64\$AppName"
$AppExe = Join-Path $AppDir "$AppName.exe"
$PackageAppDir = Join-Path $ReleaseRoot "package-win-x64\$AppName"
$PackageAppExe = Join-Path $PackageAppDir "$AppName.exe"
$InstallerDir = Join-Path $ReleaseRoot "installer"
$isSigned = -not [string]::IsNullOrWhiteSpace($CertificateThumbprint)
$buildKind = if ($isSigned) { "SIGNED" } else { "UNSIGNED" }
$outputSuffix = if ($isSigned) { "" } else { "-UNSIGNED" }
$InstallerExe = Join-Path $InstallerDir "PowerAccessibleMailFullSetup-$Version-win-x64$outputSuffix.exe"
$PublishedInstaller = Join-Path $ReleaseRoot "PowerAccessibleMailFullSetup-$Version-win-x64$outputSuffix.exe"
$PortableZip = Join-Path $ReleaseRoot "PowerAccessibleMailFull-$Version-win-x64$outputSuffix.zip"
$HashManifest = Join-Path $ReleaseRoot "SHA256SUMS-FULL-$buildKind.txt"
$BuildManifest = Join-Path $ReleaseRoot "$buildKind-FULL-BUILD-MANIFEST.json"

foreach ($required in @($PythonPath, $LockFile, $BuildScript, $InstallerScript, $InnoCompiler) + $InstallerResources) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required release input was not found: $required"
    }
}
if ($isSigned -and -not (Test-Path -LiteralPath $SignScript)) {
    throw "Signing was requested but the signing script was not found: $SignScript"
}

$expectedPackages = Get-Content -LiteralPath $LockFile |
    Where-Object { $_ -and -not $_.StartsWith("#") } |
    Sort-Object
$actualPackages = & $PythonPath -m pip freeze |
    Where-Object { $_ -and -not $_.StartsWith("#") } |
    Sort-Object
$packageDifference = Compare-Object $expectedPackages $actualPackages
if ($packageDifference) {
    throw "The release environment does not match requirements-release.lock.`n$($packageDifference | Out-String)"
}

& $PythonPath -m compileall -q (Join-Path $ProjectRoot "accessible_mail") (Join-Path $ProjectRoot "tests")
if ($LASTEXITCODE -ne 0) {
    throw "Python compilation failed."
}
& $PythonPath -m unittest discover -s (Join-Path $ProjectRoot "tests") -q
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed."
}

& $BuildScript -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $AppExe)) {
    throw "Full application build failed."
}

$versionInfo = (Get-Item -LiteralPath $AppExe).VersionInfo
if ($versionInfo.CompanyName -ne "Soljan.AlSharq." -or
    $versionInfo.ProductName -ne $ProductName -or
    $versionInfo.ProductVersion -ne $Version) {
    throw "The application executable is missing the expected Windows version information."
}

$upxCheck = @'
import pefile
import sys

image = pefile.PE(sys.argv[1], fast_load=True)
sections = [section.Name.rstrip(b"\0").decode("ascii", "replace") for section in image.sections]
upx_sections = [name for name in sections if name.upper().startswith("UPX")]
if upx_sections:
    raise SystemExit("UPX sections found: " + ", ".join(upx_sections))
'@
& $PythonPath -c $upxCheck $AppExe
if ($LASTEXITCODE -ne 0) {
    throw "The executable contains UPX-compressed sections."
}

$bundledOAuth = @(Get-ChildItem -LiteralPath $AppDir -Recurse -File -Filter "oauth_clients.json")
if ($bundledOAuth.Count -ne 1) {
    throw "Expected exactly one bundled oauth_clients.json, found $($bundledOAuth.Count)."
}
$bundledOAuthConfig = Get-Content -LiteralPath $bundledOAuth[0].FullName -Raw | ConvertFrom-Json
$bundledOAuthKeys = @($bundledOAuthConfig.PSObject.Properties.Name)
if ($bundledOAuthKeys -contains "google_gmail_api" -or
    $bundledOAuthKeys -notcontains "google" -or
    [string]::IsNullOrWhiteSpace([string]$bundledOAuthConfig.google.client_id)) {
    throw "The bundled OAuth file does not contain the expected full Google client."
}

if ($isSigned) {
    & $SignScript -FilePath $AppExe -CertificateThumbprint $CertificateThumbprint -TimestampServer $TimestampServer
    if ($LASTEXITCODE -ne 0) {
        throw "Application signing failed."
    }
    Copy-Item -LiteralPath $AppExe -Destination $PackageAppExe -Force
}

if (Test-Path -LiteralPath $InstallerDir) {
    $resolvedInstallerDir = [System.IO.Path]::GetFullPath($InstallerDir)
    $resolvedReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedInstallerDir.StartsWith($resolvedReleaseRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an installer directory outside the release root."
    }
    Remove-Item -LiteralPath $InstallerDir -Recurse -Force
}
New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null

if ($isSigned) {
    $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT = $CertificateThumbprint
    $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER = $TimestampServer
    $signCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File $q' + $SignScript + '$q $f'
    & $InnoCompiler "/DSignedBuild=1" "/SPowerAccessibleMail=$signCommand" $InstallerScript
}
else {
    & $InnoCompiler $InstallerScript
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $InstallerExe)) {
    throw "Installer build failed."
}
Copy-Item -LiteralPath $InstallerExe -Destination $PublishedInstaller -Force
$installerSourceHash = (Get-FileHash -LiteralPath $InstallerExe -Algorithm SHA256).Hash
$publishedInstallerHash = (Get-FileHash -LiteralPath $PublishedInstaller -Algorithm SHA256).Hash
if ($installerSourceHash -ne $publishedInstallerHash) {
    throw "The installer copy beside the portable ZIP does not match the compiled installer."
}

$filesToVerify = @($AppExe, $PublishedInstaller)
foreach ($file in $filesToVerify) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($isSigned) {
        if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
            throw "Signature verification failed for $file`: $($signature.StatusMessage)"
        }
        if (-not $signature.TimeStamperCertificate) {
            throw "Timestamp verification failed for $file."
        }
    }
    elseif ($signature.Status -ne [System.Management.Automation.SignatureStatus]::NotSigned) {
        throw "Unsigned build unexpectedly has signature status $($signature.Status) for $file."
    }
}

if (Test-Path -LiteralPath $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
Compress-Archive -LiteralPath $PackageAppDir -DestinationPath $PortableZip -CompressionLevel Optimal
$appHash = (Get-FileHash -LiteralPath $AppExe -Algorithm SHA256).Hash
$packageAppHash = (Get-FileHash -LiteralPath $PackageAppExe -Algorithm SHA256).Hash
if ($appHash -ne $packageAppHash) {
    throw "The portable package application does not match the verified application build."
}

$releaseFiles = @($AppExe, $PublishedInstaller, $PortableZip)
$hashRows = foreach ($file in $releaseFiles) {
    $hash = Get-FileHash -LiteralPath $file -Algorithm SHA256
    "$($hash.Hash) *$([System.IO.Path]::GetRelativePath($ReleaseRoot, $file).Replace('\', '/'))"
}
Set-Content -LiteralPath $HashManifest -Value $hashRows -Encoding ascii

$pythonVersion = (& $PythonPath --version 2>&1 | Out-String).Trim()
$signer = if ($isSigned) {
    (Get-AuthenticodeSignature -LiteralPath $PublishedInstaller).SignerCertificate
}
else {
    $null
}
$manifestFiles = foreach ($file in $releaseFiles) {
    [pscustomobject]@{
        Path = [System.IO.Path]::GetRelativePath($ReleaseRoot, $file).Replace('\', '/')
        Size = (Get-Item -LiteralPath $file).Length
        SHA256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    }
}
[pscustomobject]@{
    Product = $ProductName
    Edition = "full"
    Version = $Version
    Architecture = "win-x64"
    BuildKind = $buildKind
    BuiltAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    Python = $pythonVersion
    Packages = $actualPackages
    PyInstallerMode = "onedir"
    UPX = $false
    SignerSubject = if ($signer) { $signer.Subject } else { $null }
    SignerThumbprint = if ($signer) { $signer.Thumbprint } else { $null }
    TimestampServer = if ($isSigned) { $TimestampServer } else { $null }
    Files = $manifestFiles
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $BuildManifest -Encoding utf8

$finalVersionInfo = (Get-Item -LiteralPath $AppExe).VersionInfo
$finalInstallerHash = (Get-FileHash -LiteralPath $PublishedInstaller -Algorithm SHA256).Hash
if ($finalVersionInfo.CompanyName -ne "Soljan.AlSharq." -or
    $finalVersionInfo.ProductName -ne $ProductName -or
    $finalVersionInfo.ProductVersion -ne $Version) {
    throw "The application changed after verification; release output is not reliable."
}
if ($finalInstallerHash -ne $installerSourceHash) {
    throw "The published installer changed after verification; release output is not reliable."
}

Write-Output "$buildKind full release complete: $ReleaseRoot"
Write-Output "Installer: $PublishedInstaller"
Write-Output "Portable ZIP: $PortableZip"
Write-Output "SHA-256 manifest: $HashManifest"
