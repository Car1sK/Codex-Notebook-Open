@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "WORKSPACE=%~dp0"

echo [OpenNotebookLM] Starting/checking Ollama local models...
call "%WORKSPACE%start_ollama_models.bat"
if errorlevel 1 goto :failed

echo.
echo [OpenNotebookLM] Starting Open Notebook...
call "%WORKSPACE%start_open_notebook.bat"
if errorlevel 1 goto :failed

echo.
echo [OpenNotebookLM] Refreshing Codex MCP connection...
call "%WORKSPACE%setup_codex_open_notebook_mcp.bat"
if errorlevel 1 goto :failed

echo.
echo [OpenNotebookLM] Refreshing Hermes MCP connection...
call "%WORKSPACE%setup_hermes_open_notebook_mcp.bat"
if errorlevel 1 goto :failed

echo.
echo [OpenNotebookLM] Starting Hermes...
call "%WORKSPACE%start_hermes.bat"
if errorlevel 1 goto :failed

echo.
echo Local agent stack started.
echo Open Notebook: http://localhost:3000
echo Codex MCP: notebooklm configured. Restart Codex or open a new thread if tools are not visible yet.
exit /b 0

:failed
echo.
echo Local agent stack startup failed. Review the message above.
pause
exit /b 1
