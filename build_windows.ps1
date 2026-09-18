$ErrorActionPreference = "Stop"

py -3.11-32 -m PyInstaller --noconfirm --clean ilm_app.spec

$distributionPath = Join-Path $PSScriptRoot "dist\LightWorkbench"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README_INSTALL.txt") `
    -Destination (Join-Path $distributionPath "README_INSTALL.txt") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Check Dependencies.cmd") `
    -Destination (Join-Path $distributionPath "Check Dependencies.cmd") -Force

Write-Host "Build complete: dist\LightWorkbench\LightWorkbench.exe"
Write-Host "Installation guide included: dist\LightWorkbench\README_INSTALL.txt"
Write-Host "Dependency checker included: dist\LightWorkbench\Check Dependencies.cmd"
Write-Host "The target computer still needs the 32-bit VISA runtime for real hardware."
