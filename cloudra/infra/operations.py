"""Production backup and restore primitives for the Cloudra data directory."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cloudra import __version__


class BackupError(RuntimeError):
    pass


def _count_states(database: Path, table: str, allowed_tables: set[str]) -> Counter:
    if table not in allowed_tables:
        raise ValueError("unsupported metrics table")
    try:
        uri = f"file:{database.as_posix()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=2)) as con:
            return Counter(dict(con.execute(
                f"SELECT state, COUNT(*) FROM {table} GROUP BY state"
            ).fetchall()))
    except sqlite3.Error:
        return Counter()


def operational_status(data_dir: Path, *, min_free_bytes: int = 1024**3) -> dict:
    """Return bounded-cardinality operational counters without user content."""
    root = data_dir.expanduser().resolve()
    sessions: Counter = Counter()
    compute: Counter = Counter()
    database_errors = 0
    conversation_databases = list(root.glob("conversations/*/tasks/database.db"))
    for database in conversation_databases:
        try:
            sessions.update(_count_states(database, "session", {"session"}))
            with contextlib.closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as con:
                con.execute("PRAGMA quick_check").fetchone()
        except sqlite3.Error:
            database_errors += 1
    # compute_jobs 已迁到中央库：状态计数只读 data_dir/compute.db
    compute_database = root / "compute.db"
    if compute_database.is_file():
        compute.update(_count_states(compute_database, "compute_jobs", {"compute_jobs"}))
    devices: Counter = Counter()
    device_database = root / "device-broker.db"
    if device_database.is_file():
        devices.update(_count_states(device_database, "devices", {"devices"}))
    free_bytes = shutil.disk_usage(root).free if root.exists() else 0
    alerts: list[dict] = []
    if free_bytes < min_free_bytes:
        alerts.append({"code": "disk_free_low", "severity": "critical"})
    if database_errors:
        alerts.append({"code": "database_check_failed", "severity": "critical"})
    if compute.get("failed", 0):
        alerts.append({"code": "compute_failures_present", "severity": "warning"})
    if sessions.get("interrupted", 0):
        alerts.append({"code": "interrupted_sessions_present", "severity": "warning"})
    return {
        "status": "degraded" if alerts else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conversation_databases": len(conversation_databases),
        "database_errors": database_errors,
        "disk_free_bytes": free_bytes,
        "sessions": dict(sorted(sessions.items())),
        "compute_jobs": dict(sorted(compute.items())),
        "devices": dict(sorted(devices.items())),
        "alerts": alerts,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(name: str) -> Path:
    posix = PurePosixPath(name)
    if posix.is_absolute() or not posix.parts or ".." in posix.parts:
        raise BackupError(f"unsafe backup member: {name!r}")
    return Path(*posix.parts)


def create_backup(data_dir: Path, destination: Path) -> dict:
    """Create a verified zip; live SQLite files use the online backup API."""
    root = data_dir.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise BackupError(f"data directory is not a directory: {root}")
    target = destination.expanduser().resolve()
    if target == root or root in target.parents:
        raise BackupError("backup destination must be outside the data directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise BackupError(f"backup already exists: {target}")

    manifest_files: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cloudra-backup-") as raw_temp:
        staging = Path(raw_temp)
        for source in sorted(root.rglob("*")):
            if source.is_symlink():
                raise BackupError(f"symlink is not allowed in data directory: {source}")
            if not source.is_file() or source.name.endswith(("-wal", "-shm")):
                continue
            relative = source.relative_to(root)
            snapshot = staging / relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".db":
                try:
                    with (
                        contextlib.closing(sqlite3.connect(source)) as src,
                        contextlib.closing(sqlite3.connect(snapshot)) as dst,
                    ):
                        src.backup(dst)
                except sqlite3.Error as exc:
                    raise BackupError(f"cannot snapshot SQLite database: {source}") from exc
            else:
                shutil.copy2(source, snapshot)
            manifest_files.append(
                {
                    "path": relative.as_posix(),
                    "size": snapshot.stat().st_size,
                    "sha256": _sha256(snapshot),
                }
            )
        manifest = {
            "format": 1,
            "cloudra_version": __version__,
            "created_at": int(time.time()),
            "files": manifest_files,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_target = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            with zipfile.ZipFile(
                temporary_target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                archive.write(staging / "manifest.json", "manifest.json")
                for item in manifest_files:
                    archive.write(staging / item["path"], f"data/{item['path']}")
            verify_backup(temporary_target)
            os.replace(temporary_target, target)
        finally:
            temporary_target.unlink(missing_ok=True)
    return manifest


def verify_backup(archive_path: Path) -> dict:
    archive_path = archive_path.expanduser().resolve(strict=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = set(archive.namelist())
            if "manifest.json" not in names:
                raise BackupError("backup has no manifest.json")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != 1 or not isinstance(manifest.get("files"), list):
                raise BackupError("unsupported backup manifest")
            expected_names = {"manifest.json"}
            for item in manifest["files"]:
                relative = _safe_relative(item.get("path", ""))
                member = f"data/{relative.as_posix()}"
                expected_names.add(member)
                payload = archive.read(member)
                if len(payload) != item.get("size"):
                    raise BackupError(f"size mismatch: {relative}")
                if hashlib.sha256(payload).hexdigest() != item.get("sha256"):
                    raise BackupError(f"checksum mismatch: {relative}")
            if names != expected_names:
                raise BackupError("backup contains unlisted members")
            return manifest
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"invalid backup: {archive_path}") from exc


def restore_backup(archive_path: Path, destination: Path) -> dict:
    """Restore only into a missing or empty directory, then re-verify every file."""
    manifest = verify_backup(archive_path)
    target = destination.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"restore destination is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as archive:
        for item in manifest["files"]:
            relative = _safe_relative(item["path"])
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(f"data/{relative.as_posix()}") as source, output.open("xb") as sink:
                shutil.copyfileobj(source, sink)
            if _sha256(output) != item["sha256"]:
                raise BackupError(f"restored checksum mismatch: {relative}")
    return manifest
