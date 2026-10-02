#cd "C:\Users\Austin\Documents\Python Stuff\ILM Python Testing"
# powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
$ErrorActionPreference = "Stop"

$launcherCheck = $null
try {
    $launcherCheck = & py -3.11-32 -c "import sys; print(sys.executable)" 2>$null
} catch {
    $launcherCheck = $null
}
if ($LASTEXITCODE -eq 0) {
    py -3.11-32 -m PyInstaller --noconfirm --clean ilm_app.spec
} else {
    $pythonDetails = & python -c "import struct, sys; print(sys.executable); print(struct.calcsize('P') * 8)" 2>$null
    if ($LASTEXITCODE -ne 0 -or $pythonDetails[-1] -ne "32") {
        throw "A registered 32-bit Python 3.11 interpreter is required to build Light Workbench."
    }
    python -m PyInstaller --noconfirm --clean ilm_app.spec
}
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
