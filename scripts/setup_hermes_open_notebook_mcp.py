from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


WORKSPACE = Path(__file__).resolve().parents[1]
OPEN_NOTEBOOK_ENV = WORKSPACE / "opennotebook" / ".env"


def _hermes_home() -> Path:
    if "HERMES_HOME" in os.environ:
        return Path(os.environ["HERMES_HOME"])
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(local_appdata) / "hermes"
    return Path.home() / ".hermes"


HERMES_CONFIG = _hermes_home() / "config.yaml"
HERMES_ENV = _hermes_home() / ".env"


def _notebooklm_python() -> Path:
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    exe = "python.exe" if sys.platform == "win32" else "python"
    return WORKSPACE / "notebooklm-py" / ".venv" / scripts / exe


NOTEBOOKLM_PYTHON = _notebooklm_python()

REQUIRED_TOOLS = [
    "open_notebook_list_notebooks",
    "open_notebook_create_notebook",
    "open_notebook_list_sources",
    "open_notebook_create_text_source",
    "open_notebook_list_notes",
    "open_notebook_get_note",
    "open_notebook_create_note",
    "open_notebook_update_note",
    "open_notebook_delete_note",
]


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> None:
    if not NOTEBOOKLM_PYTHON.exists():
        raise SystemExit(f"Missing notebooklm-py Python: {NOTEBOOKLM_PYTHON}")
    if not OPEN_NOTEBOOK_ENV.exists():
        raise SystemExit(f"Missing Open Notebook env file: {OPEN_NOTEBOOK_ENV}")

    open_notebook_env = read_env(OPEN_NOTEBOOK_ENV)
    password = open_notebook_env.get("OPEN_NOTEBOOK_PASSWORD")
    if not password:
        raise SystemExit("OPEN_NOTEBOOK_PASSWORD is missing in opennotebook/.env")

    upsert_env(
        HERMES_ENV,
        {
            "OPEN_NOTEBOOK_URL": "http://localhost:5055",
            "OPEN_NOTEBOOK_PASSWORD": password,
        },
    )

    HERMES_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    config = {}
    if HERMES_CONFIG.exists():
        config = yaml.safe_load(HERMES_CONFIG.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(config, dict):
        raise SystemExit(f"Hermes config is not a YAML mapping: {HERMES_CONFIG}")

    servers = config.setdefault("mcp_servers", {})
    if not isinstance(servers, dict):
        raise SystemExit("Hermes config key mcp_servers exists but is not a mapping")

    servers["open_notebook"] = {
        "command": str(NOTEBOOKLM_PYTHON),
        "args": ["-m", "notebooklm.mcp.open_notebook"],
        "env": {
            "OPEN_NOTEBOOK_URL": "${OPEN_NOTEBOOK_URL}",
            "OPEN_NOTEBOOK_PASSWORD": "${OPEN_NOTEBOOK_PASSWORD}",
        },
        "enabled": True,
        "timeout": 120,
        "connect_timeout": 60,
        "tools": {
            "include": REQUIRED_TOOLS,
            "resources": False,
            "prompts": False,
        },
    }

    HERMES_CONFIG.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"OK: wrote Hermes MCP server 'open_notebook' to {HERMES_CONFIG}")


if __name__ == "__main__":
    main()
