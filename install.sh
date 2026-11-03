#!/usr/bin/env bash
# Install the UI and default tool runtime into this checkout, without sudo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
trap 'printf "\n安装未完成，请查看上面的错误。安装指南：docs/INSTALL_CN.md\n" >&2' ERR

case "$(uname -s)" in
    Darwin|Linux) ;;
    *) printf '原生 Windows 请下载 windows 分支并运行 install.cmd。\n' >&2; exit 1 ;;
esac

# Prefer a supported interpreter; an older system python3 must not hide a newer one.
PYTHON_CMD=""
if [[ -n "${CLOUDRA_PYTHON:-}" ]]; then
    PYTHON_CMD="$(command -v "$CLOUDRA_PYTHON")"
else
    for candidate in "$SCRIPT_DIR/.venv/bin/python" python3.13 python3.12 python3.11 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && \
           "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            PYTHON_CMD="$(command -v "$candidate")"
            break
        fi
    done
fi
if [[ -z "$PYTHON_CMD" ]] || ! "$PYTHON_CMD" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    printf '需要 Python 3.11 或更高版本（推荐 3.13）。请按 docs/INSTALL_CN.md 安装。\n' >&2
    exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1 || \
   ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1)'; then
    printf '需要 Node.js 22.12 或更高版本及 npm。请安装 Node.js LTS 后重开终端。\n' >&2
    exit 1
fi

printf '\n[1/5] 准备项目独立环境 .venv…\n'
if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    "$PYTHON_CMD" -m venv "$SCRIPT_DIR/.venv"
fi
PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
printf '\n[2/5] 安装 Cloudra…\n'
"$PYTHON_CMD" -m pip install --upgrade pip
"$PYTHON_CMD" -m pip install -e "$SCRIPT_DIR"
printf '\n[3/5] 安装智能体工具运行环境…\n'
npm ci --prefix "$SCRIPT_DIR/cloudra/runtime_v2/js_host" --ignore-scripts --no-audit --no-fund
printf '\n[4/5] 安装并构建网页界面…\n'
npm ci --prefix "$SCRIPT_DIR/frontend" --no-audit --no-fund
npm run build --prefix "$SCRIPT_DIR/frontend"
printf '\n[5/5] 检查安装并创建桌面入口…\n'
"$PYTHON_CMD" -m cloudra --version
"$PYTHON_CMD" "$SCRIPT_DIR/scripts/create_desktop_shortcut.py"
printf '\n安装完成！双击桌面的 Cloudra，或在此目录运行 bash web.sh。\n'
printf '打开界面后，在全局设置中配置模型。启动窗口需保持打开。\n'
printf '本次安装包含 UI 和基础运行环境；化学扩展及量化软件按任务另装，见 docs/INSTALL_CN.md。\n'
