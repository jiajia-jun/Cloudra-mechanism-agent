#!/bin/bash
set -euo pipefail

export PATH="/opt/gridview/slurm/bin:$HOME/.venvs/cloudra/bin:$PATH"
export PYTHONPATH="$HOME/cloudra:${PYTHONPATH:-}"
export CLOUDRA_NODE_REGISTRY_FILE="$HOME/cloudra/config/nodes.json"
export CLOUDRA_FRONTEND_SERVE_DIR="$HOME/cloudra/frontend/dist"
export CLOUDRA_API_BIND_HOST="127.0.0.1"
export CLOUDRA_NO_BROWSER="1"

# 可选科学计算模块
if type module >/dev/null 2>&1; then
    module load apps/orca/5.0.2/hpcx-2.7.4-gcc-7.3.1 2>/dev/null || true
fi

cd "$HOME/cloudra"

exec "$HOME/.venvs/cloudra/bin/python" -m uvicorn cloudra.services.api_v2:create_default_v2_app \
    --factory \
    --host 127.0.0.1 \
    --port 8420 \
    --timeout-graceful-shutdown 20
