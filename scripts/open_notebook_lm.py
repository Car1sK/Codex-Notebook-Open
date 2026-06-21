# macOS/Linux cross-platform launcher for OpenNotebookLM.
# Windows users should use OpenNotebookLM.bat -- this script will redirect them.
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "open-notebook-data"
BOOTSTRAP_MARKER = DATA_ROOT / ".bootstrap-complete"

# Project definitions: (target_dir, component_source, has_frontend, marker_file)
PROJECTS = [
    ("opennotebook", "components/opennotebook", True, "pyproject.toml"),
    ("notebooklm-py", "components/notebooklm-py", False, "pyproject.toml"),
    ("Hermes_agent", "components/Hermes_agent", False, "pyproject.toml"),
]

# Ports used by services
SERVICES = {
    "surrealdb": 8000,
    "api": 5055,
    "frontend": 3000,
    "ollama": 11434,
}


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def venv_python(project: str = "opennotebook") -> Path:
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    exe = "python.exe" if sys.platform == "win32" else "python"
    return ROOT / project / ".venv" / scripts / exe


def which(cmd: str) -> str | None:
    """Return the path to *cmd*, or None."""
    path = shutil.which(cmd)
    return path


def load_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines from a dotenv-style file."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def open_notebook_env() -> dict[str, str]:
    """Build the runtime environment used by Open Notebook services."""
    env = os.environ.copy()
    env.update(load_env_file(ROOT / "opennotebook" / ".env"))
    env.setdefault("DATA_FOLDER", str(DATA_ROOT))
    env.setdefault("PYTHONPATH", str(ROOT / "opennotebook"))
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    env.setdefault("SURREAL_URL", "ws://127.0.0.1:8000/rpc")
    env.setdefault("SURREAL_USER", "root")
    env.setdefault("SURREAL_PASSWORD", "root")
    env.setdefault("SURREAL_NAMESPACE", "open_notebook")
    env.setdefault("SURREAL_DATABASE", "open_notebook")
    return env


# ---------------------------------------------------------------------------
# Tool checks
# ---------------------------------------------------------------------------

TOOL_INSTALL_INSTRUCTIONS: dict[str, str] = {
    "uv": (
        "uv is the Python package manager used by this project.\n"
        "Install it with:\n"
        "  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "Or see https://docs.astral.sh/uv/getting-started/installation/"
    ),
    "node": (
        "Node.js is required for the Open Notebook frontend.\n"
        "Install it with your package manager, e.g.:\n"
        "  brew install node        (macOS)\n"
        "  sudo apt install nodejs  (Debian/Ubuntu)"
    ),
    "npm": (
        "npm is required for the Open Notebook frontend.\n"
        "It ships with Node.js -- install Node.js first."
    ),
    "surreal": (
        "SurrealDB CLI is required for the database.\n"
        "Install it with:\n"
        "  curl -sSf https://install.surrealdb.com | sh\n"
        "Or: brew install surrealdb/tap/surreal"
    ),
    "ollama": (
        "Ollama is required for local embeddings.\n"
        "Install it with:\n"
        "  curl -fsSL https://ollama.com/install.sh | sh\n"
        "Or: brew install ollama"
    ),
}


def check_tools() -> dict[str, str | None]:
    """Check required external tools. Returns dict of tool -> path or None."""
    result: dict[str, str | None] = {}
    for tool in ("uv", "node", "npm", "surreal", "ollama"):
        result[tool] = which(tool)
    return result


def print_missing_tools(tools: dict[str, str | None]) -> list[str]:
    """Print actionable install instructions for missing tools."""
    missing: list[str] = []
    for tool, path in tools.items():
        if path is None:
            missing.append(tool)
            print(f"[Setup] {tool}: NOT FOUND")
            if tool in TOOL_INSTALL_INSTRUCTIONS:
                print(f"  {TOOL_INSTALL_INSTRUCTIONS[tool]}")
            print()
        else:
            print(f"[Setup] {tool}: {path}")
    return missing


# ---------------------------------------------------------------------------
# Filesystem setup
# ---------------------------------------------------------------------------

COPY_EXCLUDES: dict[str, set[str]] = {
    "dirs": {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
             ".mypy_cache", ".ruff_cache", ".trial_runtime"},
    "files": {".env", "*.pyc", "*.log", "*.out.log", "*.err.log"},
}


