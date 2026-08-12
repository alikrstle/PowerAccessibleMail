param(
    [ValidateSet("x64", "x86")]
    [string]$Architecture = "x64",
    [string]$PythonPath = $(if ($Architecture -eq "x64") {
        ".\.venv\Scripts\python.exe"
    }
    else {
        ".\.venv-x86\Scripts\python.exe"
    }),
    [string]$CertificateThumbprint = $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampServer = $(
        if ($env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER) {
            $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER
        }
        else {
            "https://timestamp.digicert.com"
        }
    ),
    [switch]$AllowUnsigned,
    [switch]$RunDefenderScan,
    [string]$InnoCompiler = "C:\Users\alikrstl\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Version = "1.2.14"
$AppName = "Power Accessible Mail"
$ProductName = "Power Accessible Mail"
$LockFile = Join-Path $ProjectRoot "requirements-release.lock"

function Get-CompatibleRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$ChildPath
    )

    $baseFullPath = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\', '/') + '\'
    $childFullPath = [System.IO.Path]::GetFullPath($ChildPath)
    $relativePath = [System.Uri]::UnescapeDataString(
        ([System.Uri]$baseFullPath).MakeRelativeUri([System.Uri]$childFullPath).ToString()
    ).Replace('/', '\')
    if ($relativePath -eq '..' -or $relativePath.StartsWith('..\')) {
        throw "Path is outside the expected base directory: $ChildPath"
    }
    return $relativePath
}
$BuildScript = Join-Path $ProjectRoot "build_power_accessible_mail.ps1"
$SignScript = Join-Path $ProjectRoot "sign_release_file.ps1"
$DefenderScanScript = Join-Path $ProjectRoot "scan_release_with_defender.ps1"
$InstallerScript = Join-Path $ProjectRoot "installer_power_accessible_mail.iss"
$InstallerResources = @(
    (Join-Path $ProjectRoot "installer_info_ar.txt"),
    (Join-Path $ProjectRoot "installer_info_en.txt"),
    (Join-Path $ProjectRoot "installer_info_fr.txt"),
    (Join-Path $ProjectRoot "installer_readme_ar.txt"),
    (Join-Path $ProjectRoot "installer_readme_en.txt"),
    (Join-Path $ProjectRoot "installer_readme_fr.txt")
)
$ReleaseRoot = Join-Path $ProjectRoot "release"
$AppDir = Join-Path $ReleaseRoot "win-$Architecture\$AppName"
$AppExe = Join-Path $AppDir "$AppName.exe"
$PackageAppDir = Join-Path $ReleaseRoot "package-win-$Architecture\$AppName"
$PackageAppExe = Join-Path $PackageAppDir "$AppName.exe"
$ArabicReadme = Join-Path $ProjectRoot "installer_readme_ar.txt"
$EnglishReadme = Join-Path $ProjectRoot "installer_readme_en.txt"
$FrenchReadme = Join-Path $ProjectRoot "installer_readme_fr.txt"
$PackageArabicReadme = Join-Path $PackageAppDir "README_AR.txt"
$PackageEnglishReadme = Join-Path $PackageAppDir "README_EN.txt"
$PackageFrenchReadme = Join-Path $PackageAppDir "README_FR.txt"
$InstallerDir = Join-Path $ReleaseRoot "installer"
$isSigned = -not [string]::IsNullOrWhiteSpace($CertificateThumbprint)
if (-not $isSigned -and -not $AllowUnsigned) {
    throw (
        "Public releases must be Authenticode-signed. Set " +
        "POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT or pass " +
        "-AllowUnsigned for a clearly labeled tester-only GitHub pre-release. " +
        "Never publish an unsigned build as a stable release."
    )
}
$buildKind = if ($isSigned) { "SIGNED" } else { "UNSIGNED" }
$outputSuffix = if ($isSigned) { "" } else { "-UNSIGNED" }
$assetBaseName = "PowerAccessibleMailSetup-$Version-win-$Architecture$outputSuffix.exe"
$InstallerExe = Join-Path $InstallerDir $assetBaseName
$PublishedInstaller = Join-Path $ReleaseRoot $assetBaseName
$PortableZip = Join-Path $ReleaseRoot "PowerAccessibleMail-$Version-win-$Architecture$outputSuffix.zip"
$HashManifest = Join-Path $ReleaseRoot "SHA256SUMS-$($Architecture.ToUpperInvariant())-$buildKind.txt"
$BuildManifest = Join-Path $ReleaseRoot "$buildKind-$($Architecture.ToUpperInvariant())-BUILD-MANIFEST.json"

foreach ($required in @(
    $PythonPath,
    $LockFile,
    $BuildScript,
    $InstallerScript,
    $InnoCompiler
) + $InstallerResources) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required release input was not found: $required"
    }
}
if ($isSigned -and -not (Test-Path -LiteralPath $SignScript)) {
    throw "Signing was requested but the signing script was not found: $SignScript"
}
if ($RunDefenderScan -and -not (Test-Path -LiteralPath $DefenderScanScript)) {
    throw "Defender scanning was requested but its script was not found: $DefenderScanScript"
}

