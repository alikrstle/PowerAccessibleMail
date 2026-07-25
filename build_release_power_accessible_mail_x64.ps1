param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$CertificateThumbprint = $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampServer = $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER,
    [string]$InnoCompiler = "C:\Users\alikrstl\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

$arguments = @{
    Architecture = "x64"
    PythonPath = $PythonPath
    CertificateThumbprint = $CertificateThumbprint
    InnoCompiler = $InnoCompiler
}
if ($TimestampServer) {
    $arguments.TimestampServer = $TimestampServer
}
& (Join-Path $PSScriptRoot "build_release_power_accessible_mail.ps1") @arguments
exit $LASTEXITCODE
