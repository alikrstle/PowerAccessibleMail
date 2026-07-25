param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$CertificateThumbprint = $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampServer = $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER,
    [string]$InnoCompiler = "C:\Users\alikrstl\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

& (Join-Path $PSScriptRoot "build_release_power_accessible_mail_x64.ps1") `
    -PythonPath $PythonPath `
    -CertificateThumbprint $CertificateThumbprint `
    -TimestampServer $TimestampServer `
    -InnoCompiler $InnoCompiler
exit $LASTEXITCODE
