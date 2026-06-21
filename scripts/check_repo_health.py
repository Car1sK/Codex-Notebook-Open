from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROOT_TEXT_SUFFIXES = {".bat", ".md", ".ps1", ".sh"}
ROOT_TEXT_NAMES = {".gitignore", "LICENSE"}
SCRIPT_TEXT_SUFFIXES = {".py", ".ps1"}

MOJIBAKE_MARKERS = [
    chr(codepoint)
    for codepoint in (
        0xFFFD,  # replacement character
        0x6D93,
        0x93C4,
        0x951B,
        0x9225,
        0x625C,
        0x629C,
    )
]

REQUIRED_GITIGNORE_LINES = [
    ".env",
    "**/.env",
    "open-notebook-data/",
    "/Hermes_agent/",
    "/notebooklm-py/",
    "/opennotebook/",
    "AGENTS.md",
    "**/AGENTS.md",
    "**/.venv/",
    "**/node_modules/",
    "**/__pycache__/",
    "dist/",
]

FORBIDDEN_TRACKED_PREFIXES = [
    "open-notebook-data/",
    "opennotebook/",
    "notebooklm-py/",
    "Hermes_agent/",
    "dist/",
]

FORBIDDEN_TRACKED_FILES = {
    "check_local_agent_stack.bat",
    "hermes.bat",
    "setup_codex_open_notebook_mcp.bat",
    "setup_hermes_open_notebook_mcp.bat",
    "start_hermes.bat",
    "start_local_agent_stack.bat",
    "start_ollama_models.bat",
    "start_open_notebook.bat",
    "stop_hermes.bat",
}

FORBIDDEN_BAT_LABELS = [
    ":bootstrap",
    ":detect_first_run",
    ":ensure_external_tools",
    ":sync_uv_project",
]


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def check_readmes() -> None:
    english = read_text("README.md")
    chinese = read_text("README.zh-CN.md")

    if "English | [中文](README.zh-CN.md)" not in english:
        fail("README.md language switch is missing the readable Chinese link.")
    if "[English](README.md) | 中文" not in chinese:
        fail("README.zh-CN.md language switch is missing or unreadable.")

    required_zh_headings = [
        "## 包含内容",
        "## 快速开始（macOS / Linux）",
        "## 环境要求",
        "## 运行数据和密钥",
        "## 本地 embedding 模型",
        "## 许可证与引用",
        "## 发布包",
    ]
    missing = [heading for heading in required_zh_headings if heading not in chinese]
    if missing:
        fail(f"README.zh-CN.md is missing expected headings: {', '.join(missing)}")


def check_text_encoding() -> None:
    hits: list[str] = []
    for path in candidate_text_paths():
        relative_path = str(path.relative_to(ROOT)).replace("\\", "/")
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in MOJIBAKE_MARKERS:
            if marker in text:
                hits.append(f"{relative_path}: contains {marker!r}")

    if hits:
        fail("Mojibake markers found:\n  " + "\n  ".join(hits))


def candidate_text_paths() -> list[Path]:
    paths: list[Path] = []
    for path in sorted(ROOT.iterdir()):
        if path.is_file() and (path.suffix in ROOT_TEXT_SUFFIXES or path.name in ROOT_TEXT_NAMES):
            paths.append(path)
    scripts_dir = ROOT / "scripts"
    if scripts_dir.is_dir():
        paths.extend(
            path
            for path in sorted(scripts_dir.iterdir())
            if path.is_file() and path.suffix in SCRIPT_TEXT_SUFFIXES
        )
    return paths


