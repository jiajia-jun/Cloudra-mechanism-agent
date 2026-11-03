#!/bin/bash
# Double-click in Finder to install Cloudra.
cd "$(dirname "$0")" || exit 1
/bin/bash ./install.sh
status=$?
printf '\n按 Enter 关闭安装窗口 / Press Enter to close... '
read -r
exit "$status"
