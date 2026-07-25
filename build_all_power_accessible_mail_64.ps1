param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    & .\build_power_accessible_mail_64.ps1 -PythonPath $PythonPath
    if ($LASTEXITCODE -ne 0) {
        throw "Full build failed with exit code $LASTEXITCODE"
    }

    & .\build_power_accessible_mail_gmail_api_limited_64.ps1 -PythonPath $PythonPath
    if ($LASTEXITCODE -ne 0) {
        throw "Gmail API limited build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Output "Both builds completed from the shared root source."
