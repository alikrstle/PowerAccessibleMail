$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python virtual environment was not found at $pythonPath"
}

& $pythonPath -m ruff check --no-cache --select E4,E7,E9,F,B `
    (Join-Path $projectRoot "accessible_mail") (Join-Path $projectRoot "tests")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$testProfileRoot = Join-Path $env:TEMP ("power-accessible-mail-quality-tests-" + [guid]::NewGuid().ToString('N'))
$previousAppData = $env:APPDATA
$previousLocalAppData = $env:LOCALAPPDATA
$env:APPDATA = Join-Path $testProfileRoot "Roaming"
$env:LOCALAPPDATA = Join-Path $testProfileRoot "Local"
Push-Location $projectRoot
try {
    & $pythonPath -m unittest discover -s tests
    $qualityExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
    $env:APPDATA = $previousAppData
    $env:LOCALAPPDATA = $previousLocalAppData
}
exit $qualityExitCode
