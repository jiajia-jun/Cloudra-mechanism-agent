#!/bin/bash
# This adapter only supplies bundled paths; Cloudra's existing CLI owns the service.
set -u
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
export PATH="$APP_DIR/python/bin:$APP_DIR/node/bin:$PATH"
export CLOUDRA_FRONTEND_DIR="$APP_DIR/frontend"
if [[ "${1:-}" == --version ]]; then
    exec "$APP_DIR/python/bin/python3" -m cloudra --version
fi
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/cloudra"
umask 077
mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/desktop.log"

if [[ "${1:-}" == --stop ]]; then
    shift
    "$APP_DIR/python/bin/python3" -m cloudra stop "$@" >> "$LOG" 2>&1
else
    if [[ ! -f "$STATE_DIR/desktop-shortcut-created" ]]; then
        "$APP_DIR/python/bin/python3" "$APP_DIR/create_shortcuts.py" "$APP_DIR" >> "$LOG" 2>&1
        touch "$STATE_DIR/desktop-shortcut-created"
    fi
    "$APP_DIR/python/bin/python3" -m cloudra web --skip-build "$@" >> "$LOG" 2>&1
fi
status=$?
# SIGTERM is expected after Stop Cloudra: shell status 143, or Python's -15 -> 241.
if [[ "$status" -ne 0 && "$status" -ne 143 && "$status" -ne 241 ]]; then
    message="Cloudra could not complete the requested action. Details are saved in $LOG"
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title=Cloudra --text="$message" --no-markup
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send --urgency=critical Cloudra "$message"
    fi
fi
exit "$status"
