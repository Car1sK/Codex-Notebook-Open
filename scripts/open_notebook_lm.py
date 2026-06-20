# macOS/Linux cross-platform launcher for OpenNotebookLM.
# Windows users should use OpenNotebookLM.bat — this script will redirect them.
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
        "It ships with Node.js — install Node.js first."
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
    if is_port_listening("127.0.0.1", 5055):
        print("[Start] Open Notebook API port 5055 is already listening; reusing it.")
    else:
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
            print(f"  Cannot signal process {pid} — permission denied.", file=sys.stderr)

        pid_file.unlink()

    if stopped == 0:
        print("[Stop] No running services found (no PID files with live processes).")
    else:
        print(f"[Stop] Stopped {stopped} service(s).")


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def run_check() -> int:
    """Run the local stack check."""
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
        ROOT / "Hermes_agent" / "scripts" / "hermes.exe" if sys.platform == "win32" else ROOT / "Hermes_agent" / ".venv" / "bin" / "hermes",
    ]
    if sys.platform == "win32":
        key_files.append(ROOT / "Hermes_agent" / ".venv" / "Scripts" / "hermes.exe")
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
        print("  (Ollama port 11434 is not listening — skipping model checks)")

    print()
    if issues == 0:
        print("All checks passed.")
    else:
        print(f"{issues} check(s) failed.")
    return issues


# ---------------------------------------------------------------------------
# Usage / help
# ---------------------------------------------------------------------------

def print_usage() -> None:
    print("OpenNotebookLM.sh - macOS/Linux launcher for OpenNotebookLM")
    print()
    print("Usage:")
    print("  ./OpenNotebookLM.sh              Install missing dependencies if needed, then start everything.")
    print("  ./OpenNotebookLM.sh --setup-only Install/repair dependencies, but do not start services.")
    print("  ./OpenNotebookLM.sh --check      Run the local stack check only.")
    print("  ./OpenNotebookLM.sh --stop       Stop services started by this project (via PID files).")
    print("  ./OpenNotebookLM.sh --help       Show this message.")
    print()
    print("Windows users: use OpenNotebookLM.bat instead.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--check", action="store_true")
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

    if sys.platform == "win32":
        print("Windows detected. Please use OpenNotebookLM.bat instead of this script.", file=sys.stderr)
        return 1

    if unknown:
        print(f"ERROR: Unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print_usage()
        return 1

    if args.stop:
        stop_services()
        return 0

    if args.check:
        return run_check()

    # Default: setup + start (or setup-only)

    # Detect if setup is needed
    needs_setup = not BOOTSTRAP_MARKER.exists()
    if not needs_setup:
        # Check for missing runtime markers
        if not venv_python("opennotebook").exists():
            needs_setup = True
        elif not (ROOT / "opennotebook" / "frontend" / "node_modules").exists():
            needs_setup = True
        elif not venv_python("notebooklm-py").exists():
            needs_setup = True

    if needs_setup:
        print("[OpenNotebookLM] First run or incomplete setup detected. Preparing local stack...")
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        prepare_working_copies()
        install_deps(do_ollama_model=True)
        BOOTSTRAP_MARKER.write_text(f"completed={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"[OpenNotebookLM] Setup marker written: {BOOTSTRAP_MARKER}")
    else:
        print("[OpenNotebookLM] Existing setup detected. Skipping dependency installation.")

    if args.setup_only:
        print()
        print("Setup is complete. Run OpenNotebookLM.sh again without arguments to start services.")
        return 0

    print()
    print("[OpenNotebookLM] Starting local stack...")
    start_services()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
