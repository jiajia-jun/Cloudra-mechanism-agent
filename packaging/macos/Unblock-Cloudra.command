#!/bin/bash
# Remove download quarantine only from Cloudra's installer and application.
set -euo pipefail

if [[ "$(uname -s)" != Darwin ]]; then
    printf '这个脚本仅适用于 macOS。\n' >&2
    exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
targets=()
if [[ $# -gt 0 ]]; then
    targets=("$@")
else
    shopt -s nullglob
    for candidate in "$SCRIPT_DIR"/Cloudra-*-macos-arm64.pkg "$SCRIPT_DIR"/Cloudra-*-macos-x86_64.pkg \
        "$SCRIPT_DIR/Cloudra.app" /Applications/Cloudra.app "$HOME/Applications/Cloudra.app"; do
        if [[ -e "$candidate" ]]; then targets+=("$candidate"); fi
    done
fi
if [[ ${#targets[@]} -eq 0 ]]; then
    printf '未找到 Cloudra。请把脚本与 Cloudra 安装包放在同一文件夹，或在命令末尾指定 Cloudra 的路径。\n' >&2
    exit 1
fi
# Check the complete selection before changing any file.
for target in "${targets[@]}"; do
    if [[ ! -e "$target" ]]; then
        printf '找不到文件：%s\n' "$target" >&2
        exit 1
    fi
    case "$(basename "$target")" in
        Cloudra.app) [[ -d "$target" ]] ;;
        Cloudra-*-macos-arm64.pkg|Cloudra-*-macos-x86_64.pkg) [[ -f "$target" ]] ;;
        *) printf '拒绝处理非 Cloudra 文件：%s\n' "$target" >&2; exit 1 ;;
    esac
done
for target in "${targets[@]}"; do
    printf '解除 Cloudra 下载隔离：%s\n' "$target"
    if error=$(LC_ALL=C /usr/bin/xattr -dr com.apple.quarantine "$target" 2>&1); then
        continue
    fi
    printf '%s\n' "$error" >&2
    case "$error" in
        *"Permission denied"*|*"Operation not permitted"*)
            printf '这个位置需要管理员权限，请按提示输入 Mac 登录密码。\n'
            /usr/bin/sudo /usr/bin/xattr -dr com.apple.quarantine "$target"
            ;;
        *) exit 1 ;;
    esac
done
printf '\n完成。请重新打开 Cloudra 安装包或应用。\n'
