@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "WORKSPACE=%~dp0"
set "NOTEBOOKLM=%WORKSPACE%notebooklm-py"
set "HERMES_EXE=%WORKSPACE%Hermes_agent\.venv\Scripts\hermes.exe"
set "OPEN_NOTEBOOK_PYTHON=%WORKSPACE%opennotebook\.venv\Scripts\python.exe"
set "ENV_FILE=%WORKSPACE%opennotebook\.env"
set "OPEN_NOTEBOOK_URL=http://localhost:5055"
set "OLLAMA_API_BASE=http://127.0.0.1:11434"

echo [Check] OpenNotebookLM local stack
echo.

echo [Check] Ollama local embedding model...
if not exist "%OPEN_NOTEBOOK_PYTHON%" (
  echo ERROR: Open Notebook Python environment was not found at "%OPEN_NOTEBOOK_PYTHON%".
  goto :failed
)
call "%OPEN_NOTEBOOK_PYTHON%" "%WORKSPACE%scripts\check_ollama_models.py"
if errorlevel 1 (
  echo ERROR: Ollama local embedding readiness check failed.
  goto :failed
)

echo [Check] SurrealDB port 8000...
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo ERROR: SurrealDB is not listening on port 8000.
  goto :failed
)
echo OK: SurrealDB is listening on port 8000.

echo [Check] Open Notebook API port 5055...
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 5055 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Open Notebook API is not listening on port 5055.
  goto :failed
)
echo OK: Open Notebook API is listening on port 5055.

echo [Check] Open Notebook frontend port 3000...
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Open Notebook frontend is not listening on port 3000.
  goto :failed
)
echo OK: Open Notebook frontend is listening on port 3000.

if not exist "%NOTEBOOKLM%\pyproject.toml" (
  echo ERROR: notebooklm-py was not found at "%NOTEBOOKLM%".
  goto :failed
)

if not exist "%HERMES_EXE%" (
  echo ERROR: Hermes executable was not found at "%HERMES_EXE%".
  goto :failed
)
echo OK: Hermes executable is available.

if not exist "%ENV_FILE%" (
  echo ERROR: Open Notebook .env was not found.
  goto :failed
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
  if /i "%%A"=="OPEN_NOTEBOOK_PASSWORD" set "OPEN_NOTEBOOK_PASSWORD=%%B"
)

if not defined OPEN_NOTEBOOK_PASSWORD (
  echo ERROR: OPEN_NOTEBOOK_PASSWORD is missing in "%ENV_FILE%".
  goto :failed
)

echo [Check] Codex MCP configuration...
call codex mcp get notebooklm >nul 2>nul
if errorlevel 1 (
  echo ERROR: Codex MCP server "notebooklm" is not configured.
  echo Run setup_codex_open_notebook_mcp.bat.
  goto :failed
)
echo OK: Codex MCP server "notebooklm" is configured.

echo [Check] notebooklm-py Open Notebook API connection...
cd /d "%NOTEBOOKLM%"
call uv run notebooklm open-notebook notebooks --json >nul
if errorlevel 1 (
  echo ERROR: notebooklm-py could not read Open Notebook notebooks.
  goto :failed
)
echo OK: notebooklm-py can read Open Notebook notebooks.

echo [Check] notebooklm-py Open Notebook MCP tool manifest...
call uv run python scripts\check_open_notebook_mcp_tools.py
if errorlevel 1 (
  echo ERROR: notebooklm-py Open Notebook MCP tool manifest is incomplete.
  goto :failed
)

echo [Check] Hermes Open Notebook MCP connection...
cd /d "%WORKSPACE%"
call "%HERMES_EXE%" mcp test open_notebook >nul
if errorlevel 1 (
  echo ERROR: Hermes could not connect to Open Notebook MCP server "open_notebook".
  echo Run setup_hermes_open_notebook_mcp.bat.
  goto :failed
)
echo OK: Hermes can connect to Open Notebook MCP server "open_notebook".

echo [Check] Hermes Open Notebook MCP tool calls...
cd /d "%WORKSPACE%Hermes_agent"
call ".venv\Scripts\python.exe" "%WORKSPACE%scripts\check_hermes_open_notebook_mcp.py"
if errorlevel 1 (
  echo ERROR: Hermes Open Notebook MCP tools could not read notebooks/sources.
  goto :failed
)

echo.
echo Local agent stack check passed.
exit /b 0

:failed
echo.
echo Local agent stack check failed. Review the message above.
pause
exit /b 1
