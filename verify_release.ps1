param(
    [string]$DistributionPath = (Join-Path $PSScriptRoot "dist\LightWorkbench")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $DistributionPath -PathType Container)) {
    throw "Distribution folder was not found: $DistributionPath"
}

$requiredFiles = @(
    "LightWorkbench.exe",
    "README_INSTALL.txt",
    "Check Dependencies.cmd",
    "ILM_READING_GUIDE.html"
)

foreach ($fileName in $requiredFiles) {
    $filePath = Join-Path $DistributionPath $fileName
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "Required release file is missing: $filePath"
    }
}

$internalDirectory = Join-Path $DistributionPath "_internal"
if (-not (Test-Path -LiteralPath $internalDirectory -PathType Container)) {
    throw "PyInstaller support directory is missing: $internalDirectory"
}

$executable = Get-Item -LiteralPath (Join-Path $DistributionPath "LightWorkbench.exe")
if ($executable.Length -le 0) {
    throw "The packaged executable is empty: $($executable.FullName)"
}

Write-Host "Release layout verified: $DistributionPath"
Write-Host "Executable size: $($executable.Length) bytes"
