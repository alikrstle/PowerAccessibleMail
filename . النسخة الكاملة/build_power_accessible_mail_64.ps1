param([string]$PythonPath = "")

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root ".venv\Scripts\python.exe"
}

& (Join-Path $Root "build_power_accessible_mail_64.ps1") -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

foreach ($name in @("build", "dist", "release")) {
    $legacyPath = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $legacyPath) {
        Remove-Item -LiteralPath $legacyPath -Recurse -Force
    }
}

Write-Output "Canonical release: $(Join-Path $Root 'release\win-x64')"
