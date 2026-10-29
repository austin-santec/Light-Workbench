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

$sourceMigrationDirectory = Join-Path `
    $PSScriptRoot "infrastructure\database\sql_migrations"
$packagedMigrationDirectory = Join-Path `
    $internalDirectory "infrastructure\database\sql_migrations"
$migrationVerifier = Join-Path $PSScriptRoot "tools\release_resources.py"
if (-not (Test-Path -LiteralPath $migrationVerifier -PathType Leaf)) {
    throw "SQL migration release verifier is missing: $migrationVerifier"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCommand) {
    & $pythonCommand.Source $migrationVerifier `
        --source-directory $sourceMigrationDirectory `
        --packaged-directory $packagedMigrationDirectory
    $migrationVerificationExitCode = $LASTEXITCODE
}
else {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $pythonLauncher) {
        throw "Python is required to verify packaged SQL migration integrity."
    }
    & $pythonLauncher.Source -3.11-32 $migrationVerifier `
        --source-directory $sourceMigrationDirectory `
        --packaged-directory $packagedMigrationDirectory
    $migrationVerificationExitCode = $LASTEXITCODE
}
if ($migrationVerificationExitCode -ne 0) {
    throw "Packaged SQL migration integrity verification failed."
}

$requiredTemplates = @(
    "OSX-150 Single Mode COC Template 2 (45max).xlsx",
    "OSX-150 Single Mode COC Template 1 (48max).xlsx",
    "OSX-100 Single Mode COC Template 2 (45max).xlsx",
    "OSX-100 Single Mode COC Template 1 (48max).xlsx",
    "OSX-100 Multi Mode COC Template 2 (45max).xlsx",
    "OSX-100 Multi Mode COC Template 1 (48max).xlsx"
)
$templateDirectory = Join-Path $internalDirectory "Templates"
foreach ($templateName in $requiredTemplates) {
    $templatePath = Join-Path $templateDirectory $templateName
    if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
        throw "Required COC template is missing: $templatePath"
    }
}

$executable = Get-Item -LiteralPath (Join-Path $DistributionPath "LightWorkbench.exe")
if ($executable.Length -le 0) {
    throw "The packaged executable is empty: $($executable.FullName)"
}

Write-Host "Release layout verified: $DistributionPath"
Write-Host "Executable size: $($executable.Length) bytes"