def prepare_working_copies() -> set[str]:
    """Copy project sources from components/ if missing. Returns prepared dirs."""
    prepared: set[str] = set()
    for target_dir, source_dir, has_frontend, marker in PROJECTS:
        target = ROOT / target_dir
        source = ROOT / source_dir
        marker_path = target / marker

        if marker_path.exists():
            print(f"[Setup] {target_dir}/ already looks complete.")
            continue

        if not (source / marker).exists():
            print(f"[Setup] ERROR: Bundled source snapshot missing: {source}", file=sys.stderr)
            raise SystemExit(1)

        print(f"[Setup] Preparing {target_dir}/ from bundled source snapshot...")
        # Remove stale directory if it exists without the marker
        if target.exists():
            shutil.rmtree(target)

        # Use custom copier that skips excluded dirs/files
        _copytree_excluding(source, target)
        prepared.add(target_dir)

    return prepared


def _copytree_excluding(src: Path, dst: Path) -> None:
    """Copy tree from src to dst, skipping excluded directories and files."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in COPY_EXCLUDES["dirs"] and item.is_dir():
            continue
        if item.name in COPY_EXCLUDES["files"]:
            continue
        if item.is_dir():
            _copytree_excluding(item, dst / item.name)
        else:
            dst_file = dst / item.name
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst_file)


# ---------------------------------------------------------------------------
# Dependency installation
# ---------------------------------------------------------------------------

def install_deps(do_ollama_model: bool = True) -> None:
    """Install project dependencies using uv sync and npm ci."""
    tools = check_tools()
    print_missing_tools(tools)

    for tool in ("uv", "node", "npm", "surreal", "ollama"):
        if tools[tool] is None:
            raise SystemExit(f"Missing required tool: {tool}")

    # Sync each Python project
    for target_dir, _source_dir, _has_frontend, marker in PROJECTS:
        proj_dir = ROOT / target_dir
        if not (proj_dir / marker).exists():
            print(f"[Setup] WARNING: {target_dir}/ marker missing; skipping uv sync.", file=sys.stderr)
            continue

        # Check if venv already exists
        vp = venv_python(target_dir)
        if vp.exists():
            print(f"[Setup] Python environment already exists: {target_dir}/")
            continue

        extra = ["--extra", "mcp"] if target_dir in ("notebooklm-py", "Hermes_agent") else []
        print(f"[Setup] Syncing Python environment: {target_dir}/")
        subprocess.run([str(which("uv")), "sync"] + extra, cwd=str(proj_dir), check=True)

    # npm ci for frontend
    frontend_dir = ROOT / "opennotebook" / "frontend"
    if frontend_dir.is_dir() and not (frontend_dir / "node_modules").is_dir():
        print("[Setup] Installing frontend dependencies...")
        subprocess.run([str(which("npm")), "ci"], cwd=str(frontend_dir), check=True)

    # Ensure .env
    ensure_env_script = ROOT / "scripts" / "ensure_open_notebook_env.py"
    if ensure_env_script.exists():
        env_file = ROOT / "opennotebook" / ".env"
        print("[Setup] Ensuring opennotebook/.env...")
        subprocess.run([sys.executable, str(ensure_env_script), str(env_file)], check=True)

    # Ollama model check
    if do_ollama_model:
        _ensure_ollama_model()


def _ensure_ollama_model() -> None:
    """Start Ollama if needed and pull embedding model."""
    if not is_port_listening("127.0.0.1", 11434):
        print("[Setup] Starting Ollama serve...")
        ollama_path = which("ollama")
        if not ollama_path:
            print("WARNING: ollama not found; cannot start serve.", file=sys.stderr)
            return
        subprocess.Popen([ollama_path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if is_port_listening("127.0.0.1", 11434):
                break
            time.sleep(1)
        else:
            print("WARNING: Ollama did not become ready on port 11434.", file=sys.stderr)
            return

    print("[Setup] Ensuring Ollama embedding model exists: nomic-embed-text:latest")
    try:
        result = subprocess.run(
            [str(which("ollama")), "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        result = None

    if result and "nomic-embed-text" in (result.stdout or ""):
        return

    # Pull the model
    subprocess.run(
        [str(which("ollama")), "pull", "nomic-embed-text"],
        check=True,
    )


# ---------------------------------------------------------------------------
# Port helpers
# ---------------------------------------------------------------------------

def is_port_listening(host: str, port: int) -> bool:
    """Check if a TCP port is listening."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def acquire_launcher_lock() -> bool:
    """Acquire a lightweight startup lock; returns False when another start is active."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    lock_dir = DATA_ROOT / "launcher.lock"
    try:
        lock_dir.mkdir()
        return True
    except FileExistsError:
        try:
            if time.time() - lock_dir.stat().st_mtime > 15 * 60:
                lock_dir.rmdir()
                lock_dir.mkdir()
                return True
        except OSError:
            pass
        return False


def release_launcher_lock() -> None:
    """Release the startup lock if this process owns it."""
    lock_dir = DATA_ROOT / "launcher.lock"
    try:
        lock_dir.rmdir()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def wait_for_existing_startup() -> None:
    """Wait for another launcher invocation to finish exposing Open Notebook."""
    print("[Start] Another launcher is already starting Open Notebook; waiting for it.")
    _wait_for_port("127.0.0.1", 5055, 120)
    _wait_for_port("127.0.0.1", 3000, 120)
    print()
    print("OpenNotebookLM is ready.")
    print("Open Notebook: http://localhost:3000")


# ---------------------------------------------------------------------------
# Service management
# ---------------------------------------------------------------------------

def start_services() -> None:
    """Start all four services: SurrealDB, worker, API, frontend."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    vp = venv_python("opennotebook")
    npm_path = which("npm")
    if not npm_path:
        raise SystemExit("npm not found; cannot start frontend.")
    env = open_notebook_env()

    # 1. SurrealDB
    surreal_log = DATA_ROOT / "surrealdb.log"
    surreal_pid = DATA_ROOT / "surrealdb.pid"
    surreal_db_dir = DATA_ROOT / "surrealdb"
    surreal_db_dir.mkdir(parents=True, exist_ok=True)

    api_already_running = is_port_listening("127.0.0.1", 5055)
    if api_already_running:
        print("[Start] Open Notebook backend/API port 5055 is already listening; reusing it.")
    else:
        if is_port_listening("127.0.0.1", 8000):
            print("[Start] SurrealDB port 8000 is already listening; reusing it.")
        else:
            print("[Start] Launching SurrealDB on port 8000...")
            p1 = subprocess.Popen(
                [
                    "surreal", "start",
                    "--user", "root", "--pass", "root",
                    "--bind", "127.0.0.1:8000",
                    "--log", "warn",
                    f"rocksdb:{surreal_db_dir / 'database.db'}",
                ],
                stdout=open(str(surreal_log), "w"),
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
                env=env,
            )
            surreal_pid.write_text(str(p1.pid))

            # Wait for SurrealDB
            print("[Start] Waiting for SurrealDB (port 8000)...")
            _wait_for_port("127.0.0.1", 8000, 30)

        # 2. Worker
        worker_log = DATA_ROOT / "worker.log"
        worker_pid_file = DATA_ROOT / "worker.pid"
        print("[Start] Launching worker...")
        p2 = subprocess.Popen(
            [str(vp), "-m", "surreal_commands.cli.worker", "--import-modules", "commands"],
            stdout=open(str(worker_log), "w"),
            stderr=subprocess.STDOUT,
            cwd=str(ROOT / "opennotebook"),
            env=env,
        )
        worker_pid_file.write_text(str(p2.pid))

        # 3. API
        api_log = DATA_ROOT / "api.log"
        api_pid_file = DATA_ROOT / "api.pid"
        api_entry = ROOT / "opennotebook" / "run_api.py"
        print("[Start] Launching API on port 5055...")
        p3 = subprocess.Popen(
            [str(vp), str(api_entry)],
            stdout=open(str(api_log), "w"),
            stderr=subprocess.STDOUT,
            cwd=str(ROOT / "opennotebook"),
            env=env,
        )
        api_pid_file.write_text(str(p3.pid))

        print("[Start] Waiting for API (port 5055)...")
        _wait_for_port("127.0.0.1", 5055, 30)

    # 4. Frontend
    frontend_log = DATA_ROOT / "frontend.log"
    frontend_pid_file = DATA_ROOT / "frontend.pid"
    if is_port_listening("127.0.0.1", 3000):
        print("[Start] Open Notebook frontend port 3000 is already listening; reusing it.")
    else:
        print("[Start] Launching frontend on port 3000...")
        p4 = subprocess.Popen(
            [npm_path, "run", "dev"],
            stdout=open(str(frontend_log), "w"),
            stderr=subprocess.STDOUT,
            cwd=str(ROOT / "opennotebook" / "frontend"),
            env=env,
        )
        frontend_pid_file.write_text(str(p4.pid))

        print("[Start] Waiting for frontend (port 3000)...")
        _wait_for_port("127.0.0.1", 3000, 60)

    print()
    print("OpenNotebookLM is ready.")
    print("Open Notebook: http://localhost:3000")


