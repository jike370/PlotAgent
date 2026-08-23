Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$modulePath = Join-Path $repoRoot 'packaging/windows/ReleaseTools.psm1'
Import-Module $modulePath -Force

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) {
        throw "ASSERT EQUAL FAILED: $Message. Expected '$Expected', got '$Actual'."
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw "ASSERT TRUE FAILED: $Message"
    }
}

$allowedSubject = 'CN=PlotAgent Test Publisher, O=PlotAgent'
$allowedThumbprint = 'AABBCCDD'
$validPublisher = [pscustomobject]@{
    Status = 'Valid'
    Subject = $allowedSubject
    Thumbprint = $allowedThumbprint
}
$validAuthenticode = [pscustomobject]@{
    Path = 'PlotAgent-0.1.0-x64-setup.exe'
    Status = 'Valid'
    Subject = $allowedSubject
    Thumbprint = $allowedThumbprint
}

$unsignedManifest = [pscustomobject]@{ Status = 'NotSigned'; Subject = ''; Thumbprint = '' }
$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $unsignedManifest `
    -IntegrityIssues @() `
    -AuthenticodeSignatures @() `
    -AllowedPublisher @($allowedSubject)
Assert-Equal $decision.Code 'INSTALLER_PUBLISHER_SIGNATURE_INVALID' 'unsigned manifest is blocked'

$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $validPublisher `
    -IntegrityIssues @('SHA-256 mismatch: installer.exe') `
    -AuthenticodeSignatures @($validAuthenticode) `
    -AllowedPublisher @($allowedSubject)
Assert-Equal $decision.Code 'INSTALLER_HASH_INVALID' 'tampered artifact is blocked by hash'

$wrongPublisher = [pscustomobject]@{
    Status = 'Valid'
    Subject = 'CN=Wrong Publisher'
    Thumbprint = '00112233'
}
$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $wrongPublisher `
    -IntegrityIssues @() `
    -AuthenticodeSignatures @($validAuthenticode) `
    -AllowedPublisher @($allowedSubject)
Assert-Equal $decision.Code 'INSTALLER_PUBLISHER_SIGNATURE_INVALID' 'wrong publisher is blocked'

$unsignedAuthenticode = [pscustomobject]@{
    Path = 'installer.exe'
    Status = 'NotSigned'
    Subject = ''
    Thumbprint = ''
}
$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $validPublisher `
    -IntegrityIssues @() `
    -AuthenticodeSignatures @($unsignedAuthenticode) `
    -AllowedPublisher @($allowedSubject)
Assert-Equal $decision.Code 'INSTALLER_WINDOWS_CODE_SIGNATURE_INVALID' 'unsigned executable is blocked'

$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $unsignedManifest `
    -IntegrityIssues @() `
    -AuthenticodeSignatures @($unsignedAuthenticode) `
    -AllowUnsignedDevelopment
Assert-True $decision.Success 'unsigned development requires an explicit verifier override'
Assert-Equal $decision.Code 'UNSIGNED_DEVELOPMENT_VERIFIED' 'unsigned override never claims a signed release'

$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $validPublisher `
    -IntegrityIssues @() `
    -AuthenticodeSignatures @([pscustomobject]@{
        Path = 'installer.exe'
        Status = 'Valid'
        Subject = 'CN=Wrong Publisher'
        Thumbprint = '00112233'
    }) `
    -AllowedPublisher @($allowedSubject)
