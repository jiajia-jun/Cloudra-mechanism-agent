#!/usr/bin/env bash
# 组装可分发的 Cloudra 桌面端：Tauri 二进制 + 独立 Python 运行时（含 cloudra 及全部依赖）。
# 产物为 frontend/dist-app/ 目录，整体拷贝即可分发——目标机无需安装任何 Python 环境。
# 可重复执行：已完成的步骤（下载、依赖安装）会自动跳过/增量更新。
#
# 用法：frontend/scripts/package-desktop.sh
# 可选环境变量：PIP_INDEX_URL（pip 源，默认官方 PyPI）
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$FRONTEND_DIR/.." && pwd)"
BUILD_DIR="$FRONTEND_DIR/runtime-build"
DIST_DIR="$FRONTEND_DIR/dist-app"

PY_VERSION="3.13.14"
PBS_TAG="20260623"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PY_VERSION}%2B${PBS_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"

# 1. 独立 Python 运行时（python-build-standalone，install_only 变体）
if [ ! -x "$BUILD_DIR/python/bin/python3" ]; then
  echo "==> [1/5] 下载独立 Python ${PY_VERSION} 运行时（约 119MB）"
  mkdir -p "$BUILD_DIR"
  curl -fL --retry 3 -o "$BUILD_DIR/python.tar.gz" "$PBS_URL"
  tar -xzf "$BUILD_DIR/python.tar.gz" -C "$BUILD_DIR"
  rm -f "$BUILD_DIR/python.tar.gz"
else
  echo "==> [1/5] 独立 Python 运行时已存在，跳过"
fi
RUNTIME_PY="$BUILD_DIR/python/bin/python3"
"$RUNTIME_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true

# 2. 构建 cloudra wheel（使用宿主 python3，需 pip + setuptools）
WHEEL_DIR="$BUILD_DIR/wheels"
mkdir -p "$WHEEL_DIR"
echo "==> [2/5] 构建 cloudra wheel"
(cd "$REPO_ROOT" && python3 -m pip wheel . --no-deps --no-build-isolation -w "$WHEEL_DIR")

# 3. 安装 cloudra 及全部依赖到运行时（首次较慢，依赖体积大）
echo "==> [3/5] 安装 cloudra 及依赖到运行时"
# shellcheck disable=SC2086
"$RUNTIME_PY" -m pip install --upgrade --force-reinstall --no-cache-dir $WHEEL_DIR/cloudra-*.whl

# 4. 构建 Tauri release 二进制（lib.rs 会优先探测 <exe>/runtime/bin/python3）
# 注意：必须走 `tauri build`（npm run desktop:build）——直接 `cargo build --release`
# 产出的二进制会把窗口导航到 devUrl（127.0.0.1:5173），表现为白屏/连接拒绝。
echo "==> [4/5] tauri build（release）"
(cd "$FRONTEND_DIR" && npm run desktop:build)

# 5. 组装 dist-app
echo "==> [5/5] 组装 $DIST_DIR"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"
cp "$FRONTEND_DIR/src-tauri/target/release/cloudra-desktop" "$DIST_DIR/"
cp -a "$BUILD_DIR/python" "$DIST_DIR/runtime"
# 只清缓存类文件；不删第三方包自带 tests 目录，避免个别包运行时引用
find "$DIST_DIR/runtime" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "完成：$DIST_DIR（$(du -sh "$DIST_DIR" | cut -f1)）"
echo "启动：$DIST_DIR/cloudra-desktop"
echo "注意：浏览器工具首次使用需执行 $DIST_DIR/runtime/bin/python3 -m playwright install chromium"
