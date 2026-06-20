@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "WORKSPACE=%~dp0"
set "HERMES_EXE=%WORKSPACE%Hermes_agent\.venv\Scripts\hermes.exe"
set "NOTEBOOKLM_PY=%WORKSPACE%notebooklm-py"
set "OPEN_NOTEBOOK_ENV=%WORKSPACE%opennotebook\.env"

if not exist "%HERMES_EXE%" (
  echo ERROR: Hermes executable was not found at "%HERMES_EXE%".
  goto :failed
)

if not exist "%NOTEBOOKLM_PY%\.venv\Scripts\python.exe" (
  echo ERROR: notebooklm-py Python environment was not found.
  goto :failed
)

if not exist "%OPEN_NOTEBOOK_ENV%" (
  echo ERROR: Open Notebook .env was not found.
  echo Start Open Notebook once with start_open_notebook.bat first.
  goto :failed
)

echo Ensuring Hermes MCP support is installed...
pushd "%WORKSPACE%Hermes_agent" >nul
"%WORKSPACE%Hermes_agent\.venv\Scripts\python.exe" -c "import mcp" >nul 2>nul
if errorlevel 1 (
  call uv sync --extra mcp
  if errorlevel 1 (
    popd >nul
    goto :failed
  )
) else (
  echo Hermes MCP Python dependency already exists. Skipping uv sync.
)
popd >nul

echo Installing Open Notebook MCP server for Hermes...
"%HERMES_EXE%" config path >nul
if errorlevel 1 goto :failed

"%HERMES_EXE%" config env-path >nul
if errorlevel 1 goto :failed

call "%NOTEBOOKLM_PY%\.venv\Scripts\python.exe" "%WORKSPACE%scripts\setup_hermes_open_notebook_mcp.py"
if errorlevel 1 goto :failed

echo.
echo Hermes Open Notebook MCP connection configured as "open_notebook".
echo Start a new Hermes session or run /reload-mcp inside Hermes.
exit /b 0

:failed
echo.
echo Hermes MCP setup failed. Review the message above.
pause
exit /b 1
