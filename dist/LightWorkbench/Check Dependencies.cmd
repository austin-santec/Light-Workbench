@echo off
setlocal

set "LWB_X86_RUNTIME_DIR=%WINDIR%\System32"
if exist "%WINDIR%\SysWOW64\" set "LWB_X86_RUNTIME_DIR=%WINDIR%\SysWOW64"

set "LWB_RUNTIME_MISSING="
for %%F in (VCRUNTIME140.dll MSVCP140.dll MSVCP140_1.dll) do (
    if not exist "%LWB_X86_RUNTIME_DIR%\%%F" (
        echo [FAIL] Missing x86 Visual C++ runtime file: %LWB_X86_RUNTIME_DIR%\%%F
        set "LWB_RUNTIME_MISSING=1"
    )
)

if defined LWB_RUNTIME_MISSING (
    echo.
    echo Install or repair the Microsoft Visual C++ 2015-2022 Redistributable ^(x86^),
    echo then run this dependency check again.
    echo Do not copy VCRUNTIME140.dll or MSVCP140*.dll into the LightWorkbench folder.
    pause
    exit /b 1
)

start "" "%~dp0LightWorkbench.exe" --check-dependencies
endlocal
