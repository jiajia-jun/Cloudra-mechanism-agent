#!/usr/bin/env bash
# Non-interactive dev environment bootstrap (Python 3.11–3.13 recommended).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${CLOUDRA_PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "python3 not found; set CLOUDRA_PYTHON to a 3.11+ interpreter" >&2
  exit 1
fi

VER="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$VER" in
  3.11|3.12|3.13) ;;
  *)
    echo "WARN: Python ${VER} detected; 3.11–3.13 recommended (pymol-open-source wheel)." >&2
    ;;
esac

VENV="${ROOT}/.venv"
if [[ ! -d "$VENV" ]]; then
  # Inherit conda/site PyMOL when the pip wheel has broken rpaths (common on macOS).
  "$PYTHON" -m venv "$VENV" --system-site-packages
fi
# shellcheck source=/dev/null
source "${VENV}/bin/activate"

python -m pip install --upgrade pip
if ! python -m pip install -e ".[all,dev]"; then
  echo "WARN: optional extras failed; installing dev core only" >&2
  python -m pip install -e ".[dev]"
fi

echo "Dev env ready: ${VENV}"
echo "  pytest -q tests"
echo "  cloudra web"
