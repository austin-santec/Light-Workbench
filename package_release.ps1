param(
    [string]$DistributionPath = (Join-Path $PSScriptRoot "dist\LightWorkbench"),
    [string]$ReleaseDirectory = (Join-Path $PSScriptRoot "releases"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "verify_release.ps1") `
    -DistributionPath $DistributionPath
if ($LASTEXITCODE -ne 0) {
    throw "Release layout verification failed."
}

$versionMatch = Select-String `
    -LiteralPath (Join-Path $PSScriptRoot "config\app_info.py") `
    -Pattern 'APP_VERSION\s*=\s*["'']([^"'']+)["'']' `
    | Select-Object -First 1
if ($null -eq $versionMatch) {
    throw "APP_VERSION could not be read from config\app_info.py."
}

$version = $versionMatch.Matches[0].Groups[1].Value
$archiveName = "LightWorkbench-v$version.zip"
New-Item -ItemType Directory -Path $ReleaseDirectory -Force | Out-Null
$archivePath = Join-Path $ReleaseDirectory $archiveName

if ((Test-Path -LiteralPath $archivePath) -and -not $Force) {
    throw "Release archive already exists. Use -Force to replace it: $archivePath"
}

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

Compress-Archive `
    -Path $DistributionPath `
    -DestinationPath $archivePath `
    -CompressionLevel Optimal

Write-Host "Release archive created: $archivePath"
