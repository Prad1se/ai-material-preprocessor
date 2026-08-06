param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][ValidateSet("word", "powerpoint")][string]$Kind
)

$ErrorActionPreference = "Stop"
$inputFull = [System.IO.Path]::GetFullPath($InputPath)
$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
$app = $null
$document = $null

try {
    if ($Kind -eq "word") {
        $app = New-Object -ComObject Word.Application
        $app.Visible = $false
        $app.DisplayAlerts = 0
        $document = $app.Documents.Open($inputFull, $false, $true)
        $document.ExportAsFixedFormat($outputFull, 17)
    }
    else {
        $app = New-Object -ComObject PowerPoint.Application
        $document = $app.Presentations.Open($inputFull, $true, $true, $false)
        $document.SaveAs($outputFull, 32)
    }
}
finally {
    if ($document -ne $null) {
        $document.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    }
    if ($app -ne $null) {
        $app.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
