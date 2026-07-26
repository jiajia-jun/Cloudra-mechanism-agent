#!/usr/bin/env bash
set -euo pipefail

# Cloudra 一键安装脚本
# 用途：
#   1. 校验 Python 版本（>=3.10）
#   2. 可选创建虚拟环境
#   3. 安装 cloudra 及可选依赖
#   4. 将旧 .env 迁移到 YAML 配置
#   5. 交互式初始化 cloudra config
#   6. 把 cloudra 命令加入 PATH（可选）
#
# 注意：Cloudra 2.0 使用 Python 原生 Flet GUI，无需 Rust / Node.js / Tauri。

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

# 查找可用的 python 命令（优先系统 PATH；也检查脚本目录下的独立 Python）
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "$cmd"
            return 0
        fi
    done
    # 检查之前下载过的 standalone Python
    local standalone="${SCRIPT_DIR}/.python/python/bin/python3"
    if [[ -x "$standalone" ]]; then
        echo "$standalone"
        return 0
    fi
    return 1
}

# 检测 CPU 架构
detect_arch() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64|amd64) echo "x86_64" ;;
        aarch64|arm64) echo "aarch64" ;;
        armv7l) echo "armv7l" ;;
        *) echo "$arch" ;;
    esac
}

# 下载 python-build-standalone 到项目目录，无需系统安装
install_standalone_python() {
    local os=$1
    local arch=$2
    local target_dir="${SCRIPT_DIR}/.python"
    local triple=""

    case "${os}-${arch}" in
        Linux-x86_64)  triple="x86_64-unknown-linux-gnu" ;;
        Linux-aarch64) triple="aarch64-unknown-linux-gnu" ;;
        Linux-armv7l)  triple="armv7-unknown-linux-gnueabihf" ;;
        Darwin-x86_64) triple="x86_64-apple-darwin" ;;
        Darwin-aarch64) triple="aarch64-apple-darwin" ;;
        *)
            err "暂不支持自动下载 Python 的平台: ${os}-${arch}"
            err "请手动安装 Python ${MIN_PYTHON}+ 后重试：https://www.python.org/downloads/"
            return 1
            ;;
    esac

    info "未检测到系统 Python，正在从 python-build-standalone 下载独立运行时 (${triple})..."
    info "下载目录: ${target_dir}（无需 sudo）"

    local api_url="https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    local asset_url
    asset_url=$(curl -sL "$api_url" | grep -o "\"browser_download_url\": \"[^\"]*cpython-3.13[^\"]*${triple}-install_only\.tar\.gz[^\"]*\"" | head -n1 | cut -d'"' -f4)

    if [[ -z "$asset_url" ]]; then
        err "无法获取 ${triple} 的独立 Python 下载链接"
        err "请手动安装 Python ${MIN_PYTHON}+ 后重试：https://www.python.org/downloads/"
        return 1
    fi

    mkdir -p "$target_dir"
    local tmp_tar
    tmp_tar=$(mktemp)
    if ! curl -sL -o "$tmp_tar" "$asset_url"; then
        err "下载独立 Python 失败"
        rm -f "$tmp_tar"
        return 1
    fi

    info "解压独立 Python..."
    if ! tar -xzf "$tmp_tar" -C "$target_dir"; then
        err "解压独立 Python 失败"
        rm -f "$tmp_tar"
        return 1
    fi
    rm -f "$tmp_tar"

    local py_cmd="${target_dir}/python/bin/python3"
    if [[ ! -x "$py_cmd" ]]; then
        err "独立 Python 解压后未找到可执行文件: ${py_cmd}"
        return 1
    fi
    echo "$py_cmd"
}

# 检测操作系统
OS=$(uname -s)
info "操作系统: ${OS}"

