from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tracked files list used when git ls-files is unavailable.
# Must match what the .gitignore allows and what the repo publishes.
FALLBACK_FILES: list[str] = [
    ".gitignore",
    "LICENSE",
    "OpenNotebookLM.bat",
    "OpenNotebookLM.sh",
    "README.md",
    "README.zh-CN.md",
    "REPOSITORIES.md",
    "THIRD_PARTY.md",
]

INCLUDE_DIRS = ["components", "scripts"]


def git_tracked_files(root: Path) -> list[str] | None:
    """Return a list of tracked relative paths from git, or None."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    lines = result.stdout.splitlines()
    # Filter any bare .git entries that git ls-files might emit
    paths: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(".git/") or line == ".git":
            continue
        if line == "AGENTS.md" or line.endswith("/AGENTS.md"):
            continue
        # Also filter excluded patterns like dist/
        if line.startswith("dist/"):
            continue
        paths.append(line)
    return paths


def fallback_files(root: Path) -> list[str]:
    """Build file list by scanning known tracked directories."""
    result = list(FALLBACK_FILES)
    for directory in INCLUDE_DIRS:
        dir_path = root / directory
        if not dir_path.is_dir():
            continue
        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_dir():
                continue
            rel = str(file_path.relative_to(root)).replace("\\", "/")
            # Skip patterns that .gitignore excludes
            if rel == "AGENTS.md" or rel.endswith("/AGENTS.md"):
                continue
            if "/.venv/" in rel or "/node_modules/" in rel or "/__pycache__/" in rel:
                continue
            if rel.endswith(".pyc") or rel.endswith(".out.log") or rel.endswith(".err.log"):
                continue
            if "/.git/" in rel:
                continue
            result.append(rel)
    return result


def collect_files(root: Path, dry_run: bool) -> list[str]:
    files = git_tracked_files(root)
    if files is None:
        if dry_run:
            print("WARNING: git ls-files unavailable; using fallback file list.", file=sys.stderr)
        files = fallback_files(root)
    # Deduplicate and sort
    files = sorted(set(files))
    return files


def build_zip(root: Path, version: str, files: list[str]) -> Path:
    dist_dir = root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"Codex-Notebook-Open-{version}.zip"
    archive_path = dist_dir / archive_name

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            full = root / file_path
            if not full.is_file():
                print(f"WARNING: skipping missing file: {file_path}", file=sys.stderr)
                continue
            zf.write(full, arcname=f"Codex-Notebook-Open-{version}/{file_path}")

    return archive_path


def build_tar_gz(root: Path, version: str, files: list[str]) -> Path:
    dist_dir = root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"Codex-Notebook-Open-{version}.tar.gz"
    archive_path = dist_dir / archive_name

    prefix = f"Codex-Notebook-Open-{version}"

    with tarfile.open(archive_path, "w:gz") as tf:
        for file_path in files:
            full = root / file_path
            if not full.is_file():
                print(f"WARNING: skipping missing file: {file_path}", file=sys.stderr)
                continue
            info = tf.gettarinfo(full, arcname=f"{prefix}/{file_path}")
            # Preserve executable mode for shell scripts
            if file_path == "OpenNotebookLM.sh":
                info.mode = 0o755
            with open(full, "rb") as fh:
                tf.addfile(info, fh)

    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Codex-Notebook-Open release archives (zip + tar.gz)."
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Release version (default 'dev' when --dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be included; do not create archives.",
    )
    args = parser.parse_args()

    version = args.version or ("dev" if args.dry_run else None)
    if version is None:
        print("ERROR: --version is required (e.g. --version 1.0.0)", file=sys.stderr)
        return 1

    files = collect_files(ROOT, args.dry_run)

    if args.dry_run:
        print(f"Files that would be included in release v{version}:")
        for f in files:
            full = ROOT / f
            status = "OK" if full.is_file() else "MISSING"
            print(f"  [{status}] {f}")
        print()
        print(f"Total: {len(files)} files")
        print("Dry run complete. No archives created.")
        return 0

    print(f"Building release archives for version {version}...")
    zip_path = build_zip(ROOT, version, files)
    print(f"Created: {zip_path}")

    tar_path = build_tar_gz(ROOT, version, files)
    print(f"Created: {tar_path}")

    print(f"Release build complete. {len(files)} files included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
