param(
    [string]$PythonX64Path = ".\.venv\Scripts\python.exe",
    [string]$PythonX86Path = ".\.venv-x86\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$LockFile = Join-Path $ProjectRoot "requirements-release.lock"

function Invoke-ArchitectureTests {
    param(
        [string]$Architecture,
        [int]$ExpectedBits,
        [string]$PythonPath
    )

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        throw "$Architecture Python was not found: $PythonPath"
    }

    $probe = & $PythonPath -c @"
import json
from pathlib import Path
import struct
import sys
import pefile
import PyInstaller
bootloader_folder = (
    'Windows-64bit-intel'
    if struct.calcsize('P') * 8 == 64
    else 'Windows-32bit-intel'
)
bootloader_path = (
    Path(PyInstaller.__file__).resolve().parent
    / 'bootloader'
    / bootloader_folder
    / 'runw.exe'
)
bootloader = pefile.PE(str(bootloader_path), fast_load=True)
print(json.dumps({
    'bits': struct.calcsize('P') * 8,
    'bootloader_machine': bootloader.FILE_HEADER.Machine,
    'bootloader_path': str(bootloader_path),
    'executable': sys.executable,
    'version': sys.version.split()[0],
}))
"@
    if ($LASTEXITCODE -ne 0 -or -not $probe) {
        throw (
            "$Architecture virtual environment did not start correctly. " +
            "Rebuild it with the matching base Python using: " +
            "python.exe -m venv --upgrade <environment>"
        )
    }

    try {
        $runtime = $probe | ConvertFrom-Json
    }
    catch {
        throw "$Architecture Python returned an invalid runtime probe: $probe"
    }
    if ([int]$runtime.bits -ne $ExpectedBits) {
        throw "$Architecture requires $ExpectedBits-bit Python, but found $($runtime.bits)-bit."
    }
    $expectedMachine = if ($Architecture -eq "x64") { 0x8664 } else { 0x014C }
    if ([int]$runtime.bootloader_machine -ne $expectedMachine) {
        throw (
            "$Architecture PyInstaller bootloader has the wrong PE machine " +
            "at $($runtime.bootloader_path). Force-reinstall PyInstaller " +
            "with this environment before building."
        )
    }

    $expectedPackages = Get-Content -LiteralPath $LockFile |
        Where-Object { $_ -and -not $_.StartsWith("#") } |
        Sort-Object
    $actualPackages = & $PythonPath -m pip freeze |
        Where-Object { $_ -and -not $_.StartsWith("#") } |
        Sort-Object
    if ($LASTEXITCODE -ne 0) {
        throw "$Architecture could not list installed packages."
    }
    $packageDifference = Compare-Object $expectedPackages $actualPackages
    if ($packageDifference) {
        throw (
            "$Architecture environment does not match requirements-release.lock.`n" +
            ($packageDifference | Out-String)
        )
    }

    & $PythonPath -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "$Architecture dependency check failed."
    }
    & $PythonPath -m compileall -q `
        (Join-Path $ProjectRoot "accessible_mail") `
        (Join-Path $ProjectRoot "tests")
    if ($LASTEXITCODE -ne 0) {
        throw "$Architecture compilation check failed."
    }
    & $PythonPath -m unittest discover -s (Join-Path $ProjectRoot "tests") -q
    if ($LASTEXITCODE -ne 0) {
        throw "$Architecture tests failed."
    }

    Write-Output (
        "$Architecture passed with Python $($runtime.version) " +
        "($($runtime.bits)-bit) at $($runtime.executable)"
    )
}

Push-Location $ProjectRoot
try {
    Invoke-ArchitectureTests "x64" 64 $PythonX64Path
    Invoke-ArchitectureTests "x86" 32 $PythonX86Path
}
finally {
    Pop-Location
}

Write-Output "Both architectures passed from the unified source tree."
