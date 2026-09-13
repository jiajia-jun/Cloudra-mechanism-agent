"""Filesystem navigation and directory picking routes."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from ..context import ApiContext
from ..models import (
    FsBrowseEntry,
    FsBrowseResponse,
    FsBrowseShortcut,
    FsMkdirRequest,
    FsSystemPickerResponse,
)


def _list_directory(target_path_str: str | None, show_hidden: bool) -> dict[str, Any]:
    """同步执行目录扫描与快捷方式收集（卸载到工作线程）。"""
    if target_path_str and target_path_str.strip():
        p = Path(target_path_str.strip()).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            if p.parent.exists() and p.parent.is_dir():
                p = p.parent
            else:
                p = Path.home()
    else:
        p = Path.home()

    # 快捷路径
    shortcuts: list[dict[str, str]] = []
    try:
        home = Path.home()
        shortcuts.append({"name": "Home", "path": str(home)})
        desktop = home / "Desktop"
        if desktop.is_dir():
            shortcuts.append({"name": "Desktop", "path": str(desktop)})
        documents = home / "Documents"
        if documents.is_dir():
            shortcuts.append({"name": "Documents", "path": str(documents)})
    except Exception:
        home = Path("/")

    try:
        cwd = Path.cwd()
        shortcuts.append({"name": "CWD", "path": str(cwd)})
    except Exception:
        cwd = home

    shortcuts.append({"name": "Root", "path": "/"})

    parent_str: str | None = None
    if p.parent != p and p != Path("/"):
        parent_str = str(p.parent)

    entries: list[dict[str, Any]] = []
    try:
        with os.scandir(p) as it:
            for entry in it:
                try:
                    if not show_hidden and entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=True):
                        try:
                            mtime = entry.stat().st_mtime
                        except OSError:
                            mtime = None
                        entries.append({
                            "name": entry.name,
                            "path": str(Path(entry.path).resolve()),
                            "is_dir": True,
                            "mtime": mtime,
                        })
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass

    entries.sort(key=lambda e: e["name"].lower())

    writable = False
    try:
        writable = os.access(p, os.W_OK)
    except Exception:
        pass

    return {
        "current": str(p),
        "parent": parent_str,
        "home": str(home),
        "cwd": str(cwd),
        "shortcuts": shortcuts,
        "entries": entries,
        "writable": writable,
    }


def _create_directory(path_str: str) -> str:
    """同步创建目录（卸载到工作线程）。"""
    p = Path(path_str.strip()).expanduser().resolve()
    os.makedirs(p, exist_ok=True)
    return str(p)


def _open_system_picker() -> dict[str, Any]:
    """在支持的平台同步唤起系统文件选择对话框（卸载到工作线程）。"""
    if sys.platform == "darwin" and shutil.which("osascript"):
        script = 'POSIX path of (choose folder with prompt "Select Workspace Directory")'
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode == 0:
                chosen = res.stdout.strip().rstrip("/")
                if chosen:
                    return {"supported": True, "path": chosen, "canceled": False}
            return {"supported": True, "path": None, "canceled": True}
        except Exception:
            return {"supported": False, "path": None, "canceled": False}
    return {"supported": False, "path": None, "canceled": False}


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/fs/browse", dependencies=ctx.protected)
    async def browse_fs(path: str | None = None, show_hidden: bool = False) -> FsBrowseResponse:
        data = await asyncio.to_thread(_list_directory, path, show_hidden)
        return FsBrowseResponse(
            current=data["current"],
            parent=data["parent"],
            home=data["home"],
            cwd=data["cwd"],
            shortcuts=[FsBrowseShortcut(**s) for s in data["shortcuts"]],
            entries=[FsBrowseEntry(**e) for e in data["entries"]],
            writable=data["writable"],
        )

    @router.post("/api/v2/fs/mkdir", dependencies=ctx.protected)
    async def mkdir_fs(body: FsMkdirRequest) -> dict[str, Any]:
        target = await asyncio.to_thread(_create_directory, body.path)
        return {"success": True, "path": target}

    @router.post("/api/v2/fs/system-picker", dependencies=ctx.protected)
    async def system_picker() -> FsSystemPickerResponse:
        res = await asyncio.to_thread(_open_system_picker)
        return FsSystemPickerResponse(**res)

    return router
