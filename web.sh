#!/usr/bin/env bash
set -euo pipefail
# Start the existing UI from this checkout, including when opened from a desktop shortcut.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_CMD="${CLOUDRA_PYTHON:-${SCRIPT_DIR}/.venv/bin/python}"
if [[ -z "${CLOUDRA_PYTHON:-}" && ! -x "$PYTHON_CMD" ]]; then
    PYTHON_CMD=python3
fi
PYTHON_CMD="$(command -v "$PYTHON_CMD")"
export PATH="$(dirname "$PYTHON_CMD"):$PATH"
exec "$PYTHON_CMD" -m cloudra web "$@"
