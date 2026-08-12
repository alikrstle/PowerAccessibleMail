$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$candidates = @(
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv-codex\Scripts\python.exe")
)

$pathPython = Get-Command python -ErrorAction SilentlyContinue
if ($pathPython) {
    $candidates += $pathPython.Source
}

$selectedPython = $null
foreach ($candidate in $candidates | Select-Object -Unique) {
    if (-not (Test-Path -LiteralPath $candidate)) {
        continue
    }
    & $candidate -c "import wx" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $selectedPython = $candidate
        break
    }
}

if (-not $selectedPython) {
    throw (
        "No working Python environment with wxPython was found. " +
        "Run install.bat, then try again."
    )
}

Push-Location $ProjectRoot
try {
    & $selectedPython (Join-Path $ProjectRoot "main.py")
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
