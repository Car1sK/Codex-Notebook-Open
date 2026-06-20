@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "WORKSPACE=%~dp0"
set "DATA_ROOT=%WORKSPACE%open-notebook-data"
set "BOOTSTRAP_MARKER=%DATA_ROOT%\.bootstrap-complete"
set "FORCE_SETUP=0"
set "SETUP_ONLY=0"
set "ACTION=start"

call :parse_args %*
if errorlevel 1 exit /b 1
if /i "%ACTION%"=="usage" goto :usage
if /i "%ACTION%"=="check" goto :check_only

echo [OpenNotebookLM] Unified launcher
echo Workspace: "%WORKSPACE%"

call :detect_first_run
if "%FIRST_RUN%"=="1" (
  echo.
  echo [OpenNotebookLM] First run or incomplete setup detected. Preparing local stack...
  call :bootstrap
  if errorlevel 1 goto :failed
) else (
  echo.
  echo [OpenNotebookLM] Existing setup detected. Skipping dependency installation.
)

if "%SETUP_ONLY%"=="1" (
  echo.
  echo Setup is complete. Run OpenNotebookLM.bat again without arguments to start services.
  exit /b 0
)

echo.
echo [OpenNotebookLM] Starting local stack...
call "%WORKSPACE%start_local_agent_stack.bat"
if errorlevel 1 goto :failed

echo.
echo OpenNotebookLM is ready.
echo Open Notebook: http://localhost:3000
exit /b 0

:usage
echo OpenNotebookLM.bat
echo.
echo Usage:
echo   OpenNotebookLM.bat              Install missing dependencies if needed, then start everything.
echo   OpenNotebookLM.bat --setup-only Install/repair dependencies, but do not start services.
echo   OpenNotebookLM.bat --force-setup Re-run setup checks for missing pieces, then start services.
echo   OpenNotebookLM.bat --check      Run the local stack check only.
exit /b 0

:check_only
call "%WORKSPACE%check_local_agent_stack.bat"
exit /b %errorlevel%

:parse_args
if "%~1"=="" exit /b 0
if /i "%~1"=="--help" set "ACTION=usage"& exit /b 0
if /i "%~1"=="-h" set "ACTION=usage"& exit /b 0
if /i "%~1"=="/?" set "ACTION=usage"& exit /b 0
if /i "%~1"=="--check" set "ACTION=check"& exit /b 0
if /i "%~1"=="--setup-only" set "SETUP_ONLY=1"& shift & goto :parse_args
if /i "%~1"=="--force-setup" set "FORCE_SETUP=1"& shift & goto :parse_args
echo ERROR: Unknown argument "%~1".
echo.
set "ACTION=usage"
exit /b 1

:detect_first_run
set "FIRST_RUN=0"
if "%FORCE_SETUP%"=="1" set "FIRST_RUN=1"
if not exist "%BOOTSTRAP_MARKER%" set "FIRST_RUN=1"
if not exist "%WORKSPACE%opennotebook\.venv\Scripts\python.exe" set "FIRST_RUN=1"
if not exist "%WORKSPACE%opennotebook\frontend\node_modules" set "FIRST_RUN=1"
if not exist "%WORKSPACE%notebooklm-py\.venv\Scripts\python.exe" set "FIRST_RUN=1"
if not exist "%WORKSPACE%Hermes_agent\.venv\Scripts\hermes.exe" set "FIRST_RUN=1"
exit /b 0

:bootstrap
if not exist "%DATA_ROOT%" mkdir "%DATA_ROOT%"

call :prepare_path
call :ensure_external_tools
if errorlevel 1 exit /b 1

call :ensure_project_folder "opennotebook" "pyproject.toml" "https://github.com/lfnovo/open-notebook.git"
if errorlevel 1 exit /b 1
call :ensure_project_folder "notebooklm-py" "pyproject.toml" "https://github.com/teng-lin/notebooklm-py.git"
if errorlevel 1 exit /b 1
call :ensure_project_folder "Hermes_agent" "pyproject.toml" "https://github.com/NousResearch/hermes-agent.git"
if errorlevel 1 exit /b 1
call :validate_project_files
if errorlevel 1 exit /b 1

call :sync_uv_project "%WORKSPACE%opennotebook" "" "%WORKSPACE%opennotebook\.venv\Scripts\python.exe"
if errorlevel 1 exit /b 1
call :sync_frontend
if errorlevel 1 exit /b 1
call :sync_uv_project "%WORKSPACE%notebooklm-py" "--extra mcp" "%WORKSPACE%notebooklm-py\.venv\Scripts\python.exe"
if errorlevel 1 exit /b 1
call :validate_notebooklm_bridge
if errorlevel 1 exit /b 1

