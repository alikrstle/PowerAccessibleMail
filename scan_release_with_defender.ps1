param(
    [ValidateSet("x64", "x86")]
    [string]$Architecture = "x64",
    [string]$Version = "1.2.14",
    [ValidateSet("SIGNED", "UNSIGNED")]
    [string]$BuildKind = "UNSIGNED",
    [string]$ReleaseRoot = (Join-Path $PSScriptRoot "release"),
    [switch]$SkipSignatureUpdate
)

$ErrorActionPreference = "Stop"
$AppName = "Power Accessible Mail"
$suffix = if ($BuildKind -eq "SIGNED") { "" } else { "-UNSIGNED" }
$appDirectory = Join-Path $ReleaseRoot "win-$Architecture\$AppName"
$installer = Join-Path $ReleaseRoot (
    "PowerAccessibleMailSetup-$Version-win-$Architecture$suffix.exe"
)
$portableZip = Join-Path $ReleaseRoot (
    "PowerAccessibleMail-$Version-win-$Architecture$suffix.zip"
)
$report = Join-Path $ReleaseRoot (
    "DEFENDER-SCAN-$($Architecture.ToUpperInvariant())-$BuildKind.txt"
)

function Get-MpCmdRunPath {
    $platformRoot = Join-Path $env:ProgramData "Microsoft\Windows Defender\Platform"
    if (Test-Path -LiteralPath $platformRoot) {
        $candidate = Get-ChildItem -LiteralPath $platformRoot -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "MpCmdRun.exe" } |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if ($candidate) {
            return $candidate
        }
    }

    $fallback = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }
    throw "MpCmdRun.exe was not found on this Windows installation."
}

foreach ($target in @($appDirectory, $installer, $portableZip)) {
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Release scan target was not found: $target"
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$administrator = [Security.Principal.WindowsBuiltInRole]::Administrator
if (-not $principal.IsInRole($administrator)) {
    throw "Run this Defender release scan from an elevated PowerShell window."
}

$defenderStatus = Get-MpComputerStatus
if (-not $defenderStatus.AMServiceEnabled -or
    -not $defenderStatus.AntivirusEnabled) {
    throw "Microsoft Defender Antivirus is not enabled on this computer."
}

$mpCmdRun = Get-MpCmdRunPath
$reportLines = @(
    "Power Accessible Mail Microsoft Defender release scan",
    "Version: $Version",
    "Architecture: $Architecture",
    "Build kind: $BuildKind",
    "Scanned at UTC: $((Get-Date).ToUniversalTime().ToString('o'))",
    "Defender engine: $($defenderStatus.AMEngineVersion)",
    "Defender antivirus signature: $($defenderStatus.AntivirusSignatureVersion)",
    "MpCmdRun: $mpCmdRun",
    "Remediation: disabled for this verification scan",
    ""
)

if (-not $SkipSignatureUpdate) {
    $signatureOutput = (& $mpCmdRun -SignatureUpdate 2>&1 | Out-String).Trim()
    $signatureExitCode = $LASTEXITCODE
    $reportLines += @(
        "Signature update exit code: $signatureExitCode",
        $signatureOutput,
        ""
    )
    $reportLines | Set-Content -LiteralPath $report -Encoding utf8
    if ($signatureExitCode -ne 0) {
        throw "Defender security intelligence update failed. See $report"
    }
    $defenderStatus = Get-MpComputerStatus
    $reportLines += @(
        "Defender antivirus signature after update: $($defenderStatus.AntivirusSignatureVersion)",
        ""
    )
    $reportLines | Set-Content -LiteralPath $report -Encoding utf8
}

$scanFailed = $false
foreach ($target in @($appDirectory, $installer, $portableZip)) {
    $scanOutput = (
        & $mpCmdRun `
            -Scan `
            -ScanType 3 `
            -File $target `
            -DisableRemediation 2>&1 |
            Out-String
    ).Trim()
    $scanExitCode = $LASTEXITCODE
    $reportLines += @(
        "Target: $target",
        "Exit code: $scanExitCode",
        $scanOutput,
        ""
    )
    $reportLines | Set-Content -LiteralPath $report -Encoding utf8
    if ($scanExitCode -ne 0) {
        $scanFailed = $true
    }
}

if ($scanFailed) {
    throw "Microsoft Defender reported a detection or scan error. See $report"
}

Write-Output "Microsoft Defender release scan passed: $report"
