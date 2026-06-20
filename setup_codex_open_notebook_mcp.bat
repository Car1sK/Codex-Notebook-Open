@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "WORKSPACE=%~dp0"
set "NOTEBOOKLM=%WORKSPACE%notebooklm-py"
set "ENV_FILE=%WORKSPACE%opennotebook\.env"
set "OPEN_NOTEBOOK_URL=http://localhost:5055"

if not exist "%NOTEBOOKLM%\pyproject.toml" (
  echo ERROR: notebooklm-py was not found at "%NOTEBOOKLM%".
  goto :failed
)

if not exist "%ENV_FILE%" (
  echo ERROR: Open Notebook .env was not found.
  echo Start Open Notebook once with start_open_notebook.bat first.
  goto :failed
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
  if /i "%%A"=="OPEN_NOTEBOOK_PASSWORD" set "OPEN_NOTEBOOK_PASSWORD=%%B"
)

if not defined OPEN_NOTEBOOK_PASSWORD (
  echo ERROR: OPEN_NOTEBOOK_PASSWORD is missing in "%ENV_FILE%".
  goto :failed
)

cd /d "%NOTEBOOKLM%"
echo Installing local notebooklm-py MCP server for Codex...
call uv run notebooklm mcp install-codex
if errorlevel 1 goto :failed

echo.
echo Codex MCP connection refreshed. Restart Codex or open a new Codex thread to load it.
exit /b 0

:failed
echo.
echo Setup failed. Review the message above.
pause
exit /b 1
