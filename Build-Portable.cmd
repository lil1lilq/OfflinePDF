@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto :failed

if not exist ".venv\Scripts\python.exe" (
    echo Creating a Python 3.12 virtual environment...
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo Python 3.12 x64 is required. Install it and run this file again.
        goto :failed
    )
)

".venv\Scripts\python.exe" -c "import struct,sys; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo The existing .venv is not Python 3.12 x64.
    echo Rename or remove .venv, then run this file again.
    goto :failed
)

echo Building the portable Windows version...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\packaging\build_windows.ps1" -Python "%CD%\.venv\Scripts\python.exe" -FixFormat -SkipInstaller
if errorlevel 1 goto :failed

echo Build completed: release\OfflinePDF-Windows-x64-portable.zip
start "" "%CD%\release"
goto :end

:failed
echo Build failed. Read the error above before closing this window.
:end
pause
endlocal
