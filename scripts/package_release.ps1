param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Version = "1.4.0"
)

$ErrorActionPreference = "Stop"
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
Compress-Archive -LiteralPath $releaseDirectory -DestinationPath $applicationZip -CompressionLevel Optimal

$ffmpegCommit = "38b88335f9"
$ffmpegSource = Join-Path $artifactRoot "FFmpeg-8.1.2-source-$ffmpegCommit.zip"
& curl.exe --fail --location --retry 3 --output $ffmpegSource "https://github.com/FFmpeg/FFmpeg/archive/$ffmpegCommit.zip"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download the corresponding FFmpeg source archive."
}

$checksumFile = Join-Path $artifactRoot "SHA256SUMS.txt"
$checksumLines = foreach ($path in @($applicationZip, $ffmpegSource)) {
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($path))"
}
[IO.File]::WriteAllLines($checksumFile, $checksumLines, [Text.UTF8Encoding]::new($false))

Write-Host "Release artifacts: $artifactRoot"
Get-ChildItem -LiteralPath $artifactRoot -File | Select-Object Name, Length
