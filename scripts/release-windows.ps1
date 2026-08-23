[CmdletBinding()]
param(
    [string]$PythonExecutable = 'python',
    [string]$PnpmExecutable = 'pnpm',
    [switch]$Sign,
    [string]$CertificatePath,
    [Security.SecureString]$CertificatePassword,
    [string]$TimestampServer,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'release/windows'))
$expectedReleaseRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'release/windows'))
$workRoot = Join-Path $releaseRoot 'work'
$wheelRoot = Join-Path $workRoot 'wheels'
$wheelSitePackages = Join-Path $workRoot 'wheel-site-packages'
$stagingRoot = Join-Path $releaseRoot 'staging'
$sidecarRoot = Join-Path $stagingRoot 'sidecar'
$electronRoot = Join-Path $releaseRoot 'electron'
$publishRoot = Join-Path $releaseRoot 'publish'
$manifestPath = Join-Path $publishRoot 'release-manifest.json'
$signaturePath = Join-Path $publishRoot 'release-manifest.p7s'
$modulePath = Join-Path $repoRoot 'packaging/windows/ReleaseTools.psm1'
$verifierPath = Join-Path $repoRoot 'scripts/verify-windows-release.ps1'

Import-Module $modulePath -Force

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Write-Host "> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "[RELEASE_COMMAND_FAILED] Exit $LASTEXITCODE from $FilePath"
    }
}

function Get-SigningCertificate {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][Security.SecureString]$Password
    )
    $passwordPointer = [IntPtr]::Zero
    try {
        $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
        $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
        return [Security.Cryptography.X509Certificates.X509Certificate2]::new(
            [IO.Path]::GetFullPath($Path),
            $plainPassword,
            [Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet
        )
    } finally {
        if ($passwordPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
        }
    }
}

function Set-FileAuthenticodeSignature {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )
    $parameters = @{
        LiteralPath = $Path
        Certificate = $Certificate
        HashAlgorithm = 'SHA256'
    }
    if (-not [string]::IsNullOrWhiteSpace($TimestampServer)) {
        $parameters.TimestampServer = $TimestampServer
    }
    $signature = Set-AuthenticodeSignature @parameters
    if ($signature.Status -ne 'Valid') {
        throw "[RELEASE_SIGNATURE_FAILED] $Path returned Authenticode status $($signature.Status)."
    }
}

