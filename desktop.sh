#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

fail() { printf '[Cloudra Desktop] %s\n' "$*" >&2; exit 1; }

command -v npm >/dev/null 2>&1 || fail "未找到 npm，请先安装 Node.js 20.19+"
command -v cargo >/dev/null 2>&1 || fail "未找到 Rust/Cargo，请先安装 Rust 工具链"

if ! pkg-config --exists webkit2gtk-4.1 dbus-1 2>/dev/null; then
    fail "缺少 Ubuntu 桌面构建依赖，请先执行：
sudo apt-get update
sudo apt-get install -y libdbus-1-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libxdo-dev"
fi

if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    (cd "${FRONTEND_DIR}" && npm install)
fi

cd "${FRONTEND_DIR}"
exec npm run desktop