def check_gitignore() -> None:
    lines = {
        line.strip()
        for line in read_text(".gitignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = [line for line in REQUIRED_GITIGNORE_LINES if line not in lines]
    if missing:
        fail(f".gitignore is missing required local/runtime exclusions: {', '.join(missing)}")


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        fail("git ls-files failed; cannot verify tracked runtime exclusions.")
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def check_tracked_files() -> None:
    tracked = git_ls_files()
    forbidden = [
        path
        for path in tracked
        if any(path.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES)
        or path == "AGENTS.md"
        or path.endswith("/AGENTS.md")
        or path in FORBIDDEN_TRACKED_FILES
    ]
    if forbidden:
        fail("Runtime working-copy paths are tracked:\n  " + "\n  ".join(forbidden[:20]))


def run_command(command: list[str], label: str) -> None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        fail(f"{label} failed with exit code {result.returncode}:\n{output}")


def check_python_scripts() -> None:
    scripts = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "scripts").glob("*.py"))
    run_command([sys.executable, "-m", "py_compile", *scripts], "Python script compile check")


def check_release_dry_run() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_release.py", "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        fail(f"Release dry run failed with exit code {result.returncode}:\n{output}")
    included_files: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "] " in stripped:
            included_files.append(stripped.split("] ", 1)[1].replace("\\", "/"))

    if any(path == "AGENTS.md" or path.endswith("/AGENTS.md") for path in included_files):
        fail("Release dry run includes AGENTS.md, which must stay local-only.")
    for filename in FORBIDDEN_TRACKED_FILES:
        if filename in included_files:
            fail(f"Release dry run includes deprecated component launcher: {filename}")


def check_startup_guard_smoke() -> None:
    run_command([sys.executable, "scripts/test_startup_guards.py"], "Startup guard smoke test")


def check_launcher_shape() -> None:
    """Verify the thin-wrapper launcher shape: OpenNotebookLM.bat delegates to Python."""
    bat_path = ROOT / "OpenNotebookLM.bat"
    sh_path = ROOT / "OpenNotebookLM.sh"

    if not bat_path.is_file():
        fail("OpenNotebookLM.bat is missing.")

    bat_text = bat_path.read_text(encoding="utf-8", errors="replace")
    if "open_notebook_lm.py" not in bat_text:
        fail("OpenNotebookLM.bat does not reference open_notebook_lm.py.")

    bat_lower = bat_text.lower()
    hits = [label for label in FORBIDDEN_BAT_LABELS if label in bat_lower]
    if hits:
        fail(
            "OpenNotebookLM.bat contains forbidden legacy labels: "
            + ", ".join(hits)
            + ". The .bat must be a thin wrapper calling scripts/open_notebook_lm.py."
        )

    if not sh_path.is_file():
        fail("OpenNotebookLM.sh is missing.")

    sh_text = sh_path.read_text(encoding="utf-8", errors="replace")
    if "open_notebook_lm.py" not in sh_text:
        fail("OpenNotebookLM.sh does not reference open_notebook_lm.py.")


def check_open_notebook_single_instance_guard() -> None:
    """Verify the single Python launcher owns duplicate-start protection and stack actions."""
    python_text = read_text("scripts/open_notebook_lm.py")

    required_python_markers = [
        "acquire_launcher_lock",
        "wait_for_existing_startup",
        "launcher.lock",
        "Another launcher is already starting Open Notebook; waiting for it.",
        "api_already_running",
        "Open Notebook backend/API port 5055 is already listening; reusing it.",
        "Open Notebook frontend port 3000 is already listening; reusing it.",
        "setup_codex_mcp",
        "setup_hermes_mcp",
        "start_hermes",
        "start_open_notebook",
    ]
    missing_python = [marker for marker in required_python_markers if marker not in python_text]
    if missing_python:
        fail("scripts/open_notebook_lm.py is missing single-instance guards: " + ", ".join(missing_python))


def main() -> int:
    checks = [
        ("launcher shape", check_launcher_shape),
        ("Open Notebook single-instance guards", check_open_notebook_single_instance_guard),
        ("README language and headings", check_readmes),
        ("text encoding", check_text_encoding),
        (".gitignore runtime exclusions", check_gitignore),
        ("tracked runtime exclusions", check_tracked_files),
        ("Python script syntax", check_python_scripts),
        ("startup guard smoke test", check_startup_guard_smoke),
        ("release dry run", check_release_dry_run),
    ]

    for label, check in checks:
        print(f"[check] {label}...")
        check()
        print(f"[ok] {label}")

    print()
    print("Repository health check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
