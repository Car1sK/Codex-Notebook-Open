from __future__ import annotations

import secrets
import sys
from pathlib import Path


DEFAULT_LINES = {
    "OPEN_NOTEBOOK_PASSWORD": "open-notebook-change-me",
    "SURREAL_URL": "ws://127.0.0.1:8000/rpc",
    "SURREAL_USER": "root",
    "SURREAL_PASSWORD": "root",
    "SURREAL_NAMESPACE": "open_notebook",
    "SURREAL_DATABASE": "open_notebook",
}


def new_key() -> str:
    return secrets.token_hex(32)


def parse_key(line: str) -> str:
    return line.split("=", 1)[0].strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: ensure_open_notebook_env.py <env-file>", file=sys.stderr)
        return 2

    env_file = Path(sys.argv[1])
    env_file.parent.mkdir(parents=True, exist_ok=True)

    if not env_file.exists():
        lines = [f"OPEN_NOTEBOOK_ENCRYPTION_KEY={new_key()}"]
        lines.extend(f"{key}={value}" for key, value in DEFAULT_LINES.items())
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0

    original_lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines()
    seen: set[str] = set()
    has_key = False
    repaired_lines: list[str] = []

    for line in original_lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            repaired_lines.append(line)
            continue
        key = parse_key(line)
        seen.add(key)
        if key == "OPEN_NOTEBOOK_ENCRYPTION_KEY":
            value = line.split("=", 1)[1].strip()
            if value:
                has_key = True
                repaired_lines.append(line)
            else:
                has_key = True
                repaired_lines.append(f"OPEN_NOTEBOOK_ENCRYPTION_KEY={new_key()}")
            continue
        repaired_lines.append(line)

    if not has_key:
        repaired_lines.insert(0, f"OPEN_NOTEBOOK_ENCRYPTION_KEY={new_key()}")

    for key, value in DEFAULT_LINES.items():
        if key not in seen:
            repaired_lines.append(f"{key}={value}")

    env_file.write_text("\n".join(repaired_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
