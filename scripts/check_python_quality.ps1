$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python virtual environment was not found at $pythonPath"
}

& $pythonPath -m ruff check --no-cache --select E4,E7,E9,F,B accessible_mail tests
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$testProfileRoot = Join-Path $env:TEMP "power-accessible-mail-quality-tests"
$env:APPDATA = Join-Path $testProfileRoot "Roaming"
$env:LOCALAPPDATA = Join-Path $testProfileRoot "Local"
& $pythonPath -m unittest discover -s tests
exit $LASTEXITCODE
