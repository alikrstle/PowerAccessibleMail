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
$Version = "1.2.8"
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
$AppDir = Join-Path $ReleaseRoot "win-x64\Power Accessible Mail"
$AppExe = Join-Path $AppDir "Power Accessible Mail.exe"
$PackageAppDir = Join-Path $ReleaseRoot "package-win-x64\Power Accessible Mail"
$PackageAppExe = Join-Path $PackageAppDir "Power Accessible Mail.exe"
$InstallerDir = Join-Path $ReleaseRoot "installer"
$InstallerExe = Join-Path $InstallerDir "PowerAccessibleMailSetup-$Version-win-x64.exe"
$PortableZip = Join-Path $ReleaseRoot "PowerAccessibleMail-$Version-win-x64.zip"
$HashManifest = Join-Path $ReleaseRoot "SHA256SUMS.txt"
$BuildManifest = Join-Path $ReleaseRoot "BUILD-MANIFEST.json"

foreach ($required in @($PythonPath, $LockFile, $BuildScript, $SignScript, $InstallerScript, $InnoCompiler) + $InstallerResources) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required release input was not found: $required"
    }
}
if (-not $CertificateThumbprint) {
    throw "A trusted Authenticode certificate is required. Set POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT."
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
    throw "Application build failed."
}

$env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT = $CertificateThumbprint
$env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER = $TimestampServer
& $SignScript -FilePath $AppExe -CertificateThumbprint $CertificateThumbprint -TimestampServer $TimestampServer
if ($LASTEXITCODE -ne 0) {
    throw "Application signing failed."
}

if (Test-Path -LiteralPath $PackageAppDir) {
    Copy-Item -LiteralPath $AppExe -Destination $PackageAppExe -Force
}

if (Test-Path -LiteralPath $InstallerDir) {
    $resolvedInstallerDir = [System.IO.Path]::GetFullPath($InstallerDir)
    $resolvedReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedInstallerDir.StartsWith($resolvedReleaseRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an installer directory outside the release root."
    }
    Remove-Item -LiteralPath $InstallerDir -Recurse -Force
}
New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null

$signCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File $q' + $SignScript + '$q $f'
& $InnoCompiler "/DSignedBuild=1" "/SPowerAccessibleMail=$signCommand" $InstallerScript
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $InstallerExe)) {
    throw "Signed installer build failed."
}

foreach ($signedFile in @($AppExe, $InstallerExe)) {
    $signature = Get-AuthenticodeSignature -LiteralPath $signedFile
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Signature verification failed for $signedFile`: $($signature.StatusMessage)"
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "Timestamp verification failed for $signedFile."
    }
}

if (Test-Path -LiteralPath $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
Compress-Archive -LiteralPath $PackageAppDir -DestinationPath $PortableZip -CompressionLevel Optimal

$releaseFiles = @($AppExe, $InstallerExe, $PortableZip)
$hashRows = foreach ($file in $releaseFiles) {
    $hash = Get-FileHash -LiteralPath $file -Algorithm SHA256
    "$($hash.Hash) *$([System.IO.Path]::GetRelativePath($ReleaseRoot, $file).Replace('\', '/'))"
}
Set-Content -LiteralPath $HashManifest -Value $hashRows -Encoding ascii

$pythonVersion = (& $PythonPath --version 2>&1 | Out-String).Trim()
$signer = (Get-AuthenticodeSignature -LiteralPath $InstallerExe).SignerCertificate
$manifestFiles = foreach ($file in $releaseFiles) {
    [pscustomobject]@{
        Path = [System.IO.Path]::GetRelativePath($ReleaseRoot, $file).Replace('\', '/')
        Size = (Get-Item -LiteralPath $file).Length
        SHA256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    }
}
[pscustomobject]@{
    Product = "Power Accessible Mail"
    Version = $Version
    Architecture = "win-x64"
    BuiltAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    Python = $pythonVersion
    Packages = $actualPackages
    SignerSubject = $signer.Subject
    SignerThumbprint = $signer.Thumbprint
    TimestampServer = $TimestampServer
    Files = $manifestFiles
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $BuildManifest -Encoding utf8

Write-Output "Signed release complete: $ReleaseRoot"
Write-Output "SHA-256 manifest: $HashManifest"
