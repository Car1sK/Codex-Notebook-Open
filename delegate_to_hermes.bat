@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SCRIPT=%ROOT%\delegate_to_hermes.ps1"

if not exist "%SCRIPT%" (
    echo Delegate script not found:
    echo %SCRIPT%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*

endlocal
