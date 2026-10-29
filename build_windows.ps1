#cd "C:\Users\Austin\Documents\Python Stuff\ILM Python Testing"
# powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
param(
    [string]$PythonExecutable,
    [switch]$ValidatePythonOnly
)

$ErrorActionPreference = "Stop"

function Test-BuildPythonCandidate {
    param([string]$Candidate)

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $null
    }
    $candidatePath = [Environment]::ExpandEnvironmentVariables($Candidate.Trim().Trim('"'))
    if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
        return $null
    }
    try {
        $details = @(
            & $candidatePath -c `
                "import struct, sys; print(sys.executable); print(f'{sys.version_info.major}.{sys.version_info.minor}'); print(struct.calcsize('P') * 8)" `
                2>$null
        )
        if ($LASTEXITCODE -ne 0 -or $details.Count -lt 3) {
            return $null
        }
    } catch {
        return $null
    }
    if ($details[-2] -ne "3.11" -or $details[-1] -ne "32") {
        return $null
    }
    return [PSCustomObject]@{
        Path = [string]$details[-3]
        Version = [string]$details[-2]
        Architecture = [string]$details[-1]
    }
}

$selectedPython = $null
$explicitPython = $PythonExecutable
if ([string]::IsNullOrWhiteSpace($explicitPython)) {
    $explicitPython = $env:LWB_BUILD_PYTHON
}
if (-not [string]::IsNullOrWhiteSpace($explicitPython)) {
    $selectedPython = Test-BuildPythonCandidate $explicitPython
    if ($null -eq $selectedPython) {
        throw "The explicitly configured build interpreter is not Python 3.11 32-bit: $explicitPython"
    }
}

if ($null -eq $selectedPython) {
    $candidates = [System.Collections.Generic.List[string]]::new()
    try {
        $launcherPath = & py -3.11-32 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $launcherPath) {
            $candidates.Add([string]$launcherPath[-1])
        }
    } catch {
        # The launcher can exist without a registered interpreter.
    }

    $candidates.Add(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311-32\python.exe")
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates.Add(
            (Join-Path ${env:ProgramFiles(x86)} "Python311-32\python.exe")
        )
        $candidates.Add(
            (Join-Path ${env:ProgramFiles(x86)} "Python311\python.exe")
        )
    }
    foreach ($command in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        $candidates.Add($command.Source)
    }

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        $selectedPython = Test-BuildPythonCandidate $candidate
        if ($null -ne $selectedPython) {
            break
        }
    }
}

if ($null -eq $selectedPython) {
    throw @"
A Python 3.11 32-bit interpreter is required to build Light Workbench.
Install it, pass -PythonExecutable <path>, or set LWB_BUILD_PYTHON to its full path.
"@
}

Write-Host (
    "Using build Python: {0} ({1}, {2}-bit)" -f `
        $selectedPython.Path, $selectedPython.Version, $selectedPython.Architecture
)

if ($ValidatePythonOnly) {
    Write-Host "Build Python validation passed."
    exit 0
}

& $selectedPython.Path -m PyInstaller --noconfirm --clean ilm_app.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$distributionPath = Join-Path $PSScriptRoot "dist\LightWorkbench"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README_INSTALL.txt") `
    -Destination (Join-Path $distributionPath "README_INSTALL.txt") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Check Dependencies.cmd") `
    -Destination (Join-Path $distributionPath "Check Dependencies.cmd") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "ILM_READING_GUIDE.html") `
    -Destination (Join-Path $distributionPath "ILM_READING_GUIDE.html") -Force

& (Join-Path $PSScriptRoot "verify_release.ps1") -DistributionPath $distributionPath
if ($LASTEXITCODE -ne 0) {
    throw "Packaged release layout verification failed."
}

Write-Host "Build complete: dist\LightWorkbench\LightWorkbench.exe"
Write-Host "Installation guide included: dist\LightWorkbench\README_INSTALL.txt"
Write-Host "Dependency checker included: dist\LightWorkbench\Check Dependencies.cmd"
Write-Host "ILM operator guide included: dist\LightWorkbench\ILM_READING_GUIDE.html"
Write-Host "The target computer still needs the 32-bit VISA runtime for real hardware."
