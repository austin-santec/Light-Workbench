param(
    [string]$DistributionPath = (Join-Path $PSScriptRoot "dist\LightWorkbench"),
    [string]$PythonExecutable
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

# Application-local copies can force native components such as ODBC Driver 18
# to load an older Visual C++ runtime than the installed driver requires.
# Light Workbench deliberately uses the supported system x86 redistributable.
$forbiddenRuntimeNames = @(
    "VCRUNTIME140.dll",
    "MSVCP140.dll",
    "MSVCP140_1.dll"
)
$bundledRuntimeFiles = @(
    Get-ChildItem -LiteralPath $DistributionPath -Recurse -File |
        Where-Object { $forbiddenRuntimeNames -contains $_.Name }
)
if ($bundledRuntimeFiles.Count -gt 0) {
    $relativeRuntimePaths = @(
        foreach ($runtimeFile in $bundledRuntimeFiles) {
            $runtimeFile.FullName.Substring($DistributionPath.Length).TrimStart("\")
        }
    )
    throw @"
Unsupported application-local Visual C++ runtime file(s) were packaged:
$($relativeRuntimePaths -join [Environment]::NewLine)
These files can break ODBC Driver 18. Update ilm_app.spec or the packaging hooks
so Light Workbench uses the installed x86 Visual C++ Redistributable.
"@
}

$sourceMigrationDirectory = Join-Path `
    $PSScriptRoot "infrastructure\database\sql_migrations"
$packagedMigrationDirectory = Join-Path `
    $internalDirectory "infrastructure\database\sql_migrations"
$migrationVerifier = Join-Path $PSScriptRoot "tools\release_resources.py"
if (-not (Test-Path -LiteralPath $migrationVerifier -PathType Leaf)) {
    throw "SQL migration release verifier is missing: $migrationVerifier"
}

$pythonCandidates = [System.Collections.Generic.List[string]]::new()
if (-not [string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $pythonCandidates.Add($PythonExecutable)
}
if (-not [string]::IsNullOrWhiteSpace($env:LWB_BUILD_PYTHON)) {
    $pythonCandidates.Add($env:LWB_BUILD_PYTHON)
}
$pythonCandidates.Add(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311-32\python.exe")
)
foreach ($pythonCommand in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
    $pythonCandidates.Add($pythonCommand.Source)
}

$verificationPython = $null
foreach ($candidate in @($pythonCandidates | Select-Object -Unique)) {
    $candidatePath = [Environment]::ExpandEnvironmentVariables(
        ([string]$candidate).Trim().Trim('"')
    )
    if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
        continue
    }
    try {
        & $candidatePath -c "import sys; print(sys.executable)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $verificationPython = $candidatePath
            break
        }
    }
    catch {
        # Windows Store aliases can resolve as files but remain non-executable.
    }
}
if ($null -eq $verificationPython) {
    throw "Python is required to verify packaged SQL migration integrity."
}

& $verificationPython $migrationVerifier `
    --source-directory $sourceMigrationDirectory `
    --packaged-directory $packagedMigrationDirectory
$migrationVerificationExitCode = $LASTEXITCODE
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
Write-Host "No conflicting application-local Visual C++ runtime DLLs were found."