def _wait_for_port(host: str, port: int, timeout: int) -> None:
    """Wait up to *timeout* seconds for a port to accept connections."""
    for _ in range(timeout):
        if is_port_listening(host, port):
            return
        time.sleep(1)
    raise SystemExit(f"Port {port} did not become ready within {timeout}s.")


def stop_services() -> None:
    """Stop services using recorded PID files."""
    stopped = 0

    for pid_file in sorted(DATA_ROOT.glob("*.pid")):
        try:
            raw = pid_file.read_text().strip()
            if not raw:
                pid_file.unlink()
                continue
            pid = int(raw)
        except (ValueError, OSError):
            pid_file.unlink()
            continue

        name = pid_file.stem
        print(f"[Stop] Sending SIGTERM to {name} (PID {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
            stopped += 1
        except ProcessLookupError:
            print(f"  Process {pid} already gone.")
        except PermissionError:
            print(f"  Cannot signal process {pid} -- permission denied.", file=sys.stderr)

        pid_file.unlink()

    if stopped == 0:
        print("[Stop] No running services found (no PID files with live processes).")
    else:
        print(f"[Stop] Stopped {stopped} service(s).")


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def _print_path_status(label: str, path: Path, *, required: bool = True) -> bool:
    """Print a path status line. Returns True when the path exists."""
    exists = path.exists()
    if exists:
        status = "OK"
    else:
        status = "MISSING" if required else "PENDING"
    print(f"  [{status}] {label}: {path}")
    return exists


def run_install_check() -> int:
    """Check package/setup readiness without requiring live services."""
    issues = 0
    pending = 0

    print("=== Checking package files ===")
    package_files = [
        ROOT / "OpenNotebookLM.bat",
        ROOT / "OpenNotebookLM.sh",
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "scripts" / "open_notebook_lm.py",
        ROOT / "scripts" / "ensure_open_notebook_env.py",
        ROOT / "scripts" / "build_release.py",
    ]
    for path in package_files:
        if not _print_path_status(path.name, path):
            issues += 1

    print()
    print("=== Checking bundled source snapshots ===")
    for target_dir, source_dir, _has_frontend, marker in PROJECTS:
        marker_path = ROOT / source_dir / marker
        if not _print_path_status(f"{target_dir} source snapshot", marker_path):
            issues += 1

    print()
    print("=== Checking prepared runtime working copies ===")
    for target_dir, _source_dir, _has_frontend, marker in PROJECTS:
        marker_path = ROOT / target_dir / marker
        if not _print_path_status(f"{target_dir} runtime copy", marker_path, required=False):
            pending += 1
    frontend_modules = ROOT / "opennotebook" / "frontend" / "node_modules"
    if not _print_path_status("Open Notebook frontend dependencies", frontend_modules, required=False):
        pending += 1
    if not _print_path_status("Open Notebook Python environment", venv_python("opennotebook"), required=False):
        pending += 1

    print()
    print("=== Checking external tools visible now ===")
    tools = check_tools()
    missing_tools: list[str] = []
    for tool, path in tools.items():
        status = "OK" if path else "MISSING"
        if not path:
            missing_tools.append(tool)
        print(f"  [{status}] {tool}: {path or 'not found'}")

    if sys.platform == "win32" and any(tool in missing_tools for tool in ("node", "npm", "surreal", "ollama")):
        winget_path = which("winget")
        status = "OK" if winget_path else "MISSING"
        print(f"  [{status}] winget: {winget_path or 'not found'}")
        if winget_path is None:
            issues += 1
    elif sys.platform != "win32" and missing_tools:
        issues += len(missing_tools)

    print()
    if pending:
        setup_cmd = "OpenNotebookLM.bat --setup-only" if sys.platform == "win32" else "./OpenNotebookLM.sh --setup-only"
        print(
            f"{pending} setup item(s) are not prepared yet. "
            f"Run {setup_cmd} before starting services."
        )
    if issues == 0:
        print("Install/package check passed.")
    else:
        print(f"{issues} install/package check(s) failed.")
    return issues


def run_check() -> int:
    """Run the live local stack check."""
    issues = 0

    # 1. Key files
    print("=== Checking key files ===")
    key_files = [
        ROOT / "opennotebook" / "pyproject.toml",
        ROOT / "opennotebook" / "run_api.py",
        ROOT / "opennotebook" / "frontend" / "package-lock.json",
        ROOT / "notebooklm-py" / "pyproject.toml",
        ROOT / "Hermes_agent" / "pyproject.toml",
        venv_python("opennotebook"),
        _hermes_executable(),
    ]
    for f in key_files:
        status = "OK" if f.exists() else "MISSING"
        if not f.exists():
            issues += 1
        print(f"  [{status}] {f}")

    # 2. Required commands
    print()
    print("=== Checking required commands ===")
    tools = check_tools()
    for tool, path in tools.items():
        status = "OK" if path else "MISSING"
        if not path:
            issues += 1
        print(f"  [{status}] {tool}: {path or 'not found'}")

    # 3. Ports
    print()
    print("=== Checking ports ===")
    for name, port in SERVICES.items():
        listening = is_port_listening("127.0.0.1", port)
        status = "LISTENING" if listening else "CLOSED"
        print(f"  [{status}] {name}: {port}")

    # 4. Ollama embedding check (only if port 11434 is listening)
    if is_port_listening("127.0.0.1", 11434):
        print()
        print("=== Checking Ollama models ===")
        check_script = ROOT / "scripts" / "check_ollama_models.py"
        if check_script.exists():
            result = subprocess.run(
                [sys.executable, str(check_script)],
                capture_output=True, text=True, timeout=60,
            )
            print(result.stdout, end="")
            if result.returncode != 0:
                issues += 1
        else:
            print("  WARNING: check_ollama_models.py not found", file=sys.stderr)
            issues += 1
    else:
        print()
        print("  (Ollama port 11434 is not listening -- skipping model checks)")

    print()
    print("=== Checking Codex MCP configuration ===")
    try:
        result = subprocess.run(
            ["codex", "mcp", "get", "notebooklm"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"  [MISSING] Codex MCP check could not run: {exc}")
        issues += 1
    else:
        if result.returncode == 0:
            print('  [OK] Codex MCP server "notebooklm" is configured.')
        else:
            print('  [MISSING] Codex MCP server "notebooklm" is not configured.')
            issues += 1

    print()
    print("=== Checking notebooklm-py Open Notebook bridge ===")
    notebooklm_dir = ROOT / "notebooklm-py"
    if notebooklm_dir.is_dir() and which("uv"):
        env = _open_notebook_auth_env()
        notebooks = subprocess.run(
            ["uv", "run", "notebooklm", "open-notebook", "notebooks", "--json"],
            cwd=str(notebooklm_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if notebooks.returncode == 0:
            print("  [OK] notebooklm-py can read Open Notebook notebooks.")
        else:
            print("  [FAILED] notebooklm-py could not read Open Notebook notebooks.")
            issues += 1

        manifest = subprocess.run(
            ["uv", "run", "python", "scripts/check_open_notebook_mcp_tools.py"],
            cwd=str(notebooklm_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if manifest.returncode == 0:
            print("  [OK] notebooklm-py Open Notebook MCP tool manifest is complete.")
        else:
            print("  [FAILED] notebooklm-py Open Notebook MCP tool manifest is incomplete.")
            issues += 1
    else:
        print("  [MISSING] notebooklm-py runtime or uv was not found.")
        issues += 1

    print()
    print("=== Checking Hermes Open Notebook MCP connection ===")
    hermes_exe = _hermes_executable()
    if hermes_exe.exists():
        test = subprocess.run(
            [str(hermes_exe), "mcp", "test", "open_notebook"],
            cwd=str(ROOT),
            env=_open_notebook_auth_env(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if test.returncode == 0:
            print('  [OK] Hermes can connect to MCP server "open_notebook".')
        else:
            print('  [FAILED] Hermes could not connect to MCP server "open_notebook".')
            issues += 1

        hermes_python = venv_python("Hermes_agent")
        checker = ROOT / "scripts" / "check_hermes_open_notebook_mcp.py"
        if hermes_python.exists() and checker.exists():
            tool_call = subprocess.run(
                [str(hermes_python), str(checker)],
                cwd=str(ROOT / "Hermes_agent"),
                env=_open_notebook_auth_env(),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if tool_call.returncode == 0:
                print("  [OK] Hermes Open Notebook MCP tools can list state.")
            else:
                print("  [FAILED] Hermes Open Notebook MCP tool calls failed.")
                issues += 1
        else:
            print("  [MISSING] Hermes Python environment or MCP checker is missing.")
            issues += 1
    else:
        print(f"  [MISSING] Hermes executable: {hermes_exe}")
        issues += 1

    print()
    if issues == 0:
        print("All checks passed.")
    else:
        print(f"{issues} check(s) failed.")
    return issues


def _open_notebook_auth_env() -> dict[str, str]:
    """Return an environment with Open Notebook auth variables loaded."""
    env = os.environ.copy()
    env.update(load_env_file(ROOT / "opennotebook" / ".env"))
    env.setdefault("OPEN_NOTEBOOK_URL", "http://localhost:5055")
    if "LOCALAPPDATA" in env:
        env.setdefault("HERMES_HOME", str(Path(env["LOCALAPPDATA"]) / "hermes"))
    else:
        env.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
    return env


def _hermes_executable() -> Path:
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    exe = "hermes.exe" if sys.platform == "win32" else "hermes"
    return ROOT / "Hermes_agent" / ".venv" / scripts / exe


def setup_codex_mcp() -> int:
    """Install or refresh the notebooklm-py MCP server for Codex."""
    notebooklm_dir = ROOT / "notebooklm-py"
    if not notebooklm_dir.is_dir():
        print(f"ERROR: notebooklm-py was not found at {notebooklm_dir}", file=sys.stderr)
        return 1
    if not (ROOT / "opennotebook" / ".env").is_file():
        print("ERROR: opennotebook/.env is missing. Run setup first.", file=sys.stderr)
        return 1
    if not which("uv"):
        print("ERROR: uv is missing.", file=sys.stderr)
        return 1

    print("[MCP] Installing local notebooklm-py MCP server for Codex...")
    result = subprocess.run(
        ["uv", "run", "notebooklm", "mcp", "install-codex"],
        cwd=str(notebooklm_dir),
        env=_open_notebook_auth_env(),
        check=False,
    )
    if result.returncode == 0:
        print("[MCP] Codex MCP connection refreshed. Restart Codex or open a new thread if needed.")
    return result.returncode


def setup_hermes_mcp() -> int:
    """Install or refresh the Open Notebook MCP server for Hermes."""
    hermes_dir = ROOT / "Hermes_agent"
    hermes_exe = _hermes_executable()
    notebooklm_python = venv_python("notebooklm-py")
    if not hermes_exe.exists():
        print(f"ERROR: Hermes executable was not found at {hermes_exe}", file=sys.stderr)
        return 1
    if not notebooklm_python.exists():
        print(f"ERROR: notebooklm-py Python environment was not found at {notebooklm_python}", file=sys.stderr)
        return 1
    if not (ROOT / "opennotebook" / ".env").is_file():
        print("ERROR: opennotebook/.env is missing. Run setup first.", file=sys.stderr)
        return 1

    hermes_python = venv_python("Hermes_agent")
    if not hermes_python.exists():
        print(f"ERROR: Hermes Python environment was not found at {hermes_python}", file=sys.stderr)
        return 1

    print("[MCP] Ensuring Hermes MCP support is installed...")
    has_mcp = subprocess.run(
        [str(hermes_python), "-c", "import mcp"],
        cwd=str(hermes_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if has_mcp.returncode != 0:
        if not which("uv"):
            print("ERROR: uv is missing.", file=sys.stderr)
            return 1
        sync = subprocess.run(["uv", "sync", "--extra", "mcp"], cwd=str(hermes_dir), check=False)
        if sync.returncode != 0:
            return sync.returncode

    env = _open_notebook_auth_env()
    for command in ([str(hermes_exe), "config", "path"], [str(hermes_exe), "config", "env-path"]):
        result = subprocess.run(command, cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, check=False)
        if result.returncode != 0:
            return result.returncode

    print("[MCP] Installing Open Notebook MCP server for Hermes...")
    result = subprocess.run(
        [str(notebooklm_python), str(ROOT / "scripts" / "setup_hermes_open_notebook_mcp.py")],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    if result.returncode == 0:
        print('[MCP] Hermes Open Notebook MCP connection configured as "open_notebook".')
    return result.returncode


def start_hermes(args: list[str] | None = None) -> int:
    """Start Hermes in a separate Windows terminal when possible."""
    args = args or []
    hermes_exe = _hermes_executable()
    if not hermes_exe.exists():
        print(f"ERROR: Hermes executable was not found at {hermes_exe}", file=sys.stderr)
        return 1

    if sys.platform == "win32":
        run_script = ROOT / "scripts" / "hermes_runtime.ps1"
        if not run_script.exists():
            print(f"ERROR: Hermes runtime script was not found at {run_script}", file=sys.stderr)
            return 1
        wt = which("wt.exe")
        command = [
            "powershell.exe", "-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass",
            "-File", str(run_script), "-Action", "start", *args,
        ]
        if wt:
            subprocess.Popen([wt, "-w", "0", "new-tab", "--title", "Hermes Agent", *command], cwd=str(ROOT))
            print("[Hermes] Started in Windows Terminal.")
            return 0
        subprocess.Popen(command, cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        print("[Hermes] Started in PowerShell.")
        return 0

    env = _open_notebook_auth_env()
    subprocess.Popen([str(hermes_exe), *args], cwd=str(ROOT / "Hermes_agent"), env=env)
    print("[Hermes] Started.")
    return 0


def stop_hermes() -> int:
    """Stop Hermes processes for this local checkout."""
    if sys.platform == "win32":
        run_script = ROOT / "scripts" / "hermes_runtime.ps1"
        if not run_script.exists():
            print(f"ERROR: Hermes runtime script was not found at {run_script}", file=sys.stderr)
            return 1
        return subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(run_script), "-Action", "stop",
            ],
            cwd=str(ROOT),
            check=False,
        ).returncode

    # Best effort for POSIX: stop PID-recorded services only.
    stop_services()
    return 0


# ---------------------------------------------------------------------------
# Windows helpers
# ---------------------------------------------------------------------------

_WINDOWS_EXTRA_PATHS = [
    r"%APPDATA%\Python\Python313\Scripts",
    r"%USERPROFILE%\.local\bin",
    r"%USERPROFILE%\.cargo\bin",
    r"C:\nvm4w\nodejs",
    r"C:\Program Files\nodejs",
    r"%LOCALAPPDATA%\Programs\Ollama",
]

_WINGET_PACKAGES: dict[str, tuple[str, str]] = {
    "node": ("OpenJS.NodeJS.LTS", "Node.js LTS"),
    "surreal": ("SurrealDB.SurrealDB", "SurrealDB"),
    "ollama": ("Ollama.Ollama", "Ollama"),
}


def _prepare_windows_path() -> None:
    """Add common Windows tool directories to PATH."""
    added: list[str] = []
    for raw in _WINDOWS_EXTRA_PATHS:
        expanded = os.path.expandvars(raw)
        if os.path.isdir(expanded) and expanded not in os.environ.get("PATH", ""):
            added.append(expanded)
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")


def _ensure_windows_tools() -> None:
    """Check and optionally install external tools on Windows via winget."""
    print("[Setup] Checking external tools...")
    tools = check_tools()

    # uv - try PowerShell install if missing
    if tools["uv"] is None:
        print("[Setup] uv not found. Installing uv...")
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", "irm https://astral.sh/uv/install.ps1 | iex",
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print("WARNING: uv installation failed.", file=sys.stderr)
            print(TOOL_INSTALL_INSTRUCTIONS["uv"])
        else:
            _prepare_windows_path()
            tools["uv"] = which("uv")

    # node, surreal, ollama - winget
    for tool, (winget_id, label) in _WINGET_PACKAGES.items():
        if tools[tool] is not None:
            continue
        print(f"[Setup] {label} not found. Installing {label} with winget...")
        winget_path = which("winget")
        if winget_path is None:
            print(f"WARNING: winget is not available; cannot install {label} automatically.", file=sys.stderr)
            if tool in TOOL_INSTALL_INSTRUCTIONS:
                print(TOOL_INSTALL_INSTRUCTIONS[tool])
            continue

        result = subprocess.run(
            [
                winget_path, "install", "-e", "--id", winget_id,
                "--accept-source-agreements", "--accept-package-agreements",
            ],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"WARNING: {label} installation failed.", file=sys.stderr)
            if tool in TOOL_INSTALL_INSTRUCTIONS:
                print(TOOL_INSTALL_INSTRUCTIONS[tool])
        else:
            _prepare_windows_path()
            tools[tool] = which(tool)

    # Re-check after installs
    missing = print_missing_tools(tools)
    if missing:
        raise SystemExit(
            f"Missing required tool(s): {', '.join(missing)}. "
            "Install them manually and retry."
        )


# ---------------------------------------------------------------------------
# Usage / help
# ---------------------------------------------------------------------------

def print_usage() -> None:
    print("OpenNotebookLM - cross-platform launcher")
    print()
    print("Usage:")
    print("  On macOS/Linux:    ./OpenNotebookLM.sh [flags]")
    print("  On Windows:        OpenNotebookLM.bat [flags]")
    print()
    print("Flags:")
    print("  --setup-only   Install/repair dependencies, but do not start services.")
    print("  --force-setup  Re-run setup checks for missing pieces, then start services.")
    print("  --check        Check package/setup readiness; does not require live services.")
    print("  --check-install  Alias for --check.")
    print("  --check-live   Check the running local stack, ports, and integrations.")
    print("  --start-open-notebook  Start Ollama and Open Notebook only.")
    print("  --setup-codex-mcp  Refresh the Codex MCP connection.")
    print("  --setup-hermes-mcp  Refresh the Hermes MCP connection.")
    print("  --start-hermes  Start Hermes in a separate terminal.")
    print("  --stop-hermes   Stop Hermes processes for this checkout.")
    print("  --stop         Stop services started by this project via PID files.")
    print("  --help, -h     Show this message.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--force-setup", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-install", action="store_true")
    parser.add_argument("--check-live", action="store_true")
    parser.add_argument("--start-open-notebook", action="store_true")
    parser.add_argument("--setup-codex-mcp", action="store_true")
    parser.add_argument("--setup-hermes-mcp", action="store_true")
    parser.add_argument("--start-hermes", action="store_true")
    parser.add_argument("--stop-hermes", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--help", action="store_true")
    parser.add_argument("-h", action="store_true")

    try:
        args, unknown = parser.parse_known_args()
    except SystemExit:
        print_usage()
        return 1

    if args.help or args.h:
        print_usage()
        return 0

    if unknown:
        print(f"ERROR: Unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print_usage()
        return 1

    exclusive = [
        args.check or args.check_install,
        args.check_live,
        args.start_open_notebook,
        args.setup_codex_mcp,
        args.setup_hermes_mcp,
        args.start_hermes,
        args.stop_hermes,
        args.stop,
    ]
    if sum(1 for flag in exclusive if flag) > 1:
        print("ERROR: Use only one action flag at a time.", file=sys.stderr)
        print_usage()
        return 1

    if sys.platform == "win32":
        _prepare_windows_path()

    if args.stop:
        stop_services()
        return 0

    if args.stop_hermes:
        return stop_hermes()

    if args.check or args.check_install:
        return run_install_check()

    if args.check_live:
        return run_check()

    if args.setup_codex_mcp:
        return setup_codex_mcp()

    if args.setup_hermes_mcp:
        return setup_hermes_mcp()

    if args.start_hermes:
        return start_hermes()

    # Default: setup + start (or setup-only)

    # Detect if setup is needed
    needs_setup = args.force_setup or not BOOTSTRAP_MARKER.exists()
    if not needs_setup:
        # Check for missing runtime markers
        if not venv_python("opennotebook").exists():
            needs_setup = True
        elif not (ROOT / "opennotebook" / "frontend" / "node_modules").exists():
            needs_setup = True
        elif not venv_python("notebooklm-py").exists():
            needs_setup = True
        elif sys.platform == "win32" and not venv_python("Hermes_agent").exists():
            needs_setup = True

    if needs_setup:
        print("[OpenNotebookLM] First run or incomplete setup detected. Preparing local stack...")
        DATA_ROOT.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            _ensure_windows_tools()

        prepare_working_copies()
        install_deps(do_ollama_model=True)
        BOOTSTRAP_MARKER.write_text(f"completed={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"[OpenNotebookLM] Setup marker written: {BOOTSTRAP_MARKER}")
    else:
        print("[OpenNotebookLM] Existing setup detected. Skipping dependency installation.")

    if args.setup_only:
        print()
        launch_cmd = "OpenNotebookLM.bat" if sys.platform == "win32" else "./OpenNotebookLM.sh"
        print(f"Setup is complete. Run {launch_cmd} again without arguments to start services.")
        return 0

    print()
    print("[OpenNotebookLM] Starting local stack...")
    _ensure_ollama_model()

    lock_acquired = acquire_launcher_lock()
    if not lock_acquired:
        wait_for_existing_startup()
        return 0
    try:
        start_services()
    finally:
        release_launcher_lock()
    if args.start_open_notebook:
        return 0

    codex_result = setup_codex_mcp()
    hermes_mcp_result = setup_hermes_mcp()
    hermes_result = start_hermes()
    return codex_result or hermes_mcp_result or hermes_result


if __name__ == "__main__":
    raise SystemExit(main())
