param(
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$artifactRoot = Join-Path $ProjectRoot "release\v$Version"
$archive = Join-Path $artifactRoot "AI-Material-Preprocessor-v$Version-windows-x64.zip"
if (-not (Test-Path -LiteralPath $archive)) { throw "Portable ZIP not found: $archive" }

$workRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "work"))
$smokeRoot = Join-Path $workRoot "portable-smoke-$Version"
if (Test-Path -LiteralPath $smokeRoot) {
    $resolved = [IO.Path]::GetFullPath($smokeRoot)
    $workPrefix = $workRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($workPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe portable smoke directory."
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $smokeRoot

$applicationRoot = Join-Path $smokeRoot "AI-Material-Preprocessor"
$exe = Join-Path $applicationRoot "AI-Material-Preprocessor.exe"
$diagnostics = Join-Path $smokeRoot "diagnostics"
if (-not (Test-Path -LiteralPath $exe)) { throw "Portable executable was not found after extraction." }

$selfTest = Start-Process -FilePath $exe -ArgumentList @("--self-test", $diagnostics) -Wait -PassThru
if ($selfTest.ExitCode -ne 0) { throw "Portable self-test returned $($selfTest.ExitCode)." }
$reportPath = Join-Path $diagnostics "diagnostics.json"
if (-not (Test-Path -LiteralPath $reportPath)) { throw "Portable diagnostics report was not created." }
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.overall -ne "passed") { throw "Portable self-test report failed." }

$previousPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
try {
    $gui = Start-Process -FilePath $exe -ArgumentList "--skip-onboarding" -PassThru
    Start-Sleep -Seconds 5
    if ($gui.HasExited) { throw "Portable GUI exited before smoke validation." }
    Stop-Process -Id $gui.Id -Force
    $gui.WaitForExit()
}
finally {
    $env:QT_QPA_PLATFORM = $previousPlatform
}
Write-Host "Portable ZIP extraction, self-test, and GUI smoke passed."