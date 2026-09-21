param(
    [string]$PythonX64Path = ".\.venv\Scripts\python.exe",
    [string]$PythonX86Path = ".\.venv-x86\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    & .\build_power_accessible_mail_x64.ps1 -PythonPath $PythonX64Path
    if ($LASTEXITCODE -ne 0) {
        throw "x64 build failed with exit code $LASTEXITCODE"
    }

    & .\build_power_accessible_mail_x86.ps1 -PythonPath $PythonX86Path
    if ($LASTEXITCODE -ne 0) {
        throw "x86 build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Output "Both architecture builds completed from the unified root source."
