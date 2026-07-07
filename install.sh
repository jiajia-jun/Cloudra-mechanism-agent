#!/usr/bin/env bash
set -euo pipefail

# Cloudra 一键安装脚本
# 用途：
#   1. 校验 Python 版本（>=3.10）
#   2. 可选创建虚拟环境
#   3. 以 editable 模式安装 cloudra
#   4. 将旧的 .env 配置迁移到 cloudra config（YAML）
#   5. 交互式初始化 cloudra config
#   6. 验证安装

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="cloudra"
MIN_PYTHON="3.10"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 比较版本号：>= 返回 0，< 返回 1
version_ge() {
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# 查找可用的 python 命令
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "$cmd"
            return 0
        fi
    done
    return 1
}

PYTHON_CMD=$(find_python) || {
    err "未找到 Python 解释器，请先安装 Python ${MIN_PYTHON}+"
    exit 1
}

PYTHON_VERSION=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "检测到 Python: $PYTHON_CMD (v${PYTHON_VERSION})"

if ! version_ge "$PYTHON_VERSION" "$MIN_PYTHON"; then
    err "需要 Python >= ${MIN_PYTHON}，当前为 ${PYTHON_VERSION}"
    exit 1
fi
ok "Python 版本符合要求"

# 询问是否使用虚拟环境
USE_VENV=""
while [[ "$USE_VENV" != "y" && "$USE_VENV" != "n" ]]; do
    read -rp "是否在项目目录下创建虚拟环境（.venv）？[Y/n] " USE_VENV
    USE_VENV=${USE_VENV:-y}
    USE_VENV=$(echo "$USE_VENV" | tr '[:upper:]' '[:lower:]')
done

if [[ "$USE_VENV" == "y" ]]; then
    VENV_DIR="${SCRIPT_DIR}/.venv"
    if [[ ! -d "$VENV_DIR" ]]; then
        info "创建虚拟环境: $VENV_DIR"
        "$PYTHON_CMD" -m venv "$VENV_DIR"
    else
        warn "虚拟环境已存在: $VENV_DIR"
    fi
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    PYTHON_CMD="${VENV_DIR}/bin/python"
    ok "已激活虚拟环境"
else
    warn "不使用虚拟环境，将直接安装到当前 Python 环境"
fi

# 确保 pip 可用
info "升级 pip..."
"$PYTHON_CMD" -m pip install --upgrade pip

# 安装项目
info "安装 ${PROJECT_NAME}（editable 模式）..."
"$PYTHON_CMD" -m pip install -e "${SCRIPT_DIR}"

# 如果存在 .env，询问是否迁移到 cloudra config
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
    warn "检测到旧的 .env 配置文件: ${ENV_FILE}"
    warn "注意：cloudra 现在优先使用 YAML 配置文件（~/.config/cloudra/config.yaml）"
    warn ".env 中的配置将不会被 cloudra config 覆盖"

    MIGRATE=""
    while [[ "$MIGRATE" != "y" && "$MIGRATE" != "n" ]]; do
        read -rp "是否将 .env 中的 LLM 配置迁移到 cloudra config？[Y/n] " MIGRATE
        MIGRATE=${MIGRATE:-y}
        MIGRATE=$(echo "$MIGRATE" | tr '[:upper:]' '[:lower:]')
    done

    if [[ "$MIGRATE" == "y" ]]; then
        info "读取 .env 并准备迁移..."
        # 读取 .env 中的关键变量
        COORDINATOR_MODEL=$(grep -E '^COORDINATOR_MODEL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        COORDINATOR_URL=$(grep -E '^COORDINATOR_URL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        COORDINATOR_KEY=$(grep -E '^COORDINATOR_KEY=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        FOLLOWER_MODEL=$(grep -E '^FOLLOWER_MODEL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        FOLLOWER_URL=$(grep -E '^FOLLOWER_URL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        FOLLOWER_KEY=$(grep -E '^FOLLOWER_KEY=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)

        # 使用 cloudra config set 写入 YAML 配置
        set +e
        [[ -n "$COORDINATOR_MODEL" ]] && cloudra config set coordinator.model "$COORDINATOR_MODEL"
        [[ -n "$COORDINATOR_URL" ]] && cloudra config set coordinator.url "$COORDINATOR_URL"
        [[ -n "$COORDINATOR_KEY" ]] && cloudra config set coordinator.key "$COORDINATOR_KEY"
        [[ -n "$FOLLOWER_MODEL" ]] && cloudra config set follower.model "$FOLLOWER_MODEL"
        [[ -n "$FOLLOWER_URL" ]] && cloudra config set follower.url "$FOLLOWER_URL"
        [[ -n "$FOLLOWER_KEY" ]] && cloudra config set follower.key "$FOLLOWER_KEY"
        set -e

        ok "迁移完成"
        warn "建议备份后删除 ${ENV_FILE}，以免旧配置造成困惑"
    fi
fi

# 交互式初始化配置
info "初始化 cloudra 配置..."
cloudra config init

# 验证安装
info "验证安装..."
if cloudra --version; then
    ok "cloudra 安装成功"
else
    err "cloudra 命令无法执行，请检查安装日志"
    exit 1
fi

ok "安装完成！"
info "常用命令："
echo "  cloudra config show       # 查看当前配置"
echo "  cloudra run 'YOUR TASK'   # 运行任务"
echo "  cloudra --help            # 查看帮助"
