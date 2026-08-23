Set-StrictMode -Version Latest

$script:PublisherError = 'INSTALLER_PUBLISHER_SIGNATURE_INVALID'
$script:HashError = 'INSTALLER_HASH_INVALID'
$script:AuthenticodeError = 'INSTALLER_WINDOWS_CODE_SIGNATURE_INVALID'

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $stream = [System.IO.File]::OpenRead($LiteralPath)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $algorithm.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function New-VerificationResult {
    param(
        [Parameter(Mandatory = $true)][bool]$Success,
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message,
        [string[]]$Details = @()
    )

    [pscustomobject]@{
        Success = $Success
        Code = $Code
        Message = $Message
        Details = @($Details)
    }
}

function Test-PublisherAllowed {
    param(
        [AllowNull()][string]$Subject,
        [AllowNull()][string]$Thumbprint,
        [string[]]$AllowedPublisher = @(),
        [string[]]$AllowedPublisherThumbprint = @()
    )

    foreach ($allowed in $AllowedPublisher) {
        if (-not [string]::IsNullOrWhiteSpace($Subject) -and
            [string]::Equals($Subject.Trim(), $allowed.Trim(), [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    $normalizedThumbprint = if ($null -eq $Thumbprint) { '' } else { $Thumbprint.Replace(' ', '') }
    foreach ($allowed in $AllowedPublisherThumbprint) {
        if (-not [string]::IsNullOrWhiteSpace($normalizedThumbprint) -and
            [string]::Equals(
                $normalizedThumbprint,
                $allowed.Replace(' ', ''),
                [StringComparison]::OrdinalIgnoreCase
            )) {
            return $true
        }
    }
    return $false
}

function Get-ReleaseVerificationDecision {
    param(
        [Parameter(Mandatory = $true)]$ManifestSignature,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$IntegrityIssues,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$AuthenticodeSignatures,
        [string[]]$AllowedPublisher = @(),
        [string[]]$AllowedPublisherThumbprint = @(),
        [switch]$AllowUnsignedDevelopment
    )

    $manifestUnsignedAllowed = $AllowUnsignedDevelopment -and $ManifestSignature.Status -eq 'NotSigned'
    if ($ManifestSignature.Status -ne 'Valid' -and -not $manifestUnsignedAllowed) {
        return New-VerificationResult -Success $false -Code $script:PublisherError `
            -Message 'The detached release manifest signature is missing or invalid.' `
            -Details @([string]$ManifestSignature.Status)
    }
    if ($ManifestSignature.Status -eq 'Valid' -and -not (Test-PublisherAllowed `
            -Subject $ManifestSignature.Subject `
            -Thumbprint $ManifestSignature.Thumbprint `
            -AllowedPublisher $AllowedPublisher `
            -AllowedPublisherThumbprint $AllowedPublisherThumbprint)) {
        return New-VerificationResult -Success $false -Code $script:PublisherError `
            -Message 'The release manifest signer is not in the publisher allowlist.' `
            -Details @([string]$ManifestSignature.Subject, [string]$ManifestSignature.Thumbprint)
    }

    if ($IntegrityIssues.Count -gt 0) {
        return New-VerificationResult -Success $false -Code $script:HashError `
            -Message 'The release artifact set or a SHA-256 digest does not match the manifest.' `
            -Details @($IntegrityIssues | ForEach-Object { [string]$_ })
    }

    foreach ($signature in $AuthenticodeSignatures) {
        $authenticodeUnsignedAllowed = $AllowUnsignedDevelopment -and $signature.Status -eq 'NotSigned'
        if ($signature.Status -ne 'Valid' -and -not $authenticodeUnsignedAllowed) {
            return New-VerificationResult -Success $false -Code $script:AuthenticodeError `
                -Message 'A Windows executable has a missing or invalid Authenticode signature.' `
                -Details @([string]$signature.Path, [string]$signature.Status)
        }
        if ($signature.Status -eq 'Valid' -and -not (Test-PublisherAllowed `
                -Subject $signature.Subject `
                -Thumbprint $signature.Thumbprint `
                -AllowedPublisher $AllowedPublisher `
                -AllowedPublisherThumbprint $AllowedPublisherThumbprint)) {
            return New-VerificationResult -Success $false -Code $script:PublisherError `
                -Message 'A Windows executable signer is not in the publisher allowlist.' `
                -Details @([string]$signature.Path, [string]$signature.Subject, [string]$signature.Thumbprint)
        }
    }

    $successCode = if ($AllowUnsignedDevelopment) {
        'UNSIGNED_DEVELOPMENT_VERIFIED'
    } else {
        'INSTALLER_VERIFIED'
    }
    $successMessage = if ($AllowUnsignedDevelopment) {
        'Hashes were verified, but this is explicitly an unsigned development release.'
    } else {
        'Manifest signature, artifact hashes, Authenticode, and publisher allowlist are valid.'
    }
    return New-VerificationResult -Success $true -Code $successCode -Message $successMessage
}

function ConvertTo-SafeRelativeReleasePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $pathFull = [IO.Path]::GetFullPath($Path)
    $rootPrefix = $rootFull + [IO.Path]::DirectorySeparatorChar
    if (-not $pathFull.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the release root: $Path"
    }
    return $pathFull.Substring($rootPrefix.Length).Replace('\', '/')
}

function Test-SafeManifestRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or [IO.Path]::IsPathRooted($Path)) {
        return $false
    }
    $normalized = $Path.Replace('\', '/')
    if ($normalized.StartsWith('/') -or $normalized.EndsWith('/')) {
        return $false
    }
    foreach ($segment in $normalized.Split('/')) {
        if ([string]::IsNullOrWhiteSpace($segment) -or $segment -eq '.' -or $segment -eq '..') {
            return $false
        }
    }
    return $true
}

function New-ReleaseManifest {
    param(
        [Parameter(Mandatory = $true)][string]$PublishDirectory,
        [Parameter(Mandatory = $true)][string[]]$ArtifactPaths,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$GitCommit,
        [Parameter(Mandatory = $true)][bool]$SourceDirty,
        [Parameter(Mandatory = $true)][ValidateSet('signed', 'unsigned-development')][string]$ReleaseMode,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )

    $artifacts = @()
    foreach ($artifactPath in $ArtifactPaths) {
        $file = Get-Item -LiteralPath $artifactPath -ErrorAction Stop
        if ($file.PSIsContainer) {
            throw "Release artifact must be a file: $artifactPath"
        }
        $relativePath = ConvertTo-SafeRelativeReleasePath -Root $PublishDirectory -Path $file.FullName
        $artifacts += [pscustomobject]@{
            path = $relativePath
            size_bytes = [int64]$file.Length
            sha256 = Get-Sha256Hex -LiteralPath $file.FullName
            authenticode_required = $file.Extension -ieq '.exe'
        }
    }

    $manifest = [ordered]@{
        format_version = 1
        product = 'PlotAgent'
        version = $Version
        git_commit = $GitCommit
        source_dirty = $SourceDirty
        generated_at_utc = [DateTime]::UtcNow.ToString('o')
        platform = 'windows'
        architecture = 'x64'
        release_mode = $ReleaseMode
        core_implementation = 'bounded_rpc_runtime'
        artifacts = @($artifacts | Sort-Object path)
    }
    $json = $manifest | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText(
        [IO.Path]::GetFullPath($OutputPath),
        $json + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
    return [pscustomobject]$manifest
}

function Get-ReleaseArtifactIntegrityIssues {
    param(
        [Parameter(Mandatory = $true)][string]$PublishDirectory,
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$SignaturePath
    )

    $issues = [Collections.Generic.List[string]]::new()
    if ($Manifest.format_version -ne 1 -or $Manifest.product -ne 'PlotAgent') {
        $issues.Add('manifest: unsupported format or product')
        return @($issues)
    }

    $rootFull = [IO.Path]::GetFullPath($PublishDirectory).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $expected = @{}
    foreach ($artifact in @($Manifest.artifacts)) {
        $relativePath = [string]$artifact.path
        if (-not (Test-SafeManifestRelativePath -Path $relativePath)) {
            $issues.Add("unsafe manifest path: $relativePath")
            continue
        }
        if ($expected.ContainsKey($relativePath)) {
            $issues.Add("duplicate manifest path: $relativePath")
            continue
        }
        $expected[$relativePath] = $artifact
    }

    $ignored = @(
        ConvertTo-SafeRelativeReleasePath -Root $rootFull -Path $ManifestPath
    )
    if (Test-Path -LiteralPath $SignaturePath -PathType Leaf) {
        $ignored += ConvertTo-SafeRelativeReleasePath -Root $rootFull -Path $SignaturePath
    }

    $actual = @{}
    foreach ($file in Get-ChildItem -LiteralPath $rootFull -File -Recurse) {
        $relativePath = ConvertTo-SafeRelativeReleasePath -Root $rootFull -Path $file.FullName
        if ($ignored -contains $relativePath) {
            continue
        }
        $actual[$relativePath] = $file
    }

    foreach ($relativePath in $expected.Keys) {
        if (-not $actual.ContainsKey($relativePath)) {
            $issues.Add("missing artifact: $relativePath")
            continue
        }
        $artifact = $expected[$relativePath]
        $file = $actual[$relativePath]
        if ([int64]$artifact.size_bytes -ne [int64]$file.Length) {
            $issues.Add("size mismatch: $relativePath")
            continue
        }
        $actualHash = Get-Sha256Hex -LiteralPath $file.FullName
        if (-not [string]::Equals(
                $actualHash,
                [string]$artifact.sha256,
                [StringComparison]::OrdinalIgnoreCase
            )) {
            $issues.Add("SHA-256 mismatch: $relativePath")
        }
    }
    foreach ($relativePath in $actual.Keys) {
        if (-not $expected.ContainsKey($relativePath)) {
            $issues.Add("extra artifact: $relativePath")
        }
    }
    return @($issues | Sort-Object)
}

function Get-DetachedCmsSignatureInfo {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$SignaturePath
    )

    if (-not (Test-Path -LiteralPath $SignaturePath -PathType Leaf)) {
        return [pscustomobject]@{ Status = 'NotSigned'; Subject = ''; Thumbprint = '' }
    }
    try {
        Add-Type -AssemblyName System.Security -ErrorAction Stop
        $content = [Security.Cryptography.Pkcs.ContentInfo]::new(
            [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($ManifestPath))
        )
        $cms = [Security.Cryptography.Pkcs.SignedCms]::new($content, $true)
        $cms.Decode([IO.File]::ReadAllBytes([IO.Path]::GetFullPath($SignaturePath)))
        $cms.CheckSignature($true)
        if ($cms.SignerInfos.Count -ne 1 -or $null -eq $cms.SignerInfos[0].Certificate) {
            throw 'The manifest signature must contain exactly one signing certificate.'
        }
        $certificate = $cms.SignerInfos[0].Certificate
        $chain = [Security.Cryptography.X509Certificates.X509Chain]::new()
        try {
            $chain.ChainPolicy.RevocationMode = `
                [Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
            $chain.ChainPolicy.VerificationFlags = `
                [Security.Cryptography.X509Certificates.X509VerificationFlags]::NoFlag
            foreach ($embeddedCertificate in $cms.Certificates) {
                if ($embeddedCertificate.Thumbprint -ne $certificate.Thumbprint) {
                    [void]$chain.ChainPolicy.ExtraStore.Add($embeddedCertificate)
                }
            }
            if (-not $chain.Build($certificate)) {
                $chainErrors = @($chain.ChainStatus | ForEach-Object { $_.Status.ToString() })
                throw "The manifest signer chain is not trusted: $($chainErrors -join ', ')"
            }
        } finally {
            $chain.Dispose()
        }
        return [pscustomobject]@{
            Status = 'Valid'
            Subject = $certificate.Subject
            Thumbprint = $certificate.Thumbprint
        }
    } catch {
        return [pscustomobject]@{
            Status = 'Invalid'
            Subject = ''
            Thumbprint = ''
        }
    }
}

function New-DetachedCmsSignature {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$SignaturePath,
        [Parameter(Mandatory = $true)][Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )

    Add-Type -AssemblyName System.Security -ErrorAction Stop
    $content = [Security.Cryptography.Pkcs.ContentInfo]::new(
        [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($ManifestPath))
    )
    $cms = [Security.Cryptography.Pkcs.SignedCms]::new($content, $true)
    $signer = [Security.Cryptography.Pkcs.CmsSigner]::new(
        [Security.Cryptography.Pkcs.SubjectIdentifierType]::IssuerAndSerialNumber,
        $Certificate
    )
    $signer.IncludeOption = [Security.Cryptography.X509Certificates.X509IncludeOption]::WholeChain
    $signer.DigestAlgorithm = [Security.Cryptography.Oid]::new('2.16.840.1.101.3.4.2.1')
    $cms.ComputeSignature($signer)
    [IO.File]::WriteAllBytes([IO.Path]::GetFullPath($SignaturePath), $cms.Encode())
}

function Get-ManifestAuthenticodeSignatures {
    param(
        [Parameter(Mandatory = $true)][string]$PublishDirectory,
        [Parameter(Mandatory = $true)]$Manifest
    )

    $signatures = @()
    foreach ($artifact in @($Manifest.artifacts)) {
        if (-not [bool]$artifact.authenticode_required) {
            continue
        }
        $path = Join-Path $PublishDirectory ([string]$artifact.path).Replace('/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            continue
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        $signatures += [pscustomobject]@{
            Path = [string]$artifact.path
            Status = $signature.Status.ToString()
            Subject = if ($null -eq $signature.SignerCertificate) { '' } else { $signature.SignerCertificate.Subject }
            Thumbprint = if ($null -eq $signature.SignerCertificate) { '' } else { $signature.SignerCertificate.Thumbprint }
        }
    }
    return @($signatures)
}

function Get-ElectronBuilderConfigurationIssues {
    param([Parameter(Mandatory = $true)]$PackageJson)

    $issues = [Collections.Generic.List[string]]::new()
    if ($PackageJson.build.asar -ne $true) {
        $issues.Add('electron-builder asar must be enabled')
    }
    if ($PackageJson.build.directories.output -ne 'release/windows/electron') {
        $issues.Add('electron-builder output must stay under release/windows/electron')
    }
    if ($PackageJson.build.artifactName -ne 'PlotAgent-${version}-${arch}-setup.${ext}') {
        $issues.Add('electron-builder artifact name is not the fixed Windows release name')
    }
    $allowedFiles = @('out/**/*', 'package.json')
    foreach ($entry in @($PackageJson.build.files)) {
        if ($allowedFiles -notcontains [string]$entry) {
            $issues.Add("unexpected packaged file glob: $entry")
        }
    }
    foreach ($required in $allowedFiles) {
        if (@($PackageJson.build.files) -notcontains $required) {
            $issues.Add("missing packaged file glob: $required")
        }
    }
    $resources = @($PackageJson.build.extraResources)
    $expected = @{
        'release/windows/staging/sidecar/plotagent-core' = 'core/plotagent-core'
        'packaging/windows/core-boundary.json' = 'core/core-boundary.json'
    }
    foreach ($resource in $resources) {
        $source = ([string]$resource.from).Replace('\', '/')
        $destination = ([string]$resource.to).Replace('\', '/')
        if (-not $expected.ContainsKey($source) -or $expected[$source] -ne $destination) {
            $issues.Add("unexpected extraResource: $source -> $destination")
        }
        if ($source -match '(^|/)(\.venv|tests|data|secrets?)(/|$)') {
            $issues.Add("forbidden extraResource source: $source")
        }
    }
    foreach ($source in $expected.Keys) {
        if (-not ($resources | Where-Object {
                    ([string]$_.from).Replace('\', '/') -eq $source -and
                    ([string]$_.to).Replace('\', '/') -eq $expected[$source]
                })) {
            $issues.Add("missing extraResource: $source")
        }
    }
    $nsisTargets = @($PackageJson.build.win.target | Where-Object {
            $_.target -eq 'nsis' -and @($_.arch) -contains 'x64'
        })
    if ($nsisTargets.Count -ne 1) {
        $issues.Add('electron-builder must have exactly one NSIS x64 target')
    }
    return @($issues)
}

function Get-WindowsPowerShellExecutable {
    $command = Get-Command 'powershell.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return [IO.Path]::GetFullPath($command.Source)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:SystemRoot)) {
        $systemExecutable = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        if (Test-Path -LiteralPath $systemExecutable -PathType Leaf) {
            return [IO.Path]::GetFullPath($systemExecutable)
        }
    }
    $hostExecutable = Join-Path $PSHOME 'powershell.exe'
    if (Test-Path -LiteralPath $hostExecutable -PathType Leaf) {
        return [IO.Path]::GetFullPath($hostExecutable)
    }
    throw '[RELEASE_WINDOWS_POWERSHELL_MISSING] Windows PowerShell 5.1 is required for release verification.'
}

Export-ModuleMember -Function @(
    'Get-DetachedCmsSignatureInfo',
    'Get-ElectronBuilderConfigurationIssues',
    'Get-WindowsPowerShellExecutable',
    'Get-ManifestAuthenticodeSignatures',
    'Get-ReleaseArtifactIntegrityIssues',
    'Get-ReleaseVerificationDecision',
    'New-DetachedCmsSignature',
    'New-ReleaseManifest',
    'Test-PublisherAllowed'
)
