param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Version = "2.0.0rc1",
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "python_runtime.ps1")
$python = Resolve-PythonExecutable -ProjectRoot $ProjectRoot -Preferred $PythonExecutable
& $python (Join-Path $ProjectRoot "scripts\check_release_metadata.py") --expected-version $Version
if ($LASTEXITCODE -ne 0) { throw "Release metadata check failed." }

$releaseDirectory = Join-Path $ProjectRoot "dist\AI-Material-Preprocessor"
if (-not (Test-Path -LiteralPath $releaseDirectory)) {
    throw "Release directory not found. Run scripts\build_release.ps1 first."
}

$artifactRoot = Join-Path $ProjectRoot "release\v$Version"
$resolvedProject = [IO.Path]::GetFullPath($ProjectRoot)
$resolvedArtifact = [IO.Path]::GetFullPath($artifactRoot)
if (-not $resolvedArtifact.StartsWith($resolvedProject, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write release artifacts outside the project."
}
if (Test-Path -LiteralPath $artifactRoot) {
    Remove-Item -LiteralPath $artifactRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null

$applicationZip = Join-Path $artifactRoot "AI-Material-Preprocessor-v$Version-windows-x64.zip"
& $python (Join-Path $ProjectRoot "scripts\create_portable_zip.py") $releaseDirectory $applicationZip
if ($LASTEXITCODE -ne 0) { throw "Portable ZIP creation failed." }

$installer = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (
    Join-Path $ProjectRoot "scripts\build_installer.ps1"
) -ProjectRoot $ProjectRoot -Version $Version -OutputDirectory $artifactRoot | Select-Object -Last 1
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer creation failed." }

$ffmpegCommit = "38b88335f9"
$ffmpegSource = Join-Path $artifactRoot "FFmpeg-8.1.2-source-$ffmpegCommit.zip"
& curl.exe --http1.1 --noproxy "*" --fail --location --retry 3 --output $ffmpegSource "https://github.com/FFmpeg/FFmpeg/archive/$ffmpegCommit.zip"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download the corresponding FFmpeg source archive."
}

$checksumFile = Join-Path $artifactRoot "SHA256SUMS.txt"
$checksumLines = foreach ($path in @($applicationZip, $installer, $ffmpegSource)) {
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($path))"
}
[IO.File]::WriteAllLines($checksumFile, $checksumLines, [Text.UTF8Encoding]::new($false))

Write-Host "Release artifacts: $artifactRoot"
Get-ChildItem -LiteralPath $artifactRoot -File | Select-Object Name, Length
