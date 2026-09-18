"""持久运行现场的共享件：编号运行目录、版本记录、产物清点、进程组终止。

``crest_runner`` 与 ``xtb_path_runner`` 共用（此前两份逐字重复）。本模块只做文件/进程
事实的机械操作，不含任何引擎判定逻辑；各运行器自己的 pydantic 产物模型由各自构造。
"""

from __future__ import annotations

import os
import signal
import subprocess


def next_run_dir(output_dir: str, runs_dir_name: str, run_label: str) -> str:
    """``<output_dir>/<runs_dir_name>/<label>_<NNNN>``：编号单调递增，便于按运行次序复查。"""
    safe_label = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in run_label) or "run"
    runs_root = os.path.join(output_dir, runs_dir_name)
    os.makedirs(runs_root, exist_ok=True)
    used = set()
    for name in os.listdir(runs_root):
        head, _, tail = name.rpartition("_")
        if head == safe_label and tail.isdigit():
            used.add(int(tail))
    index = 1
    while index in used:
        index += 1
    run_dir = os.path.join(runs_root, f"{safe_label}_{index:04d}")
    os.makedirs(run_dir, exist_ok=False)
    return run_dir


def capture_versions(executables: tuple[str, ...], markers: tuple[str, ...]) -> str:
    """记录实际引擎版本；只取含 ``markers`` 任一 token 的版本行，不落环境变量。

    版本取不到不阻塞运行，如实记录失败原因。
    """
    lines: list[str] = []
    for name in executables:
        try:
            proc = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=60)
        except Exception as exc:  # noqa: BLE001 - 版本取不到不阻塞运行，如实记录
            lines.append(f"{name} --version failed: {type(exc).__name__}: {exc}")
            continue
        text = (proc.stdout or "") + (proc.stderr or "")
        interesting = [
            line.strip() for line in text.splitlines()
            if any(marker in line for marker in markers)
        ]
        lines.append(f"{name} --version (returncode={proc.returncode}):")
        lines.extend(f"    {line}" for line in (interesting or ["<no version line found>"]))
    return "\n".join(lines) + "\n"


def list_artifact_files(run_dir: str) -> list[tuple[str, str, int]]:
    """运行目录里的常规文件清单：``(文件名, 绝对路径, 字节数)``，按文件名排序。"""
    artifacts: list[tuple[str, str, int]] = []
    for name in sorted(os.listdir(run_dir)):
        path = os.path.join(run_dir, name)
        if os.path.isfile(path):
            artifacts.append((name, path, os.path.getsize(path)))
    return artifacts


def terminate_process_group(proc: subprocess.Popen) -> None:
    """先 SIGTERM 再 SIGKILL **本进程组**，并 wait/reap，绝不只发信号不回收。

    POSIX 用 ``os.getpgid``/``os.killpg`` 进程组信号；Windows 无进程组语义
    （``os.getpgid``/``os.killpg``/``signal.SIGKILL`` 都不存在），降级为对
    单个子进程 terminate → kill 并回收——终止并回收的契约不变，只是覆盖面
    从进程组缩到单进程（GH #40）。
    """
    if not (hasattr(os, "getpgid") and hasattr(os, "killpg")):
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            proc.kill()
        except ProcessLookupError:
            return
        proc.wait()
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        proc.wait()
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue
    proc.wait()
