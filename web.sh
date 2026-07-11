#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
MODE="serve"
HOST="127.0.0.1"
PORT="8000"
VITE_PORT="5173"
NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}[Cloudra]${NC} $*"; }
ok() { echo -e "${GREEN}[完成]${NC} $*"; }
warn() { echo -e "${YELLOW}[注意]${NC} $*"; }
fail() { echo -e "${RED}[错误]${NC} $*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Cloudra Web 一键启动脚本

用法：
  ./web.sh                    构建并启动生产界面（推荐）
  ./web.sh dev                同时启动 FastAPI 和 Vite 开发服务器
  ./web.sh build              只安装依赖并构建前端

选项：
  --host HOST                 后端监听地址，默认 127.0.0.1
  --port PORT                 后端端口，默认 8000
  --vite-port PORT            开发服务器端口，默认 5173
  -h, --help                  显示帮助

局域网示例：
  CLOUDRA_API_TOKEN='随机长字符串' ./web.sh --host 0.0.0.0

环境变量：
  CLOUDRA_API_TOKEN           API 认证 Token
  NPM_REGISTRY                npm 镜像，默认 registry.npmmirror.com
EOF
}

if [[ $# -gt 0 && "$1" != --* && "$1" != "-h" ]]; then
    MODE="$1"
    shift
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST="${2:-}"; shift 2 ;;
        --port) PORT="${2:-}"; shift 2 ;;
        --vite-port) VITE_PORT="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "未知参数：$1（使用 ./web.sh --help 查看帮助）" ;;
    esac
done

[[ "$MODE" =~ ^(serve|dev|build)$ ]] || fail "未知模式：${MODE}"
[[ "$PORT" =~ ^[0-9]+$ ]] || fail "--port 必须是数字"
[[ "$VITE_PORT" =~ ^[0-9]+$ ]] || fail "--vite-port 必须是数字"

command -v node >/dev/null 2>&1 || fail "未找到 Node.js，请先安装 Node.js 20.19 或更高版本"
command -v npm >/dev/null 2>&1 || fail "未找到 npm"

PYTHON_CMD=""
for candidate in "${ROOT_DIR}/.venv/bin/python" python3 python; do
    if { [[ -x "$candidate" ]] || command -v "$candidate" >/dev/null 2>&1; } \
        && "$candidate" -c 'import cloudra, fastapi, uvicorn' >/dev/null 2>&1; then
        PYTHON_CMD="$candidate"
        break
    fi
done
[[ -n "$PYTHON_CMD" ]] || fail "没有找到已安装 Cloudra 后端的 Python，请先运行 ./install.sh"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
NODE_MINOR="$(node -p 'process.versions.node.split(".")[1]')"
if (( NODE_MAJOR < 20 || (NODE_MAJOR == 20 && NODE_MINOR < 19) )); then
    fail "当前 Node.js 为 $(node --version)，Vite 需要 Node.js 20.19+"
fi

install_frontend() {
    if [[ ! -d "${FRONTEND_DIR}/node_modules" ]] || [[ ! -f "${FRONTEND_DIR}/package-lock.json" ]]; then
        info "首次运行，正在通过国内镜像安装前端依赖……"
        (cd "$FRONTEND_DIR" && npm install --registry="$NPM_REGISTRY")
        ok "前端依赖安装完成"
    fi
}

frontend_needs_build() {
    [[ ! -f "${FRONTEND_DIR}/dist/index.html" ]] && return 0
    [[ "${FRONTEND_DIR}/package.json" -nt "${FRONTEND_DIR}/dist/index.html" ]] && return 0
    [[ "${FRONTEND_DIR}/package-lock.json" -nt "${FRONTEND_DIR}/dist/index.html" ]] && return 0
    [[ "${FRONTEND_DIR}/vite.config.ts" -nt "${FRONTEND_DIR}/dist/index.html" ]] && return 0
    [[ "${FRONTEND_DIR}/index.html" -nt "${FRONTEND_DIR}/dist/index.html" ]] && return 0
    [[ "${FRONTEND_DIR}/tsconfig.app.json" -nt "${FRONTEND_DIR}/dist/index.html" ]] && return 0
    find "${FRONTEND_DIR}/src" -type f -newer "${FRONTEND_DIR}/dist/index.html" -print -quit | grep -q .
}

build_frontend() {
    install_frontend
    if frontend_needs_build; then
        info "正在构建 Web 前端……"
        (cd "$FRONTEND_DIR" && npm run build)
        ok "前端构建完成"
    else
        ok "前端已经是最新版本，跳过构建"
    fi
}

prepare_token() {
    if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" && "$HOST" != "::1" && -z "${CLOUDRA_API_TOKEN:-}" ]]; then
        warn "你正在监听 ${HOST}，同一网络中的其他设备可能访问 Cloudra。"
        read -rsp "请输入本次使用的 API Token：" CLOUDRA_API_TOKEN
        echo
        [[ ${#CLOUDRA_API_TOKEN} -ge 12 ]] || fail "对外访问时 Token 至少需要 12 个字符"
        export CLOUDRA_API_TOKEN
    fi
}

check_llm_config() {
    if ! "$PYTHON_CMD" -c 'from cloudra.config import get_config; raise SystemExit(0 if get_config().coordinator.key else 1)' >/dev/null 2>&1; then
        warn "Coordinator API Key 尚未配置。页面可以打开，但提交任务会失败。"
        warn "请运行：cloudra config init"
    fi
}

start_backend() {
    export CLOUDRA_API_HOST="$HOST"
    export CLOUDRA_API_PORT="$PORT"
    exec "$PYTHON_CMD" -m cloudra.api
}

case "$MODE" in
    build)
        build_frontend
        ;;
    serve)
        build_frontend
        prepare_token
        check_llm_config
        echo
        info "正在启动 Cloudra Web：http://${HOST}:${PORT}"
        info "按 Ctrl+C 停止服务"
        start_backend
        ;;
    dev)
        install_frontend
        prepare_token
        check_llm_config
        export CLOUDRA_API_HOST="$HOST"
        export CLOUDRA_API_PORT="$PORT"

        cleanup() {
            info "正在停止开发服务器……"
            [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
            [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
            wait 2>/dev/null || true
        }
        trap cleanup EXIT INT TERM

        info "启动 FastAPI：http://${HOST}:${PORT}"
        "$PYTHON_CMD" -m cloudra.api &
        BACKEND_PID=$!

        info "启动 Vite：http://127.0.0.1:${VITE_PORT}"
        (cd "$FRONTEND_DIR" && npm run dev -- --host 127.0.0.1 --port "$VITE_PORT") &
        FRONTEND_PID=$!

        wait -n "$BACKEND_PID" "$FRONTEND_PID"
        ;;
esac
