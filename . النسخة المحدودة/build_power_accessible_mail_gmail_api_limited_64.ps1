param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root.Path ".venv\Scripts\python.exe"
}

& (Join-Path $Root.Path "build_power_accessible_mail_gmail_api_limited_64.ps1") -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

foreach ($name in @("build-gmail-api-limited", "dist-gmail-api-limited", "release")) {
    $legacyPath = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $legacyPath) {
        Remove-Item -LiteralPath $legacyPath -Recurse -Force
    }
}

Write-Output "Canonical release: $(Join-Path $Root.Path 'release\win-x64-gmail-api-limited')"
