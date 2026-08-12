param(
    [string]$PythonPath = ".\.venv-x86\Scripts\python.exe",
    [string]$CertificateThumbprint = $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampServer = $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER,
    [switch]$AllowUnsigned,
    [switch]$RunDefenderScan,
    [string]$InnoCompiler = "C:\Users\alikrstl\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

$arguments = @{
    Architecture = "x86"
    PythonPath = $PythonPath
    CertificateThumbprint = $CertificateThumbprint
    InnoCompiler = $InnoCompiler
}
if ($TimestampServer) {
    $arguments.TimestampServer = $TimestampServer
}
if ($AllowUnsigned) {
    $arguments.AllowUnsigned = $true
}
if ($RunDefenderScan) {
    $arguments.RunDefenderScan = $true
}
& (Join-Path $PSScriptRoot "build_release_power_accessible_mail.ps1") @arguments
exit $LASTEXITCODE
