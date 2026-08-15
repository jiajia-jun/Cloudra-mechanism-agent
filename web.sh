#!/usr/bin/env bash
set -euo pipefail

# Cloudra web frontend launcher (Electron desktop or browser fallback).
#
# Usage:
#   ./web.sh               install frontend deps if needed, build, start Electron
#   ./web.sh --browser     build, then serve dist/ + runtime for a plain browser
#   ./web.sh --skip-build  reuse the existing frontend/dist build
#
# Environment:
#   CLOUDRA_PYTHON         python interpreter (default: python3)
#   CLOUDRA_API_PORT       runtime port for browser mode (default: 8000)
#   CLOUDRA_RUNTIME_STORE  runtime-v2 sqlite path (default: data_dir/runtime-v2.db)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="${ROOT}/frontend"
MODE="electron"
SKIP_BUILD="0"
for arg in "$@"; do
    case "$arg" in
        --browser) MODE="browser" ;;
        --skip-build) SKIP_BUILD="1" ;;
        --help|-h) echo "usage: ./web.sh [--browser] [--skip-build]"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

PYTHON_CMD="${CLOUDRA_PYTHON:-python3}"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "[web.sh] Node.js and npm are required for the Cloudra web frontend." >&2
    echo "[web.sh] Install Node.js >= 18 first: https://nodejs.org/" >&2
    exit 1
fi
if ! "$PYTHON_CMD" -c 'import cloudra' >/dev/null 2>&1; then
    echo "[web.sh] Python package 'cloudra' is not installed." >&2
    echo "[web.sh] Run ./install.sh first (or: pip install -e .)." >&2
    exit 1
fi

cd "$FRONTEND"
if [[ ! -d node_modules ]]; then
    echo "[web.sh] installing frontend dependencies..."
    npm install --no-audit --no-fund
fi
if [[ "$SKIP_BUILD" == "0" ]]; then
    echo "[web.sh] building frontend..."
    npm run build
fi

if [[ "$MODE" == "electron" ]]; then
    echo "[web.sh] starting Electron (spawns the runtime automatically)..."
    exec npm run electron
fi

PORT="${CLOUDRA_API_PORT:-8000}"
STORE="${CLOUDRA_RUNTIME_STORE:-${ROOT}/runtime-v2.db}"

cleanup() {
    trap - INT TERM EXIT
    [[ -n "${RUNTIME_PID:-}" ]] && kill "$RUNTIME_PID" 2>/dev/null || true
    [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "[web.sh] starting runtime v2 on http://127.0.0.1:${PORT}"
CLOUDRA_RUNTIME_STORE="$STORE" "$PYTHON_CMD" -m uvicorn \
    cloudra.services.api_v2:create_default_v2_app \
    --factory --host 127.0.0.1 --port "$PORT" --log-level warning &
RUNTIME_PID=$!

for _ in $(seq 1 80); do
    if curl -fsS "http://127.0.0.1:${PORT}/api/v2/runtime/health" >/dev/null 2>&1; then
        break
    fi
    sleep 0.25
done
if ! curl -fsS "http://127.0.0.1:${PORT}/api/v2/runtime/health" >/dev/null 2>&1; then
    echo "[web.sh] runtime did not become healthy; check the process output" >&2
    exit 1
fi

echo "[web.sh] serving frontend at http://127.0.0.1:5173"
"$PYTHON_CMD" -m http.server 5173 --bind 127.0.0.1 --directory "$FRONTEND/dist" &
WEB_PID=$!
echo "[web.sh] open http://127.0.0.1:5173"
wait
