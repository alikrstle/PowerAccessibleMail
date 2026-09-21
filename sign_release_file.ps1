param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath,
    [string]$CertificateThumbprint = $env:POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT,
    [string]$TimestampServer = $(
        if ($env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER) {
            $env:POWER_ACCESSIBLE_MAIL_TIMESTAMP_SERVER
        }
        else {
            "https://timestamp.digicert.com"
        }
    )
)

$ErrorActionPreference = "Stop"

function Find-CodeSigningCertificate {
    param([string]$Thumbprint)

    $normalized = ($Thumbprint -replace "\s", "").ToUpperInvariant()
    if (-not $normalized) {
        throw "POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT is required."
    }

    foreach ($store in @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")) {
        $certificate = Get-ChildItem -LiteralPath $store -ErrorAction SilentlyContinue |
            Where-Object { ($_.Thumbprint -replace "\s", "").ToUpperInvariant() -eq $normalized } |
            Select-Object -First 1
        if ($certificate) {
            return $certificate
        }
    }
    throw "The requested code-signing certificate was not found in CurrentUser or LocalMachine."
}

$resolvedFile = (Resolve-Path -LiteralPath $FilePath).Path
$certificate = Find-CodeSigningCertificate -Thumbprint $CertificateThumbprint
$codeSigningOid = "1.3.6.1.5.5.7.3.3"

if (-not $certificate.HasPrivateKey) {
    throw "The code-signing certificate does not have an accessible private key."
}
if ($certificate.NotBefore -gt (Get-Date) -or $certificate.NotAfter -le (Get-Date)) {
    throw "The code-signing certificate is not currently valid."
}
if ($certificate.EnhancedKeyUsageList.ObjectId.Value -notcontains $codeSigningOid) {
    throw "The selected certificate is not valid for code signing."
}

$signature = Set-AuthenticodeSignature `
    -LiteralPath $resolvedFile `
    -Certificate $certificate `
    -HashAlgorithm SHA256 `
    -TimestampServer $TimestampServer `
    -IncludeChain All

if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Authenticode signing failed: $($signature.StatusMessage)"
}
if (-not $signature.TimeStamperCertificate) {
    throw "The signature is valid but no trusted timestamp was attached."
}

[pscustomobject]@{
    File = $resolvedFile
    Status = $signature.Status.ToString()
    Signer = $signature.SignerCertificate.Subject
    SignerThumbprint = $signature.SignerCertificate.Thumbprint
    TimestampAuthority = $signature.TimeStamperCertificate.Subject
    SHA256 = (Get-FileHash -LiteralPath $resolvedFile -Algorithm SHA256).Hash
} | ConvertTo-Json -Compress
