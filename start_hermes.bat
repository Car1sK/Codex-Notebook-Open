@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "HERMES_DIR=%ROOT%\Hermes_agent"
set "HERMES_EXE=%HERMES_DIR%\.venv\Scripts\hermes.exe"
set "RUN_SCRIPT=%ROOT%\scripts\hermes_runtime.ps1"

if not exist "%HERMES_EXE%" (
    echo Hermes executable not found:
    echo %HERMES_EXE%
    echo Create the virtual environment first.
    exit /b 1
)

if not exist "%RUN_SCRIPT%" (
    echo Run script not found:
    echo %RUN_SCRIPT%
    exit /b 1
)

where wt.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    wt.exe -w 0 new-tab --title "Hermes Agent" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -File "%RUN_SCRIPT%" -Action start %*
    echo Hermes started in Windows Terminal.
    exit /b 0
)

start "Hermes Agent" /D "%ROOT%" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -File "%RUN_SCRIPT%" -Action start %*
echo Hermes started in PowerShell.

endlocal
