[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$ManifestPath,
    [string[]]$AllowedPublisher = @(),
    [string[]]$AllowedPublisherThumbprint = @(),
    [switch]$AllowUnsignedDevelopment,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $repoRoot 'packaging/windows/ReleaseTools.psm1'
Import-Module $modulePath -Force

try {
    $manifestFullPath = [IO.Path]::GetFullPath($ManifestPath)
    $publishDirectory = Split-Path -Parent $manifestFullPath
    $signaturePath = Join-Path $publishDirectory 'release-manifest.p7s'
    $manifest = Get-Content -LiteralPath $manifestFullPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $allowUnsigned = $AllowUnsignedDevelopment -and $manifest.release_mode -eq 'unsigned-development'

    $manifestSignature = Get-DetachedCmsSignatureInfo `
        -ManifestPath $manifestFullPath `
        -SignaturePath $signaturePath
    $integrityIssues = @(Get-ReleaseArtifactIntegrityIssues `
        -PublishDirectory $publishDirectory `
        -Manifest $manifest `
        -ManifestPath $manifestFullPath `
        -SignaturePath $signaturePath)
    $authenticode = @(Get-ManifestAuthenticodeSignatures `
        -PublishDirectory $publishDirectory `
        -Manifest $manifest)
    $decision = Get-ReleaseVerificationDecision `
        -ManifestSignature $manifestSignature `
        -IntegrityIssues $integrityIssues `
        -AuthenticodeSignatures $authenticode `
        -AllowedPublisher $AllowedPublisher `
        -AllowedPublisherThumbprint $AllowedPublisherThumbprint `
        -AllowUnsignedDevelopment:$allowUnsigned
} catch {
    $decision = [pscustomobject]@{
        Success = $false
        Code = 'INSTALLER_HASH_INVALID'
        Message = 'The release manifest or artifact set could not be parsed and verified.'
        Details = @($_.Exception.Message)
    }
}

if ($Json) {
    $decision | ConvertTo-Json -Depth 5
} else {
    $prefix = if ($decision.Success) { 'OK' } else { 'BLOCKED' }
    Write-Output "[$prefix][$($decision.Code)] $($decision.Message)"
    foreach ($detail in @($decision.Details)) {
        Write-Output "  $detail"
    }
}

if ($decision.Success) {
    exit 0
}
switch ($decision.Code) {
    'INSTALLER_PUBLISHER_SIGNATURE_INVALID' { exit 21 }
    'INSTALLER_HASH_INVALID' { exit 22 }
    'INSTALLER_WINDOWS_CODE_SIGNATURE_INVALID' { exit 23 }
    default { exit 99 }
}