call :stop_hermes_before_setup
call :sync_uv_project "%WORKSPACE%Hermes_agent" "--extra mcp" "%WORKSPACE%Hermes_agent\.venv\Scripts\hermes.exe"
if errorlevel 1 exit /b 1

call :ensure_ollama_model
if errorlevel 1 exit /b 1

>"%BOOTSTRAP_MARKER%" echo completed=%date% %time%
echo [OpenNotebookLM] Setup marker written: "%BOOTSTRAP_MARKER%"
exit /b 0

:prepare_path
set "PATH=%APPDATA%\Python\Python313\Scripts;%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;C:\nvm4w\nodejs;C:\Program Files\nodejs;%LOCALAPPDATA%\Programs\Ollama;%PATH%"
exit /b 0

:ensure_external_tools
call :ensure_uv
if errorlevel 1 exit /b 1
call :ensure_node
if errorlevel 1 exit /b 1
call :ensure_surreal
if errorlevel 1 exit /b 1
call :ensure_ollama
if errorlevel 1 exit /b 1
exit /b 0

:ensure_uv
where uv.exe >nul 2>nul
if not errorlevel 1 exit /b 0
where uv >nul 2>nul
if not errorlevel 1 exit /b 0
echo [Setup] uv not found. Installing uv...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 (
  echo ERROR: uv installation failed.
  exit /b 1
)
call :prepare_path
where uv.exe >nul 2>nul
if errorlevel 1 where uv >nul 2>nul
if errorlevel 1 (
  echo ERROR: uv is still not available after installation. Open a new terminal and retry.
  exit /b 1
)
exit /b 0

:ensure_node
where node.exe >nul 2>nul
if errorlevel 1 goto :install_node
where npm.cmd >nul 2>nul
if errorlevel 1 goto :install_node
exit /b 0
:install_node
echo [Setup] Node.js/npm not found. Installing Node.js LTS with winget...
call :winget_install "OpenJS.NodeJS.LTS" "Node.js LTS"
if errorlevel 1 exit /b 1
call :prepare_path
where node.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js is still not available after installation. Open a new terminal and retry.
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm is still not available after installation. Open a new terminal and retry.
  exit /b 1
)
exit /b 0

:ensure_surreal
where surreal.exe >nul 2>nul
if not errorlevel 1 exit /b 0
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages\SurrealDB.SurrealDB_Microsoft.Winget.Source_8wekyb3d8bbwe\surreal.exe" exit /b 0
echo [Setup] SurrealDB not found. Installing SurrealDB with winget...
call :winget_install "SurrealDB.SurrealDB" "SurrealDB"
if errorlevel 1 exit /b 1
exit /b 0

:ensure_ollama
where ollama.exe >nul 2>nul
if not errorlevel 1 exit /b 0
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" exit /b 0
echo [Setup] Ollama not found. Installing Ollama with winget...
call :winget_install "Ollama.Ollama" "Ollama"
if errorlevel 1 exit /b 1
call :prepare_path
where ollama.exe >nul 2>nul
if errorlevel 1 if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
  echo ERROR: Ollama is still not available after installation. Open a new terminal and retry.
  exit /b 1
)
exit /b 0

:winget_install
where winget.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: %~2 is required, and winget is not available for automatic installation.
  exit /b 1
)
winget install -e --id %~1 --accept-source-agreements --accept-package-agreements
exit /b %errorlevel%

:ensure_project_folder
set "PROJECT_NAME=%~1"
set "PROJECT_MARKER=%~2"
set "PROJECT_URL=%~3"
set "PROJECT_DIR=%WORKSPACE%%PROJECT_NAME%"
set "COMPONENT_DIR=%WORKSPACE%components\%PROJECT_NAME%"
if exist "%PROJECT_DIR%\%PROJECT_MARKER%" exit /b 0
if exist "%PROJECT_DIR%" (
  echo ERROR: "%PROJECT_DIR%" exists but does not look like the expected project folder.
  exit /b 1
)
if exist "%COMPONENT_DIR%\%PROJECT_MARKER%" (
  echo [Setup] Preparing %PROJECT_NAME% from bundled source snapshot...
  robocopy "%COMPONENT_DIR%" "%PROJECT_DIR%" /E /XD .git .venv node_modules __pycache__ .pytest_cache .mypy_cache .ruff_cache .trial_runtime /XF *.pyc *.log *.out.log *.err.log .env >nul
  if errorlevel 8 (
    echo ERROR: Could not prepare "%PROJECT_NAME%" from bundled source snapshot.
    exit /b 1
  )
  exit /b 0
)
where git.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: "%PROJECT_NAME%" is missing and Git is not available to clone it.
  exit /b 1
)
echo [Setup] Cloning %PROJECT_NAME%...
git clone "%PROJECT_URL%" "%PROJECT_DIR%"
exit /b %errorlevel%