$expectedBits = if ($Architecture -eq "x64") { 64 } else { 32 }
$pythonBits = & $PythonPath -c "import struct; print(struct.calcsize('P') * 8)"
if ([int]$pythonBits -ne $expectedBits) {
    throw "The $Architecture release requires $expectedBits-bit Python."
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

& $PythonPath -m compileall -q `
    (Join-Path $ProjectRoot "accessible_mail") `
    (Join-Path $ProjectRoot "tests")
if ($LASTEXITCODE -ne 0) {
    throw "Python compilation failed."
}
& $PythonPath -m unittest discover -s (Join-Path $ProjectRoot "tests") -q
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed."
}

& $BuildScript -Architecture $Architecture -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $AppExe)) {
    throw "$Architecture application build failed."
}

$versionInfo = (Get-Item -LiteralPath $AppExe).VersionInfo
if ($versionInfo.CompanyName -ne "Soljan.AlSharq." -or
    $versionInfo.ProductName -ne $ProductName -or
    $versionInfo.ProductVersion -ne $Version) {
    throw "The application executable is missing the expected Windows version information."
}

$peCheck = @'
import pefile
import sys

image = pefile.PE(sys.argv[1], fast_load=True)
expected_machine = int(sys.argv[2], 16)
if image.FILE_HEADER.Machine != expected_machine:
    raise SystemExit(
        f'Unexpected PE machine 0x{image.FILE_HEADER.Machine:04X}; '
        f'expected 0x{expected_machine:04X}'
    )
sections = [
    section.Name.rstrip(b'\0').decode('ascii', 'replace')
    for section in image.sections
]
upx_sections = [name for name in sections if name.upper().startswith('UPX')]
if upx_sections:
    raise SystemExit('UPX sections found: ' + ', '.join(upx_sections))
'@
$expectedMachine = if ($Architecture -eq "x64") { "8664" } else { "014c" }
& $PythonPath -c $peCheck $AppExe $expectedMachine
if ($LASTEXITCODE -ne 0) {
    throw "The executable architecture or UPX verification failed."
}

$bundledOAuth = @(
    Get-ChildItem -LiteralPath $AppDir -Recurse -File -Filter "oauth_clients.json"
)
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
    throw "The release does not contain the unified OAuth configuration."
}

