#!/bin/bash
pkill -9 -f 'uvicorn' 2>/dev/null || true
sleep 1
cd "$HOME/cloudra"
export CLOUDRA_NODE_REGISTRY_FILE="$HOME/cloudra/config/nodes.json"
export CLOUDRA_FRONTEND_SERVE_DIR="$HOME/cloudra/frontend/dist"
export CLOUDRA_NO_BROWSER=1
export PYTHONPATH="$HOME/cloudra"

nohup "$HOME/.venvs/cloudra/bin/python" -m uvicorn cloudra.services.api_v2:create_default_v2_app \
    --factory --host 127.0.0.1 --port 8420 </dev/null >"$HOME/cloudra/server.log" 2>&1 &
sleep 2
echo "STARTED"
