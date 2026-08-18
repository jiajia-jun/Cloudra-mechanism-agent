#!/usr/bin/env bash
set -euo pipefail
# Compatibility wrapper: the recommended entry point is `cloudra` itself.
# Usage: ./web.sh [--skip-build] [--rebuild]
PYTHON_CMD="${CLOUDRA_PYTHON:-python3}"
exec "$PYTHON_CMD" -m cloudra web "$@"