if (-not [string]::Equals($releaseRoot, $expectedReleaseRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw '[RELEASE_UNSAFE_CLEAN_TARGET] Release root validation failed.'
}
if (-not $releaseRoot.StartsWith(
        [IO.Path]::GetFullPath((Join-Path $repoRoot 'release')) + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
    throw '[RELEASE_UNSAFE_CLEAN_TARGET] Refusing to clean outside the repository release directory.'
}
if ($env:CSC_LINK -or $env:CSC_KEY_PASSWORD -or $env:WIN_CSC_LINK -or $env:WIN_CSC_KEY_PASSWORD) {
    throw '[RELEASE_IMPLICIT_SIGNING_DISABLED] Clear electron-builder signing variables and use -Sign explicitly.'
}
if ($Sign -and [string]::IsNullOrWhiteSpace($CertificatePath)) {
    throw '[RELEASE_CERTIFICATE_REQUIRED] -Sign requires -CertificatePath.'
}
if (-not $Sign -and -not [string]::IsNullOrWhiteSpace($CertificatePath)) {
    throw '[RELEASE_EXPLICIT_SIGN_REQUIRED] Certificate parameters require -Sign.'
}

$packageJson = Get-Content -LiteralPath (Join-Path $repoRoot 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$configurationIssues = @(Get-ElectronBuilderConfigurationIssues -PackageJson $packageJson)
if ($configurationIssues.Count -gt 0) {
    throw "[RELEASE_CONFIG_INVALID] $($configurationIssues -join '; ')"
}
$gitCommit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw '[RELEASE_GIT_COMMIT_UNAVAILABLE] Could not resolve the current commit.'
}
$sourceDirty = @(& git status --porcelain --untracked-files=normal).Count -gt 0
if ($Sign -and $sourceDirty) {
    throw '[RELEASE_SIGNED_DIRTY_WORKTREE] Signed release output requires a clean Git worktree.'
}

$plan = @(
    'clean release/windows only',
    'run Python, TypeScript, and release-tool tests',
    'build wheel and install it into release/windows/work/wheel-site-packages',
    'build PyInstaller onedir sidecar into release/windows/staging/sidecar',
    'build electron-vite output and electron-builder win-unpacked/NSIS',
    $(if ($Sign) { 'sign unpacked executables, installer, and detached manifest using the explicit certificate' } else { 'emit an explicitly unsigned-development manifest (no signature claim)' }),
    'verify the publish directory offline and require an exact file set'
)
if ($DryRun) {
    Write-Output '[DRY-RUN] Windows release plan validated; no files were changed.'
    $plan | ForEach-Object { Write-Output "  - $_" }
    return
}

if ($env:OS -ne 'Windows_NT') {
    throw '[RELEASE_WINDOWS_REQUIRED] NSIS and Authenticode packaging require Windows.'
}
if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $wheelRoot, $wheelSitePackages, $sidecarRoot, $publishRoot -Force | Out-Null

Push-Location $repoRoot
try {
    Invoke-CheckedCommand -FilePath $PythonExecutable -Arguments @('-m', 'pytest')
    Invoke-CheckedCommand -FilePath $PnpmExecutable -Arguments @('run', 'lint')
    Invoke-CheckedCommand -FilePath $PnpmExecutable -Arguments @('run', 'test')
    Invoke-CheckedCommand -FilePath $PnpmExecutable -Arguments @('run', 'test:release')

    Invoke-CheckedCommand -FilePath $PythonExecutable -Arguments @(
        '-m', 'build', '--wheel', '--outdir', $wheelRoot
    )
    $wheels = @(Get-ChildItem -LiteralPath $wheelRoot -Filter '*.whl' -File)
    if ($wheels.Count -ne 1) {
        throw "[RELEASE_WHEEL_COUNT_INVALID] Expected one wheel, found $($wheels.Count)."
    }
    Invoke-CheckedCommand -FilePath $PythonExecutable -Arguments @(
        '-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps',
        '--target', $wheelSitePackages, $wheels[0].FullName
    )

    $env:PLOTAGENT_WHEEL_SITE_PACKAGES = $wheelSitePackages
    try {
        Invoke-CheckedCommand -FilePath $PythonExecutable -Arguments @(
            '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--distpath', $sidecarRoot,
            '--workpath', (Join-Path $workRoot 'pyinstaller'),
            (Join-Path $repoRoot 'packaging/windows/plotagent-core.spec')
        )
    } finally {
        Remove-Item Env:PLOTAGENT_WHEEL_SITE_PACKAGES -ErrorAction SilentlyContinue
    }
    $sidecarExecutable = Join-Path $sidecarRoot 'plotagent-core/plotagent-core.exe'
    if (-not (Test-Path -LiteralPath $sidecarExecutable -PathType Leaf)) {
        throw '[RELEASE_SIDECAR_MISSING] PyInstaller did not create the expected onedir executable.'
    }

    Invoke-CheckedCommand -FilePath $PnpmExecutable -Arguments @('run', 'build')
    Invoke-CheckedCommand -FilePath $PnpmExecutable -Arguments @(
        'exec', 'electron-builder', '--win', 'dir', '--x64'
    )
    $unpackedDirectory = Join-Path $electronRoot 'win-unpacked'
    if (-not (Test-Path -LiteralPath $unpackedDirectory -PathType Container)) {
        throw '[RELEASE_ELECTRON_UNPACKED_MISSING] electron-builder did not create win-unpacked.'
    }

    $certificate = $null
    if ($Sign) {
        if ($null -eq $CertificatePassword) {
            $CertificatePassword = Read-Host 'PFX password' -AsSecureString
        }
        $certificate = Get-SigningCertificate -Path $CertificatePath -Password $CertificatePassword
        if (-not $certificate.HasPrivateKey) {
            throw '[RELEASE_CERTIFICATE_PRIVATE_KEY_MISSING] The certificate has no private key.'
        }
        foreach ($executable in Get-ChildItem -LiteralPath $unpackedDirectory -Filter '*.exe' -File -Recurse) {
            Set-FileAuthenticodeSignature -Path $executable.FullName -Certificate $certificate
        }
    }

    Invoke-CheckedCommand -FilePath $PnpmExecutable -Arguments @(
        'exec', 'electron-builder', '--win', 'nsis', '--x64', '--prepackaged', $unpackedDirectory
    )
    $installers = @(Get-ChildItem -LiteralPath $electronRoot -Filter '*-setup.exe' -File)
    if ($installers.Count -ne 1) {
        throw "[RELEASE_INSTALLER_COUNT_INVALID] Expected one NSIS installer, found $($installers.Count)."
    }
    $publishedInstaller = Join-Path $publishRoot $installers[0].Name
    Copy-Item -LiteralPath $installers[0].FullName -Destination $publishedInstaller
    if ($Sign) {
        Set-FileAuthenticodeSignature -Path $publishedInstaller -Certificate $certificate
    }

    $releaseMode = if ($Sign) { 'signed' } else { 'unsigned-development' }
    New-ReleaseManifest `
        -PublishDirectory $publishRoot `
        -ArtifactPaths @($publishedInstaller) `
        -Version ([string]$packageJson.version) `
        -GitCommit $gitCommit `
        -SourceDirty $sourceDirty `
        -ReleaseMode $releaseMode `
        -OutputPath $manifestPath | Out-Null
    if ($Sign) {
        New-DetachedCmsSignature `
            -ManifestPath $manifestPath `
            -SignaturePath $signaturePath `
            -Certificate $certificate
    }

    $verificationArguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $verifierPath,
        '-ManifestPath', $manifestPath
    )
    if ($Sign) {
        $verificationArguments += @(
            '-AllowedPublisher', $certificate.Subject,
            '-AllowedPublisherThumbprint', $certificate.Thumbprint
        )
    } else {
        $verificationArguments += '-AllowUnsignedDevelopment'
    }
    Invoke-CheckedCommand -FilePath (Get-WindowsPowerShellExecutable) -Arguments $verificationArguments

    Write-Output "[RELEASE_READY][$releaseMode] $publishRoot"
    Write-Output "Manifest: $manifestPath"
    if (-not $Sign) {
        Write-Warning 'This installer is unsigned development output and is blocked by the verifier unless -AllowUnsignedDevelopment is explicit.'
    }
} finally {
    Pop-Location
}
