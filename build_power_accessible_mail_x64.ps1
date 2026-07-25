param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

& (Join-Path $PSScriptRoot "build_power_accessible_mail.ps1") `
    -Architecture x64 `
    -PythonPath $PythonPath
exit $LASTEXITCODE
