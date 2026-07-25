param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "build_power_accessible_mail_gmail_api_limited_64.ps1") -PythonPath $PythonPath
exit $LASTEXITCODE
