"""Run Hermes or a verification command with deterministic capture and timeout."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


TIMEOUT_EXIT_CODE = 124


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--stdout-file", required=True)
    parser.add_argument("--stderr-file", required=True)
    parser.add_argument("--timeout", required=True, type=int)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hermes-exe")
    mode.add_argument("--command-file")

    parser.add_argument("--prompt-file")
    parser.add_argument("--model")
    parser.add_argument("--provider")
    return parser.parse_args()


def write_output(path: str, value: str | bytes | None) -> None:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    Path(path).write_text(value or "", encoding="utf-8")


def build_command(args: argparse.Namespace) -> list[str]:
    if args.hermes_exe:
        if not args.prompt_file:
            raise ValueError("--prompt-file is required with --hermes-exe")
        prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig")
        command = [args.hermes_exe]
        if args.model:
            command.extend(["--model", args.model])
        if args.provider:
            command.extend(["--provider", args.provider])
        command.extend(["--oneshot", prompt])
        return command

    command_text = Path(args.command_file).read_text(encoding="utf-8-sig")
    return [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        command_text,
    ]


def main() -> int:
    args = parse_args()
    try:
        command = build_command(args)
        child_env = None
        if args.command_file:
            child_env = os.environ.copy()
            # The uv-managed Python used to host this runner exports its own
            # PYTHONHOME for child processes. A verification command may use
            # a different repository interpreter, where that inherited value
            # causes a stdlib/runtime mismatch. Verification must start from
            # the operator's command, not the runner's Python installation.
            child_env.pop("PYTHONHOME", None)
            child_env.pop("UV_INTERNAL__PYTHONHOME", None)
        result = subprocess.run(
            command,
            cwd=args.cwd,
            capture_output=True,
            env=child_env,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        write_output(args.stdout_file, exc.stdout)
        write_output(args.stderr_file, exc.stderr)
        with Path(args.stderr_file).open("a", encoding="utf-8") as stream:
            stream.write(f"\nProcess timed out after {args.timeout} seconds.\n")
        return TIMEOUT_EXIT_CODE
    except Exception as exc:  # pragma: no cover - defensive process boundary
        write_output(args.stdout_file, "")
        write_output(args.stderr_file, f"{type(exc).__name__}: {exc}\n")
        return 1

    write_output(args.stdout_file, result.stdout)
    write_output(args.stderr_file, result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
