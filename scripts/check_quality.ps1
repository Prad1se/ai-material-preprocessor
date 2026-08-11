param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "python_runtime.ps1")
$python = Resolve-PythonExecutable -ProjectRoot $ProjectRoot -Preferred $PythonExecutable

$workRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "work"))
$testTemp = Join-Path $workRoot ("pytest-quality-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $testTemp | Out-Null
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$env:TEMP = $testTemp
$env:TMP = $testTemp

Push-Location $ProjectRoot
try {
    & $python -m ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff format check failed." }
    & $python -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff lint failed." }
    & $python -m mypy src
    if ($LASTEXITCODE -ne 0) { throw "mypy failed." }
    & $python -m pytest -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
}
finally {
    Pop-Location
    if ($null -eq $previousTemp) { Remove-Item Env:TEMP -ErrorAction SilentlyContinue }
    else { $env:TEMP = $previousTemp }
    if ($null -eq $previousTmp) { Remove-Item Env:TMP -ErrorAction SilentlyContinue }
    else { $env:TMP = $previousTmp }

    $resolvedTestTemp = [IO.Path]::GetFullPath($testTemp)
    $workPrefix = $workRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if ($resolvedTestTemp.StartsWith($workPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $testTemp)) {
        Remove-Item -LiteralPath $testTemp -Recurse -Force
    }
}