Assert-Equal $decision.Code 'INSTALLER_PUBLISHER_SIGNATURE_INVALID' `
    'wrong Authenticode publisher is blocked even when the manifest signer is allowed'

$decision = Get-ReleaseVerificationDecision `
    -ManifestSignature $validPublisher `
    -IntegrityIssues @() `
    -AuthenticodeSignatures @($validAuthenticode) `
    -AllowedPublisherThumbprint @($allowedThumbprint)
Assert-True $decision.Success 'valid signature, hash state, Authenticode, and thumbprint pass'

$packageJson = Get-Content -LiteralPath (Join-Path $repoRoot 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$configurationIssues = @(Get-ElectronBuilderConfigurationIssues -PackageJson $packageJson)
Assert-Equal $configurationIssues.Count 0 'electron-builder allowlists only compiled output and sidecar resources'
$windowsPowerShell = Get-WindowsPowerShellExecutable
Assert-True (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf) `
    'release verification resolves Windows PowerShell independently of the current PSHOME'

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("plotagent-release-test-" + [guid]::NewGuid().ToString('N'))
$publishRoot = Join-Path $testRoot 'publish'
try {
    New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null
    $artifactPath = Join-Path $publishRoot 'PlotAgent-test-artifact.bin'
    [IO.File]::WriteAllBytes($artifactPath, [byte[]](1, 2, 3, 4))
    $manifestPath = Join-Path $publishRoot 'release-manifest.json'
    $signaturePath = Join-Path $publishRoot 'release-manifest.p7s'
    $manifest = New-ReleaseManifest `
        -PublishDirectory $publishRoot `
        -ArtifactPaths @($artifactPath) `
        -Version '0.0.0-test' `
        -GitCommit ('0' * 40) `
        -SourceDirty $false `
        -ReleaseMode 'unsigned-development' `
        -OutputPath $manifestPath

    $issues = @(Get-ReleaseArtifactIntegrityIssues `
        -PublishDirectory $publishRoot `
        -Manifest $manifest `
        -ManifestPath $manifestPath `
        -SignaturePath $signaturePath)
    Assert-Equal $issues.Count 0 'fresh manifest has an exact artifact set and matching hash'

    $verifierPath = Join-Path $repoRoot 'scripts/verify-windows-release.ps1'
    $strictOutput = & $windowsPowerShell `
        -NoProfile -ExecutionPolicy Bypass -File $verifierPath `
        -ManifestPath $manifestPath
    Assert-Equal $LASTEXITCODE 21 'strict verifier blocks unsigned development output'
    Assert-True (@($strictOutput -match 'INSTALLER_PUBLISHER_SIGNATURE_INVALID').Count -gt 0) `
        'strict verifier emits the stable unsigned failure'

    $developmentOutput = & $windowsPowerShell `
        -NoProfile -ExecutionPolicy Bypass -File $verifierPath `
        -ManifestPath $manifestPath -AllowUnsignedDevelopment
    Assert-Equal $LASTEXITCODE 0 'explicit development override verifies hashes without claiming signatures'
    Assert-True (@($developmentOutput -match 'UNSIGNED_DEVELOPMENT_VERIFIED').Count -gt 0) `
        'development verification is clearly labelled unsigned'

    [IO.File]::WriteAllBytes($artifactPath, [byte[]](1, 2, 3, 5))
    $issues = @(Get-ReleaseArtifactIntegrityIssues `
        -PublishDirectory $publishRoot `
        -Manifest $manifest `
        -ManifestPath $manifestPath `
        -SignaturePath $signaturePath)
    Assert-True (@($issues -match 'SHA-256 mismatch').Count -gt 0) 'tampering is detected'

    [IO.File]::WriteAllBytes($artifactPath, [byte[]](1, 2, 3, 4))
    [IO.File]::WriteAllText((Join-Path $publishRoot 'extra.txt'), 'extra')
    $issues = @(Get-ReleaseArtifactIntegrityIssues `
        -PublishDirectory $publishRoot `
        -Manifest $manifest `
        -ManifestPath $manifestPath `
        -SignaturePath $signaturePath)
    Assert-True (@($issues -match 'extra artifact').Count -gt 0) 'extra files are detected'

    Remove-Item -LiteralPath (Join-Path $publishRoot 'extra.txt')
    Remove-Item -LiteralPath $artifactPath
    $issues = @(Get-ReleaseArtifactIntegrityIssues `
        -PublishDirectory $publishRoot `
        -Manifest $manifest `
        -ManifestPath $manifestPath `
        -SignaturePath $signaturePath)
    Assert-True (@($issues -match 'missing artifact').Count -gt 0) 'missing files are detected'
} finally {
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTestRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTestRoot).StartsWith('plotagent-release-test-')) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$dryRunOutput = & (Join-Path $repoRoot 'scripts/release-windows.ps1') -DryRun
Assert-True (@($dryRunOutput -match 'DRY-RUN').Count -gt 0) 'release entry dry-run performs no build or cleanup'

Write-Output 'windows-release-tools.test.ps1: PASS'
