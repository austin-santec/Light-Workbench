param(
    [string]$DistributionPath = (Join-Path $PSScriptRoot "dist\LightWorkbench"),
    [int]$StartupTimeoutSeconds = 10
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "verify_release.ps1") `
    -DistributionPath $DistributionPath
if ($LASTEXITCODE -ne 0) {
    throw "Release layout verification failed."
}

$executablePath = Join-Path $DistributionPath "LightWorkbench.exe"
$process = Start-Process `
    -FilePath $executablePath `
    -WorkingDirectory $DistributionPath `
    -WindowStyle Hidden `
    -PassThru

try {
    $process.WaitForInputIdle($StartupTimeoutSeconds * 1000) | Out-Null
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) {
        throw "Light Workbench exited during startup with code $($process.ExitCode)."
    }
    Write-Host "Packaged executable started successfully (PID $($process.Id))."
}
finally {
    if (-not $process.HasExited) {
        $process.CloseMainWindow() | Out-Null
        if (-not $process.WaitForExit(3000)) {
            Stop-Process -Id $process.Id -Force
        }
    }
    $process.Dispose()
}

Write-Host "Packaged executable smoke test passed."
