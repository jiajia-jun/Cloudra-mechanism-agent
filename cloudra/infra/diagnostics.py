"""Environment self-check and read-only GitHub release update check.

All functions in this module are synchronous and may touch the local filesystem,
PATH lookups, SQLite, or the network; async callers (such as FastAPI routes)
must invoke them through ``asyncio.to_thread``.

No regular expressions are used for version parsing or validation.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cloudra import __version__

GITHUB_REPO = "yyywaa/Cloudra-mechanism-agent"
GITHUB_LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
)
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
UPDATE_CACHE_TTL_SECONDS = 15 * 60
UPDATE_TIMEOUT_SECONDS = 4.0
MAX_RELEASE_NOTES_CHARS = 1200

_update_cache: dict[str, Any] | None = None
_update_cache_at: float = 0.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_install_mode(
    executable: str | None = None,
    package_file: str | None = None,
) -> str:
    """Classify the runtime installation mode without fragile regexes."""
    exe = str(executable or sys.executable)
    pkg = str(package_file or __file__)
    combined = (exe, pkg)

    if any(".app/Contents/" in item for item in combined):
        return "macos_app"
    if any(
        item.startswith("/opt/cloudra/") or item.startswith("/usr/lib/cloudra/")
        for item in combined
    ):
        return "linux_deb"

    # Check if running from a source checkout (pyproject.toml next to cloudra/)
    try:
        repo_root = Path(pkg).resolve().parents[2]
        if (repo_root / "pyproject.toml").is_file() and (repo_root / ".git").exists():
            return "source"
    except IndexError:
        pass

    if sys.platform == "darwin":
        return "portable"
    if sys.platform.startswith("linux"):
        return "portable"
    return "source"


def parse_version_key(raw: str) -> tuple[tuple[int, ...], int, str] | None:
    """Parse a release version like ``v0.1.2`` or ``0.1.0rc1`` into a sortable key.

    Returns ``(numeric_parts, is_final, prerelease_suffix)`` where ``is_final``
    is ``1`` for final releases and ``0`` for pre-releases, so ``0.1.0rc1``
    sorts strictly before ``0.1.0``. Returns ``None`` for invalid inputs.
    """
    text = raw.strip()
    if not text:
        return None
    if text[0] in ("v", "V"):
        text = text[1:].strip()
    if not text:
        return None

    # Drop build metadata after '+'
    if "+" in text:
        text = text.split("+", 1)[0]

    # Split explicit hyphen pre-release (e.g. 0.2.0-beta.1)
    prerelease = ""
    core_text = text
    if "-" in core_text:
        core_text, prerelease = core_text.split("-", 1)

    # Split PEP 440 inline pre-release suffix attached to last numeric segment (e.g. 0.1.0rc1)
    if not prerelease:
        idx = 0
        while idx < len(core_text) and (core_text[idx].isdigit() or core_text[idx] == "."):
            idx += 1
        if idx < len(core_text):
            prerelease = core_text[idx:]
            core_text = core_text[:idx]

    if not core_text or core_text.startswith(".") or core_text.endswith("."):
        return None

    segments = core_text.split(".")
    nums: list[int] = []
    for seg in segments:
        if not seg or not seg.isdigit():
            return None
        nums.append(int(seg))

    if not nums:
        return None

    # Normalize to at least 3 segments so 0.2 == 0.2.0
    while len(nums) < 3:
        nums.append(0)

    is_final = 0 if prerelease else 1
    return (tuple(nums), is_final, prerelease.lower())


def is_newer_version(latest: str, current: str) -> bool:
    """Return True when ``latest`` is strictly newer than ``current``."""
    latest_key = parse_version_key(latest)
    current_key = parse_version_key(current)
    if latest_key is None or current_key is None:
        return False
    return latest_key > current_key


def count_active_compute_jobs() -> int:
    """Safely count active compute jobs across all projects without creating DBs."""
    try:
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import ACTIVE_STATES, _db_ready, list_compute_jobs

        db = ComputeDB()
        if not _db_ready(db):
            return 0
        jobs = list_compute_jobs(db, states=ACTIVE_STATES)
        return len(jobs)
    except Exception:
        return 0


def _slot_ready(slot: Any, codex_authenticated: bool) -> bool:
    from cloudra.infra.codex_auth import is_codex_url

    provider = str(getattr(slot, "provider", "") or "").strip().lower()
    model = str(getattr(slot, "model", "") or "").strip()
    url = str(getattr(slot, "url", "") or "").strip()
    key = str(getattr(slot, "key", "") or "").strip()

    if provider in ("openai-codex", "codex", "openai_codex") or is_codex_url(url):
        return codex_authenticated and bool(model)
    if provider == "ollama":
        return bool(model and url)
    return bool(model and url and key)


def _check_llm(cfg: Any) -> dict[str, Any]:
    codex_ok = False
    try:
        from cloudra.infra.codex_auth import codex_auth_status

        status = codex_auth_status()
        codex_ok = bool(status.get("authenticated"))
    except Exception:
        codex_ok = False

    coord_ready = _slot_ready(cfg.coordinator, codex_ok)
    follower_ready = _slot_ready(cfg.follower, codex_ok)

    if coord_ready and follower_ready:
        return {
            "id": "llm_config",
            "group": "llm",
            "status": "ready",
            "optional": False,
            "summary": "coordinator_and_follower_ready",
            "detail": (
                f"Coordinator: {cfg.coordinator.provider or 'custom'} / {cfg.coordinator.model}; "
                f"Follower: {cfg.follower.provider or 'custom'} / {cfg.follower.model}"
            ),
            "hint": "",
        }
    if coord_ready:
        return {
            "id": "llm_config",
            "group": "llm",
            "status": "ready",
            "optional": False,
            "summary": "coordinator_ready",
            "detail": (
                f"Coordinator: {cfg.coordinator.provider or 'custom'} / {cfg.coordinator.model} "
                "(Follower 未单独配置，协作子任务可选配置)"
            ),
            "hint": "configure_follower_optional",
        }
    return {
        "id": "llm_config",
        "group": "llm",
        "status": "warning",
        "optional": False,
        "summary": "llm_not_configured",
        "detail": "Coordinator 模型尚未配置 API Key 或 Codex 登录。",
        "hint": "open_global_settings_llm",
    }


def _check_python_and_rdkit() -> list[dict[str, Any]]:
    py_ok = sys.version_info >= (3, 11)
    py_ver = platform.python_version()
    checks: list[dict[str, Any]] = [
        {
            "id": "python_runtime",
            "group": "chemistry",
            "status": "ready" if py_ok else "error",
            "optional": False,
            "summary": "python_ready" if py_ok else "python_too_old",
            "detail": f"Python {py_ver}",
            "hint": "" if py_ok else "upgrade_python_311",
        }
    ]

    rdkit_spec = importlib.util.find_spec("rdkit")
    checks.append(
        {
            "id": "rdkit",
            "group": "chemistry",
            "status": "ready" if rdkit_spec is not None else "warning",
            "optional": False,
            "summary": "rdkit_ready" if rdkit_spec is not None else "rdkit_missing",
            "detail": "RDKit available" if rdkit_spec is not None else "RDKit not installed",
            "hint": "" if rdkit_spec is not None else "install_rdkit",
        }
    )

    node_path = shutil.which("node")
    checks.append(
        {
            "id": "nodejs_host",
            "group": "chemistry",
            "status": "ready" if node_path else "warning",
            "optional": False,
            "summary": "nodejs_ready" if node_path else "nodejs_missing",
            "detail": node_path or "node not found on PATH",
            "hint": "" if node_path else "install_nodejs_or_use_traditional_protocol",
        }
    )

    xtb_path = shutil.which("xtb")
    checks.append(
        {
            "id": "xtb_binary",
            "group": "chemistry",
            "status": "ready" if xtb_path else "optional_missing",
            "optional": True,
            "summary": "xtb_ready" if xtb_path else "xtb_optional_missing",
            "detail": xtb_path or "xtb not found on PATH",
            "hint": "" if xtb_path else "install_xtb_optional",
        }
    )
    return checks


def _check_compute_environment(active_jobs: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    try:
        from cloudra.services.nodes import NodeRegistry

        registry = NodeRegistry.from_environment()
        nodes = registry.public_nodes()
        remote_count = sum(1 for n in nodes if n.get("connection") == "ssh")
        slurm_count = sum(1 for n in nodes if n.get("scheduler") == "slurm")
        node_names = ", ".join(str(n.get("node_id", "")) for n in nodes)
        checks.append(
            {
                "id": "compute_nodes",
                "group": "compute",
                "status": "ready",
                "optional": False,
                "summary": "compute_nodes_loaded",
                "detail": (
                    f"{len(nodes)} node(s): {node_names} "
                    f"(SSH: {remote_count}, Slurm: {slurm_count}, active jobs: {active_jobs})"
                ),
                "hint": "",
            }
        )
    except Exception as exc:
        checks.append(
            {
                "id": "compute_nodes",
                "group": "compute",
                "status": "warning",
                "optional": False,
                "summary": "compute_nodes_config_error",
                "detail": str(exc),
                "hint": "check_nodes_config",
            }
        )

    orca_path = shutil.which("orca")
    g16_path = shutil.which("g16") or shutil.which("g09")
    gmx_path = shutil.which("gmx") or shutil.which("gmx_mpi")

    found_local: list[str] = []
    if orca_path:
        found_local.append(f"ORCA ({orca_path})")
    if g16_path:
        found_local.append(f"Gaussian ({g16_path})")
    if gmx_path:
        found_local.append(f"GROMACS ({gmx_path})")

    checks.append(
        {
            "id": "local_qm_engines",
            "group": "compute",
            "status": "ready" if found_local else "optional_missing",
            "optional": True,
            "summary": "local_engines_detected" if found_local else "local_engines_optional_missing",
            "detail": (
                "; ".join(found_local)
                if found_local
                else "No local ORCA / Gaussian / GROMACS binary found on PATH"
            ),
            "hint": "" if found_local else "configure_local_or_remote_qm",
        }
    )
    return checks


def _check_storage() -> dict[str, Any]:
    from cloudra.persistence.paths import data_dir

    root = data_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
        writable = os.access(root, os.W_OK)
        if writable:
            return {
                "id": "data_dir",
                "group": "storage",
                "status": "ready",
                "optional": False,
                "summary": "data_dir_writable",
                "detail": str(root),
                "hint": "",
            }
        return {
            "id": "data_dir",
            "group": "storage",
            "status": "error",
            "optional": False,
            "summary": "data_dir_not_writable",
            "detail": str(root),
            "hint": "fix_data_dir_permissions",
        }
    except OSError as exc:
        return {
            "id": "data_dir",
            "group": "storage",
            "status": "error",
            "optional": False,
            "summary": "data_dir_error",
            "detail": f"{root}: {exc}",
            "hint": "fix_data_dir_permissions",
        }


def run_environment_diagnostics() -> dict[str, Any]:
    """Run a fast, non-destructive capability self-check for Cloudra."""
    from cloudra.infra.config import get_config

    cfg = get_config()
    active_jobs = count_active_compute_jobs()

    checks: list[dict[str, Any]] = [
        _check_llm(cfg),
        *_check_python_and_rdkit(),
        *_check_compute_environment(active_jobs),
        _check_storage(),
    ]

    has_error = any(item["status"] == "error" for item in checks)
    has_required_warning = any(
        item["status"] == "warning" and not item["optional"] for item in checks
    )
    if has_error:
        overall = "degraded"
    elif has_required_warning:
        overall = "needs_setup"
    else:
        overall = "ready"

    return {
        "overall_status": overall,
        "version": __version__,
        "platform": sys.platform,
        "install_mode": detect_install_mode(),
        "active_compute_jobs": active_jobs,
        "checked_at": _utc_now_iso(),
        "checks": checks,
    }


def _fetch_latest_release_json() -> dict[str, Any]:
    req = urllib.request.Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Cloudra/{__version__}",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("unexpected GitHub release response")
    return parsed


def clear_update_cache() -> None:
    """Clear the in-memory update check cache (primarily for tests)."""
    global _update_cache, _update_cache_at
    _update_cache = None
    _update_cache_at = 0.0


def check_for_updates(
    *,
    force: bool = False,
    current_version: str | None = None,
    active_compute_jobs: int | None = None,
    fetcher: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check GitHub Releases for a newer version without modifying local files."""
    global _update_cache, _update_cache_at

    current = current_version or __version__
    jobs = (
        active_compute_jobs
        if active_compute_jobs is not None
        else count_active_compute_jobs()
    )
    install_mode = detect_install_mode()

    now = time.monotonic()
    if (
        not force
        and fetcher is None
        and _update_cache is not None
        and (now - _update_cache_at) < UPDATE_CACHE_TTL_SECONDS
        and _update_cache.get("current_version") == current
    ):
        cached = dict(_update_cache)
        cached["active_compute_jobs"] = jobs
        return cached

    fetch_fn = fetcher or _fetch_latest_release_json
    try:
        payload = fetch_fn()
        tag = str(payload.get("tag_name") or "").strip()
        if not tag or parse_version_key(tag) is None:
            raise ValueError("release tag_name is missing or invalid")
        latest = tag[1:] if tag[0] in ("v", "V") else tag
        release_url = str(payload.get("html_url") or GITHUB_RELEASES_PAGE)
        notes = str(payload.get("body") or "").strip()
        if len(notes) > MAX_RELEASE_NOTES_CHARS:
            notes = notes[:MAX_RELEASE_NOTES_CHARS].rstrip() + "…"
        published_at = str(payload.get("published_at") or "")
        status = "update_available" if is_newer_version(latest, current) else "up_to_date"
        result = {
            "status": status,
            "current_version": current,
            "latest_version": latest,
            "release_url": release_url,
            "release_notes": notes,
            "published_at": published_at,
            "install_mode": install_mode,
            "active_compute_jobs": jobs,
            "checked_at": _utc_now_iso(),
            "error": "",
        }
        if fetcher is None:
            _update_cache = dict(result)
            _update_cache_at = now
        return result
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "unavailable",
            "current_version": current,
            "latest_version": "",
            "release_url": GITHUB_RELEASES_PAGE,
            "release_notes": "",
            "published_at": "",
            "install_mode": install_mode,
            "active_compute_jobs": jobs,
            "checked_at": _utc_now_iso(),
            "error": str(exc),
        }
