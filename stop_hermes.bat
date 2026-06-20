@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "HERMES_DIR=%ROOT%\Hermes_agent"
set "RUN_SCRIPT=%ROOT%\scripts\hermes_runtime.ps1"

if not exist "%HERMES_DIR%\" (
    echo Hermes directory not found:
    echo %HERMES_DIR%
    exit /b 1
)

if not exist "%RUN_SCRIPT%" (
    echo Hermes runtime script not found:
    echo %RUN_SCRIPT%
    exit /b 1
)

where wt.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    wt.exe -w 0 new-tab --title "Stop Hermes" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -File "%RUN_SCRIPT%" -Action stop
    echo Hermes stop command opened in Windows Terminal.
    exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUN_SCRIPT%" -Action stop

endlocal
