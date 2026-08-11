param(
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$artifactRoot = Join-Path $ProjectRoot "release\v$Version"
$installer = Join-Path $artifactRoot "AI-Material-Preprocessor-v$Version-windows-x64-setup.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer not found: $installer" }

$workRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "work"))
$smokeRoot = Join-Path $workRoot "installer-smoke-$Version"
$installRoot = Join-Path $smokeRoot "installed"
$diagnostics = Join-Path $smokeRoot "diagnostics"
if (Test-Path -LiteralPath $smokeRoot) {
    $resolved = [IO.Path]::GetFullPath($smokeRoot)
    if (-not $resolved.StartsWith($workRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe installer smoke directory."
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

$installArguments = @("/S", "/D=$installRoot")
$install = Start-Process -FilePath $installer -ArgumentList $installArguments -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Silent installer failed with $($install.ExitCode)." }
$exe = Join-Path $installRoot "AI-Material-Preprocessor.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Installed executable was not found." }

$selfTest = Start-Process -FilePath $exe -ArgumentList @("--self-test", $diagnostics) -Wait -PassThru
if ($selfTest.ExitCode -ne 0) { throw "Installed self-test failed with $($selfTest.ExitCode)." }
$report = Get-Content -LiteralPath (Join-Path $diagnostics "diagnostics.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.overall -ne "passed") { throw "Installed self-test report failed." }

$previousPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
try {
    $gui = Start-Process -FilePath $exe -ArgumentList "--skip-onboarding" -PassThru
    Start-Sleep -Seconds 5
    if ($gui.HasExited) { throw "Installed GUI exited before smoke validation." }
    Stop-Process -Id $gui.Id -Force
    $gui.WaitForExit()
}
finally {
    $env:QT_QPA_PLATFORM = $previousPlatform
}

$uninstaller = Join-Path $installRoot "Uninstall.exe"
if (-not (Test-Path -LiteralPath $uninstaller)) { throw "Uninstaller was not created." }
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw "Silent uninstall failed with $($uninstall.ExitCode)." }
if (Test-Path -LiteralPath $exe) { throw "Installed executable remained after uninstall." }
Write-Host "Installer install, self-test, GUI smoke, and uninstall passed."
