@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "WORKSPACE=%~dp0"
set "PYTHON_EXE=%WORKSPACE%opennotebook\.venv\Scripts\python.exe"
set "OLLAMA_API_BASE=http://127.0.0.1:11434"
if not defined OLLAMA_EMBEDDING_MODEL set "OLLAMA_EMBEDDING_MODEL=nomic-embed-text:latest"

call :resolve_ollama
if errorlevel 1 goto :failed

echo [Ollama] Checking local API...
call :is_port_listening 11434
if errorlevel 1 (
  echo [Ollama] Starting local Ollama service...
  start "Ollama" /min "%OLLAMA_EXE%" serve
  call :wait_for_port 11434 60
  if errorlevel 1 (
    echo ERROR: Ollama did not become ready on port 11434.
    goto :failed
  )
)

if not exist "%PYTHON_EXE%" (
  echo ERROR: Python environment is missing. Run "uv sync" in "%WORKSPACE%opennotebook" first.
  goto :failed
)

call "%PYTHON_EXE%" "%WORKSPACE%scripts\check_ollama_models.py"
if errorlevel 1 goto :failed

exit /b 0

:resolve_ollama
set "OLLAMA_EXE="
for /f "delims=" %%I in ('where ollama.exe 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%I"
if not defined OLLAMA_EXE set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not exist "%OLLAMA_EXE%" (
  echo ERROR: ollama.exe was not found. Install Ollama first.
  exit /b 1
)
exit /b 0

:is_port_listening
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort %~1 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
exit /b %errorlevel%

:wait_for_port
for /l %%N in (1,1,%~2) do (
  call :is_port_listening %~1
  if not errorlevel 1 exit /b 0
  powershell.exe -NoProfile -Command "Start-Sleep -Seconds 1" >nul
)
exit /b 1

:failed
echo.
echo Ollama startup/check failed. Review the message above.
pause
exit /b 1
