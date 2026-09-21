param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

& (Join-Path $PSScriptRoot "build_power_accessible_mail_x64.ps1") `
    -PythonPath $PythonPath
exit $LASTEXITCODE
