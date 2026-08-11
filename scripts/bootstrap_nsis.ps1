param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$nsisVersion = "3.12"
$sevenZipVersion = "26.02"
$nsisHash = "3BC2B06253A7E4957111BE152AC6A536E0C7478A706E19DA814038DB5D706495"
$sevenZipReducerHash = "56B8CC9F4971CEF253644FAFE54063ED7FDCA551D4DEE0F8C6BAA81B855ACD72"
$sevenZipInstallerHash = "6745FA76DC2EA031596D8678F6F6B99C3C1B435B4164A63485ADBBC7B8D82EF0"
$toolsRoot = Join-Path $ProjectRoot "work\build-tools"
$installRoot = Join-Path $toolsRoot "nsis-$nsisVersion"
$compiler = Join-Path $installRoot "makensis.exe"
if (Test-Path -LiteralPath $compiler) {
    Write-Output $compiler
    exit 0
}

function Get-VerifiedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$ExpectedHash
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        & curl.exe --http1.1 --noproxy "*" --fail --location --retry 4 --retry-all-errors --output $Path $Url
        if ($LASTEXITCODE -ne 0) { throw "Failed to download $Url" }
    }
    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actualHash -ne $ExpectedHash) {
        throw "Download hash mismatch for $Path. Expected $ExpectedHash, received $actualHash."
    }
}

New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
$sevenZipReducer = Join-Path $toolsRoot "7zr-26.02.exe"
Get-VerifiedFile -Path $sevenZipReducer `
    -Url "https://github.com/ip7z/7zip/releases/download/$sevenZipVersion/7zr.exe" `
    -ExpectedHash $sevenZipReducerHash

$sevenZipInstaller = Join-Path $toolsRoot "7z2602-x64.exe"
Get-VerifiedFile -Path $sevenZipInstaller `
    -Url "https://github.com/ip7z/7zip/releases/download/$sevenZipVersion/7z2602-x64.exe" `
    -ExpectedHash $sevenZipInstallerHash

$sevenZipRoot = Join-Path $toolsRoot "7zip-$sevenZipVersion"
$sevenZip = Join-Path $sevenZipRoot "7z.exe"
if (-not (Test-Path -LiteralPath $sevenZip)) {
    New-Item -ItemType Directory -Force -Path $sevenZipRoot | Out-Null
    & $sevenZipReducer x -y "-o$sevenZipRoot" $sevenZipInstaller | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sevenZip)) {
        throw "Failed to extract the verified 7-Zip build tool."
    }
}

$installer = Join-Path $toolsRoot "nsis-$nsisVersion-setup.exe"
Get-VerifiedFile -Path $installer `
    -Url "https://downloads.sourceforge.net/project/nsis/NSIS%203/$nsisVersion/nsis-$nsisVersion-setup.exe" `
    -ExpectedHash $nsisHash

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
& $sevenZip x -y "-o$installRoot" $installer | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $compiler)) {
    throw "Failed to extract the verified NSIS compiler."
}
Write-Output $compiler
