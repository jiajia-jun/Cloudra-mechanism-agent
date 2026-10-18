"""查证「谁占着某个 runtime store 的 API 锁」——只读诊断，从不终止任何进程。

``create_default_v2_app`` 用排他 flock 保证「一个 store 只有一个 API 属主」
（见 ``services/api_v2/app.py``）；锁是归属判定的唯一权威。但 CLI 侧看不见
锁被谁持有：实测（2026-10-15）launchd 自启的 API 占着主库、而它的前端目录
已失效——既不能被复用、又不能被顶掉。CLI 于是悄悄换到空闲端口，uvicorn
子进程仍在启动阶段撞锁退出，用户只看到一句 "database is already in use"，
不知道是谁占的、也不知道该关什么。

本模块只负责把占用者（PID / 端口）与不能复用的原因说清楚；终止动作仍然
只属于 ``cloudra stop``（services/shutdown.py）。
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path
from typing import NamedTuple

from cloudra.persistence.paths import runtime_api_lock_path

_HEALTH_PATH = "/api/v2/runtime/health"
# SPA 挂载点（frontend/index.html 的 #root）：同端口既供 API 又供已构建前端，
# 才构成「可复用实例」的必要条件；launcher 还须核对目标 store 的实际属主。
_SPA_MARKER = '<div id="root"></div>'


class StoreOwner(NamedTuple):
    """持锁进程；``port`` 为 None 表示它没有健康应答的 Cloudra API。"""

    pid: int
    port: int | None
    serves_spa: bool


def _lsof(args: list[str]) -> str:
    try:
        proc = subprocess.run(["lsof", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout


def api_is_healthy(probe_host: str, port: int, *, timeout: float = 1.0) -> bool:
    """``/api/v2/runtime/health`` 是否 2xx。"""
    try:
        with urllib.request.urlopen(
            f"http://{probe_host}:{port}{_HEALTH_PATH}", timeout=timeout
        ) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def api_serves_spa(probe_host: str, port: int, *, timeout: float = 1.0) -> bool:
    """同一端口是否提供已构建的前端（可复用性的必要条件）。"""
    try:
        with urllib.request.urlopen(f"http://{probe_host}:{port}/", timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", "ignore")
            return 200 <= resp.status < 300 and _SPA_MARKER in body
    except Exception:
        return False


def _holder_pids(lock_path: str) -> list[int]:
    """打开锁文件的 PID（``lsof -t``）。"""
    return [int(token) for token in _lsof(["-t", lock_path]).split() if token.strip().isdigit()]


def _listen_ports(pid: int) -> list[int]:
    """该进程 LISTEN 的 TCP 端口（``-F n`` 只输出 ``n<addr>:<port>`` 字段行）。"""
    ports: list[int] = []
    for line in _lsof(
        ["-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-F", "n"]
    ).splitlines():
        if not line.startswith("n"):
            continue
        _, _, port_text = line.rpartition(":")
        if port_text.isdigit():
            ports.append(int(port_text))
    return ports


def find_store_owner(
    store_path: str | Path, *, probe_host: str = "127.0.0.1"
) -> StoreOwner | None:
    """占着该 store 的 API 进程；探不到（无人持锁 / 无 lsof）返回 None。

    「是否被占用」由调用方用 flock 判定（infra/flocks.py）——这里只把持有者的
    PID 与端口查出来，供报错文案使用。若持有者活着但探测不到健康 API（残留或
    卡住的进程），仍返回 pid 且 ``port=None``，以便如实报出。
    """
    lock_path = str(runtime_api_lock_path(store_path))
    fallback: StoreOwner | None = None
    for pid in _holder_pids(lock_path):
        for port in _listen_ports(pid):
            if api_is_healthy(probe_host, port):
                return StoreOwner(pid, port, api_serves_spa(probe_host, port))
        if fallback is None:
            fallback = StoreOwner(pid, None, False)
    return fallback


def describe_store_conflict(
    store_path: str | Path,
    owner: StoreOwner | None,
    *,
    reuse_allowed: bool = True,
) -> str:
    """主库被别家占着时的可执行提示：谁、在哪、为什么不能复用、怎么收场。"""
    if owner is None:
        holder = "占用者进程查不到（lsof 不可用，或锁由别的用户/PID 命名空间持有）"
    elif owner.port is None:
        holder = (
            f"pid {owner.pid} 持有锁，但它没有健康应答的 Cloudra API"
            "（可能是残留或卡住的进程）"
        )
    else:
        holder = f"pid {owner.pid} 正在端口 {owner.port} 上提供同库的 Cloudra API"
        if not owner.serves_spa:
            holder += "，但该端口没有提供已构建的前端（GET / 不是 SPA），因此不能复用"
        elif not reuse_allowed:
            holder += "，但通配绑定下无法确认它实际监听的地址，因此不复用"
    return (
        "Cloudra 主库已被其他实例占用。\n"
        f"  主库：{store_path}\n"
        f"  占用者：{holder}\n"
        "  处理：先运行 `cloudra stop` 停掉它；若它由 launchd / systemd / 自启脚本"
        "拉起，必须先停掉那个自启机制，否则停掉后会被立刻重新拉起。"
    )
