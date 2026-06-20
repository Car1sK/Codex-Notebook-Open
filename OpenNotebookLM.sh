#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=""

# Find a working Python interpreter
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "ERROR: No Python interpreter found (tried python3, python)." >&2
    echo "Install Python 3.8+ and ensure it is on PATH." >&2
    exit 1
fi

LAUNCHER="$SCRIPT_DIR/scripts/open_notebook_lm.py"

if [[ ! -f "$LAUNCHER" ]]; then
    echo "ERROR: Launcher script not found: $LAUNCHER" >&2
    exit 1
fi

exec "$PYTHON" "$LAUNCHER" "$@"
