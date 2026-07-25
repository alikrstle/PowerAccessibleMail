param(
    [string]$PythonPath = ".\.venv-x86\Scripts\python.exe"
)

& (Join-Path $PSScriptRoot "build_power_accessible_mail.ps1") `
    -Architecture x86 `
    -PythonPath $PythonPath
exit $LASTEXITCODE