:validate_project_files
call :require_file "%WORKSPACE%opennotebook\run_api.py" "Open Notebook API entrypoint"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%opennotebook\frontend\package-lock.json" "Open Notebook frontend dependency lockfile"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%notebooklm-py\src\notebooklm\open_notebook.py" "notebooklm-py Open Notebook API bridge"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%notebooklm-py\src\notebooklm\cli\open_notebook_cmd.py" "notebooklm-py Open Notebook CLI commands"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%notebooklm-py\src\notebooklm\mcp\open_notebook.py" "notebooklm-py Open Notebook MCP server"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%notebooklm-py\src\notebooklm\mcp\tools\open_notebook.py" "notebooklm-py Open Notebook MCP tools"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%Hermes_agent\hermes_cli\main.py" "Hermes CLI entrypoint"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%scripts\setup_hermes_open_notebook_mcp.py" "Hermes Open Notebook MCP setup helper"
if errorlevel 1 exit /b 1
call :require_file "%WORKSPACE%scripts\check_ollama_models.py" "Ollama model check helper"
if errorlevel 1 exit /b 1
exit /b 0

:require_file
if exist "%~1" exit /b 0
echo ERROR: Missing %~2: "%~1"
exit /b 1

:validate_notebooklm_bridge
echo [Setup] Verifying notebooklm-py Open Notebook bridge...
pushd "%WORKSPACE%notebooklm-py" >nul
call uv run notebooklm open-notebook --help >nul 2>nul
set "BRIDGE_EXIT=%errorlevel%"
popd >nul
if not "%BRIDGE_EXIT%"=="0" (
  echo ERROR: notebooklm-py does not expose the required "open-notebook" CLI group.
  exit /b 1
)
exit /b 0

:sync_uv_project
set "PROJECT_DIR=%~1"
set "UV_ARGS=%~2"
set "CHECK_FILE=%~3"
if exist "%CHECK_FILE%" (
  echo [Setup] Python environment already exists: "%PROJECT_DIR%"
  exit /b 0
)
echo [Setup] Syncing Python environment: "%PROJECT_DIR%"
pushd "%PROJECT_DIR%" >nul
call uv sync %UV_ARGS%
set "SYNC_EXIT=%errorlevel%"
popd >nul
exit /b %SYNC_EXIT%

:sync_frontend
set "FRONTEND_DIR=%WORKSPACE%opennotebook\frontend"
if exist "%FRONTEND_DIR%\node_modules" (
  echo [Setup] Frontend dependencies already exist.
  exit /b 0
)
if not exist "%FRONTEND_DIR%\package-lock.json" (
  echo ERROR: Open Notebook frontend package-lock.json was not found.
  exit /b 1
)
echo [Setup] Installing frontend dependencies...
pushd "%FRONTEND_DIR%" >nul
call npm.cmd ci
set "NPM_EXIT=%errorlevel%"
popd >nul
exit /b %NPM_EXIT%

:stop_hermes_before_setup
if exist "%WORKSPACE%scripts\hermes_runtime.ps1" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%WORKSPACE%scripts\hermes_runtime.ps1" -Action stop >nul 2>nul
)
exit /b 0

:ensure_ollama_model
set "OLLAMA_EXE=ollama.exe"
where ollama.exe >nul 2>nul
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
call :is_port_listening 11434
if errorlevel 1 (
  echo [Setup] Starting Ollama service...
  start "Ollama" /min "%OLLAMA_EXE%" serve
  call :wait_for_port 11434 60
  if errorlevel 1 (
    echo ERROR: Ollama did not become ready on port 11434.
    exit /b 1
  )
)
echo [Setup] Ensuring Ollama embedding model exists: nomic-embed-text:latest
"%OLLAMA_EXE%" list | findstr /i /c:"nomic-embed-text" >nul
if not errorlevel 1 exit /b 0
"%OLLAMA_EXE%" pull nomic-embed-text
exit /b %errorlevel%

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
echo OpenNotebookLM launcher failed. Review the message above.
pause
exit /b 1
