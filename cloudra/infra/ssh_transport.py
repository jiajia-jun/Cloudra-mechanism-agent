"""SSH 传输层：远端计算节点的唯一触达原语。

只做 argv 组装与 subprocess 执行，不含业务状态。本地调用一律纯 argv
（无 ``shell=True``）；远端命令字符串内嵌的路径全部来自注册表 connection
快照（``services/nodes.py`` 已做字符白名单校验）或 int task_id，并再经
``shlex.quote`` 转义。所有函数都是同步阻塞的——协程里的调用点一律走
``asyncio.to_thread``（事件循环铁律）。
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class SshError(RuntimeError):
    pass


@dataclass(frozen=True)
class SshEndpoint:
    """一个远端节点的连接参数。

    账本行 ``scheduler_options.connection`` 快照是唯一事实源（提交时从注册表
    拷入，之后改注册表不影响在飞作业）；``from_connection`` 只做形状校验，
    字符白名单在注册表加载（nodes.py）时已强制。
    """

    host: str
    user: str
    port: int
    remote_root: str
    identity_file: str | None = None

    @classmethod
    def from_connection(cls, connection: dict) -> "SshEndpoint":
        if str(connection.get("type") or "") != "ssh":
            raise SshError(f"connection is not ssh: {connection!r}")
        try:
            host = str(connection["host"]).strip()
            user = str(connection["user"]).strip()
            remote_root = str(connection["remote_root"]).strip()
            port = int(connection.get("port", 22))
        except (KeyError, TypeError, ValueError) as exc:
            raise SshError(f"incomplete ssh connection snapshot: {connection!r}") from exc
        if not host or not user or not remote_root:
            raise SshError(f"incomplete ssh connection snapshot: {connection!r}")
        identity = connection.get("identity_file")
        return cls(
            host=host,
            user=user,
            port=port,
            remote_root=remote_root,
            identity_file=str(identity) if identity else None,
        )

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"

    def job_dir(self, task_id: int) -> str:
        """远端作业目录：``<remote_root>/cloudra-<task_id>``（按作业隔离）。"""
        return f"{self.remote_root}/cloudra-{task_id}"


def ssh_argv(endpoint: SshEndpoint) -> list[str]:
    """ssh 命令前缀（BatchMode 禁交互，10s 连接超时）。"""
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if endpoint.identity_file:
        argv += ["-i", endpoint.identity_file]
    argv += ["-p", str(endpoint.port), endpoint.target]
    return argv


def run_remote(
    endpoint: SshEndpoint, remote_cmd: str, *, timeout: float = 30
) -> tuple[int, str, str]:
    """在远端执行一条命令，返回 ``(rc, stdout, stderr)``；传输失败抛 SshError。"""
    try:
        completed = subprocess.run(
            [*ssh_argv(endpoint), remote_cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SshError(f"ssh to {endpoint.target} failed: {exc}") from exc
    return completed.returncode, completed.stdout, completed.stderr


def run_remote_checked(
    endpoint: SshEndpoint, remote_cmd: str, *, timeout: float = 30
) -> str:
    """远端命令必须 rc=0，否则抛 SshError（带远端 stderr 摘要）。"""
    rc, stdout, stderr = run_remote(endpoint, remote_cmd, timeout=timeout)
    if rc != 0:
        raise SshError(
            f"remote command failed on {endpoint.target} (rc={rc}): "
            f"{(stderr or stdout).strip()[:2000]}"
        )
    return stdout


def _rsync_ssh_opt(endpoint: SshEndpoint) -> str:
    return shlex.join(ssh_argv(endpoint))


def _check_local_rsync() -> None:
    if shutil.which("rsync") is None:
        raise SshError(
            "rsync is required for remote compute staging; install rsync on this "
            "machine and on the remote host."
        )


def _rsync_base(endpoint: SshEndpoint) -> list[str]:
    return ["rsync", "-az", "-e", _rsync_ssh_opt(endpoint)]


def _run_rsync(argv: list[str], timeout: float) -> None:
    try:
        completed = subprocess.run(
            argv, check=False, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SshError(f"rsync failed to start: {exc}") from exc
    if completed.returncode != 0:
        raise SshError(
            f"rsync failed (rc={completed.returncode}): "
            f"{(completed.stderr or completed.stdout).strip()[:2000]}"
        )


def push_dir(
    endpoint: SshEndpoint,
    local_dir: str | Path,
    remote_dir: str,
    *,
    excludes: tuple[str, ...] = (),
    timeout: float = 300,
) -> None:
    """把本地目录内容同步进远端目录（自动先 ``mkdir -p`` 远端目录）。"""
    _check_local_rsync()
    run_remote_checked(endpoint, f"mkdir -p {shlex.quote(remote_dir)}")
    argv = [*_rsync_base(endpoint)]
    for pattern in excludes:
        argv += ["--exclude", pattern]
    argv += [f"{Path(local_dir)}/", f"{endpoint.target}:{shlex.quote(remote_dir)}/"]
    _run_rsync(argv, timeout)


def push_files(
    endpoint: SshEndpoint,
    local_paths: list[str | Path],
    remote_dir: str,
    *,
    timeout: float = 300,
) -> None:
    """把若干本地文件平铺推进远端目录（自动先 ``mkdir -p``）。"""
    _check_local_rsync()
    run_remote_checked(endpoint, f"mkdir -p {shlex.quote(remote_dir)}")
    argv = [
        *_rsync_base(endpoint),
        *[str(path) for path in local_paths],
        f"{endpoint.target}:{shlex.quote(remote_dir)}/",
    ]
    _run_rsync(argv, timeout)


def pull_dir(
    endpoint: SshEndpoint,
    remote_dir: str,
    local_dir: str | Path,
    *,
    timeout: float = 600,
) -> None:
    """把远端作业目录的全部产物拉回本地目录（合并，不删除本地多余文件）。"""
    _check_local_rsync()
    argv = [
        *_rsync_base(endpoint),
        f"{endpoint.target}:{shlex.quote(remote_dir)}/",
        f"{Path(local_dir)}/",
    ]
    _run_rsync(argv, timeout)


# 远端二进制探测缓存：准入每次提交都查引擎可用性，ssh 往返按 (端点, 目标集) 缓存。
_BIN_PROBE_TTL_SECONDS = 300.0
_bin_probe_cache: dict[tuple, tuple[float, tuple[str, ...]]] = {}


def check_remote_bins(
    endpoint: SshEndpoint, bins: list[str], *, refresh: bool = False
) -> tuple[bool, list[str]]:
    """探测远端 PATH 上的可执行程序；返回 ``(全齐?, 缺失列表)``。

    单次 ssh 完成全部探测（远端循环逐个 ``command -v``，缺失项以
    ``MISSING:<name>`` 标记行回报，精确整行比对）。bins 来自本包内置常量
    （``compute_utils._REQUIRED_BINS`` 等），不是外部输入。传输失败抛 SshError。
    """
    key = (endpoint.host, endpoint.user, endpoint.port, tuple(sorted(bins)))
    now = time.monotonic()
    hit = _bin_probe_cache.get(key)
    if hit and not refresh and now - hit[0] < _BIN_PROBE_TTL_SECONDS:
        missing = list(hit[1])
        return (not missing, missing)
    probes = "; ".join(
        f"command -v {name} >/dev/null 2>&1 || echo MISSING:{name}" for name in bins
    )
    rc, stdout, stderr = run_remote(endpoint, probes, timeout=30)
    if rc != 0:
        raise SshError(
            f"remote probe failed on {endpoint.target} (rc={rc}): "
            f"{(stderr or stdout).strip()[:2000]}"
        )
    missing = []
    seen = set()
    for line in stdout.splitlines():
        token = line.strip()
        if token.startswith("MISSING:"):
            name = token[len("MISSING:"):].strip()
            if name in bins and name not in seen:
                seen.add(name)
                missing.append(name)
    _bin_probe_cache[key] = (now, tuple(missing))
    return (not missing, missing)


def check_remote_environment(
    endpoint: SshEndpoint, job_type: str, *, slurm: bool
) -> tuple[bool, str]:
    """远端节点准入探针：引擎 + 传输依赖（rsync/bash）+ Slurm 工具链。

    本地另需 rsync。任何缺失/不可达都 fail-loud 给出可读原因。
    """
    from cloudra.infra.compute_utils import _REQUIRED_BINS

    bins = _REQUIRED_BINS.get(job_type)
    if bins is None:
        return False, f"Unsupported job_type: {job_type}"
    if shutil.which("rsync") is None:
        return False, (
            "rsync is required locally to stage jobs to a remote node; "
            "install rsync and resubmit."
        )
    remote_bins = [*bins, "bash", "rsync"]
    if slurm:
        remote_bins += ["sbatch", "sacct", "scancel"]
    try:
        ok, missing = check_remote_bins(endpoint, remote_bins)
    except SshError as exc:
        return False, (
            f"Remote node {endpoint.target} is unreachable: {exc}. "
            "Check the node's connection block (host/user/port/identity_file) "
            "and SSH key authorization."
        )
    if not ok:
        return False, (
            f"Remote node {endpoint.target} is missing required programs: "
            f"{', '.join(missing)}. Install them or fix PATH/modules on the "
            "remote host, then resubmit."
        )
    return True, ""