$signableExtensions = @(".exe", ".dll", ".pyd")
$applicationPeFiles = @(
    Get-ChildItem -LiteralPath $AppDir -Recurse -File |
        Where-Object { $signableExtensions -contains $_.Extension.ToLowerInvariant() }
)
if (-not $applicationPeFiles) {
    throw "The application package does not contain any signable PE files."
}
if ($isSigned) {
    foreach ($file in $applicationPeFiles) {
        $existingSignature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        if ($existingSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
            & $SignScript `
                -FilePath $file.FullName `
                -CertificateThumbprint $CertificateThumbprint `
                -TimestampServer $TimestampServer
            if ($LASTEXITCODE -ne 0) {
                throw "Application component signing failed for $($file.FullName)."
            }
        }
        $relativePath = Get-CompatibleRelativePath $AppDir $file.FullName
        $packageFile = Join-Path $PackageAppDir $relativePath
        New-Item -ItemType Directory -Path (Split-Path $packageFile) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $packageFile -Force
    }
}

New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
foreach ($oldOutput in @($InstallerExe, $PublishedInstaller)) {
    if (Test-Path -LiteralPath $oldOutput) {
        Remove-Item -LiteralPath $oldOutput -Force
    }
}

if ($isSigned) {
    $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT = $CertificateThumbprint
    $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER = $TimestampServer
    $signCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File $q' +
        $SignScript + '$q $f'
    & $InnoCompiler `
        "/DTargetArchitecture=$Architecture" `
        "/DSignedBuild=1" `
        "/SPowerAccessibleMail=$signCommand" `
        $InstallerScript
}
else {
    & $InnoCompiler "/DTargetArchitecture=$Architecture" $InstallerScript
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $InstallerExe)) {
    throw "$Architecture installer build failed."
}
Copy-Item -LiteralPath $InstallerExe -Destination $PublishedInstaller -Force

$installerSourceHash = (
    Get-FileHash -LiteralPath $InstallerExe -Algorithm SHA256
).Hash
$publishedInstallerHash = (
    Get-FileHash -LiteralPath $PublishedInstaller -Algorithm SHA256
).Hash
if ($installerSourceHash -ne $publishedInstallerHash) {
    throw "The published installer does not match the compiled installer."
}

foreach ($file in @($AppExe, $PublishedInstaller)) {
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

if ($isSigned) {
    foreach ($file in $applicationPeFiles) {
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
            throw "PE signature verification failed for $($file.FullName): $($signature.StatusMessage)"
        }
        $relativePath = Get-CompatibleRelativePath $AppDir $file.FullName
        $packageFile = Join-Path $PackageAppDir $relativePath
        $packageSignature = Get-AuthenticodeSignature -LiteralPath $packageFile
        if ($packageSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
            throw "Portable PE signature verification failed for $packageFile."
        }
    }
}

if (Test-Path -LiteralPath $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
Copy-Item -LiteralPath $ArabicReadme -Destination $PackageArabicReadme -Force
Copy-Item -LiteralPath $EnglishReadme -Destination $PackageEnglishReadme -Force
Copy-Item -LiteralPath $FrenchReadme -Destination $PackageFrenchReadme -Force
foreach ($readmePair in @(
    @($ArabicReadme, $PackageArabicReadme),
    @($EnglishReadme, $PackageEnglishReadme),
    @($FrenchReadme, $PackageFrenchReadme)
)) {
    $sourceReadmeHash = (
        Get-FileHash -LiteralPath $readmePair[0] -Algorithm SHA256
    ).Hash
    $packageReadmeHash = (
        Get-FileHash -LiteralPath $readmePair[1] -Algorithm SHA256
    ).Hash
    if ($sourceReadmeHash -ne $packageReadmeHash) {
        throw "The portable package guide does not match its source file."
    }
}
Compress-Archive `
    -LiteralPath $PackageAppDir `
    -DestinationPath $PortableZip `
    -CompressionLevel Optimal

$appHash = (Get-FileHash -LiteralPath $AppExe -Algorithm SHA256).Hash
$packageAppHash = (
    Get-FileHash -LiteralPath $PackageAppExe -Algorithm SHA256
).Hash
if ($appHash -ne $packageAppHash) {
    throw "The portable package application does not match the verified build."
}

$releaseFiles = @($AppExe, $PublishedInstaller, $PortableZip)
$hashRows = foreach ($file in $releaseFiles) {
    $hash = Get-FileHash -LiteralPath $file -Algorithm SHA256
    "$($hash.Hash) *$((Get-CompatibleRelativePath $ReleaseRoot $file).Replace('\', '/'))"
}
Set-Content -LiteralPath $HashManifest -Value $hashRows -Encoding ascii

$defenderScanStatus = "NotRun"
$defenderScanReport = $null
if ($RunDefenderScan) {
    & $DefenderScanScript `
        -Architecture $Architecture `
        -Version $Version `
        -BuildKind $buildKind `
        -ReleaseRoot $ReleaseRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Microsoft Defender release scan failed."
    }
    $defenderScanStatus = "Passed"
    $defenderScanReport = (
        "DEFENDER-SCAN-$($Architecture.ToUpperInvariant())-$buildKind.txt"
    )
}

$pythonVersion = (& $PythonPath --version 2>&1 | Out-String).Trim()
$signer = if ($isSigned) {
    (Get-AuthenticodeSignature -LiteralPath $PublishedInstaller).SignerCertificate
}
else {
    $null
}
$manifestFiles = foreach ($file in $releaseFiles) {
    [pscustomobject]@{
        Path = (Get-CompatibleRelativePath $ReleaseRoot $file).Replace('\', '/')
        Size = (Get-Item -LiteralPath $file).Length
        SHA256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    }
}
$peComponents = foreach ($file in $applicationPeFiles) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    [pscustomobject]@{
        Path = (Get-CompatibleRelativePath $AppDir $file.FullName).Replace('\', '/')
        Size = (Get-Item -LiteralPath $file.FullName).Length
        SHA256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        SignatureStatus = $signature.Status.ToString()
        SignerSubject = if ($signature.SignerCertificate) {
            $signature.SignerCertificate.Subject
        }
        else {
            $null
        }
    }
}
[pscustomobject]@{
    Product = $ProductName
    Version = $Version
    Architecture = "win-$Architecture"
    BuildKind = $buildKind
    BuiltAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    Python = $pythonVersion
    Packages = $actualPackages
    PyInstallerMode = "onedir"
    UPX = $false
    GmailApi = $true
    MicrosoftOAuthConfigured = -not [string]::IsNullOrWhiteSpace(
        [string]$bundledOAuthConfig.microsoft.client_id
    )
    SignerSubject = if ($signer) { $signer.Subject } else { $null }
    SignerThumbprint = if ($signer) { $signer.Thumbprint } else { $null }
    TimestampServer = if ($isSigned) { $TimestampServer } else { $null }
    InstallerCompression = if ($isSigned) { "lzma-solid" } else { "zip-nonsolid" }
    UpdateInstallerLaunch = "interactive"
    UpdateStorage = "LocalAppData"
    DefenderScan = $defenderScanStatus
    DefenderScanReport = $defenderScanReport
    Files = $manifestFiles
    PeComponents = $peComponents
} | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath $BuildManifest -Encoding utf8

Write-Output "$buildKind $Architecture release complete."
Write-Output "Installer: $PublishedInstaller"
Write-Output "Portable ZIP: $PortableZip"
Write-Output "SHA-256 manifest: $HashManifest"