PYTHON_CMD=$(find_python) || {
    ARCH=$(detect_arch)
    info "未找到 Python 解释器。"
    AUTO=""
    while [[ "$AUTO" != "y" && "$AUTO" != "n" ]]; do
        read -rp "是否自动下载独立 Python ${MIN_PYTHON}+ 到项目目录（无需 sudo）？[Y/n] " AUTO
        AUTO=${AUTO:-y}
        AUTO=$(echo "$AUTO" | tr '[:upper:]' '[:lower:]')
    done
    if [[ "$AUTO" == "y" ]]; then
        PYTHON_CMD=$(install_standalone_python "$OS" "$ARCH") || exit 1
    else
        err "未找到 Python 解释器，请先安装 Python ${MIN_PYTHON}+"
        err "下载地址：https://www.python.org/downloads/"
        exit 1
    fi
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

# 是否安装 GUI 依赖（Flet）
INSTALL_GUI=""
DEFAULT_GUI="n"
if [[ "$OS" == "Darwin" ]]; then
    DEFAULT_GUI="y"
fi
while [[ "$INSTALL_GUI" != "y" && "$INSTALL_GUI" != "n" ]]; do
    read -rp "是否安装 GUI 依赖（Flet，${DEFAULT_GUI}）？[Y/n] " INSTALL_GUI
    INSTALL_GUI=${INSTALL_GUI:-$DEFAULT_GUI}
    INSTALL_GUI=$(echo "$INSTALL_GUI" | tr '[:upper:]' '[:lower:]')
done

if [[ "$INSTALL_GUI" == "y" ]]; then
    EXTRAS="all,gui"
    info "安装 ${PROJECT_NAME}（完整工具链 + GUI）..."
else
    EXTRAS="all"
    info "安装 ${PROJECT_NAME}（完整工具链，无 GUI）..."
fi

"$PYTHON_CMD" -m pip install -e "${SCRIPT_DIR}[${EXTRAS}]"

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
        COORDINATOR_MODEL=$(grep -E '^COORDINATOR_MODEL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        COORDINATOR_URL=$(grep -E '^COORDINATOR_URL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        COORDINATOR_KEY=$(grep -E '^COORDINATOR_KEY=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        FOLLOWER_MODEL=$(grep -E '^FOLLOWER_MODEL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        FOLLOWER_URL=$(grep -E '^FOLLOWER_URL=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
        FOLLOWER_KEY=$(grep -E '^FOLLOWER_KEY=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)

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

# 可选：把 cloudra 命令加入 PATH（当使用虚拟环境时，创建一个 wrapper）
if [[ "$USE_VENV" == "y" ]]; then
    LOCAL_BIN="${HOME}/.local/bin"
    WRAPPER="${LOCAL_BIN}/cloudra"
    mkdir -p "$LOCAL_BIN"

    cat > "$WRAPPER" <<EOF
#!/bin/bash
# Cloudra wrapper generated by install.sh
source "${VENV_DIR}/bin/activate"
exec cloudra "\$@"
EOF
    chmod +x "$WRAPPER"
    ok "已创建命令包装器: ${WRAPPER}"

    if [[ ":$PATH:" != *":${LOCAL_BIN}:"* ]]; then
        warn "${LOCAL_BIN} 不在 PATH 中"
        for rc in "${HOME}/.bashrc" "${HOME}/.zshrc"; do
            if [[ -f "$rc" ]]; then
                echo "export PATH=\"${LOCAL_BIN}:\$PATH\"" >> "$rc"
                info "已把 ${LOCAL_BIN} 加入 ${rc}，请重新打开终端或 source ${rc}"
            fi
        done
    fi
fi

ok "安装完成！"
info "Cloudra 2.0 使用 Python 原生 Flet GUI，无需 Rust / Node.js / Tauri。"
info "常用命令："
echo "  cloudra config show        # 查看当前配置"
echo "  cloudra run 'YOUR TASK'    # 运行任务"
echo "  cloudra                    # Linux 进入 TUI，Windows/Android 启动 GUI"
echo "  cloudra gui                # 强制启动 GUI"
echo "  cloudra-api                # 启动 REST API（http://127.0.0.1:8000）"
