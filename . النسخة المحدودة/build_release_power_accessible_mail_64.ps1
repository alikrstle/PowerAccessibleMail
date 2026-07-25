param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root.Path ".venv\Scripts\python.exe"
}

& (Join-Path $Root.Path "build_release_power_accessible_mail_gmail_api_limited_64.ps1") `
    -PythonPath $PythonPath
exit $LASTEXITCODE
