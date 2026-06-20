@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "HERMES_EXE=%ROOT%\Hermes_agent\.venv\Scripts\hermes.exe"

if not exist "%HERMES_EXE%" (
    echo Hermes executable not found:
    echo %HERMES_EXE%
    exit /b 1
)

"%HERMES_EXE%" %*

endlocal
