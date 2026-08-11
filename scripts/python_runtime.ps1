function Resolve-PythonExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [string]$Preferred
    )

    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        if (-not (Test-Path -LiteralPath $Preferred -PathType Leaf)) {
            throw "Requested Python executable was not found: $Preferred"
        }
        return [IO.Path]::GetFullPath($Preferred)
    }

    $projectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
        return [IO.Path]::GetFullPath($projectPython)
    }

    $command = Get-Command python -CommandType Application -ErrorAction Stop
    return $command.Source
}
