import sqlite3
import zipfile

import pytest

from cloudra.infra.operations import (
    BackupError,
    create_backup,
    operational_status,
    restore_backup,
    verify_backup,
)


def test_backup_snapshots_sqlite_and_restores_verified_files(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "memory").mkdir()
    (data / "memory" / "MEMORY.md").write_text("remember me", encoding="utf-8")
    database = data / "device-broker.db"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE devices(id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO devices VALUES ('phone-a')")
        con.commit()

    backup = tmp_path / "backup.zip"
    manifest = create_backup(data, backup)
    assert {item["path"] for item in manifest["files"]} == {
        "device-broker.db",
        "memory/MEMORY.md",
    }
    assert verify_backup(backup) == manifest

    restored = tmp_path / "restored"
    restore_backup(backup, restored)
    assert (restored / "memory" / "MEMORY.md").read_text() == "remember me"
    with sqlite3.connect(restored / "device-broker.db") as con:
        assert con.execute("SELECT id FROM devices").fetchone() == ("phone-a",)


def test_backup_rejects_tampering_and_nonempty_restore(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "state.json").write_text("{}", encoding="utf-8")
    backup = tmp_path / "backup.zip"
    create_backup(data, backup)
    with zipfile.ZipFile(backup, "a") as archive:
        archive.writestr("data/unlisted.txt", "oops")
    with pytest.raises(BackupError, match="unlisted"):
        verify_backup(backup)

    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(BackupError):
        restore_backup(backup, destination)


def test_operational_status_is_bounded_and_alerts_without_content(tmp_path):
    root = tmp_path / "data"
    database = root / "conversations" / "conv-a" / "tasks" / "database.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE session(state TEXT, query TEXT)")
        con.execute("CREATE TABLE compute_jobs(state TEXT, last_error TEXT)")
        con.execute("INSERT INTO session VALUES ('interrupted', 'private prompt')")
        con.execute("INSERT INTO compute_jobs VALUES ('failed', 'secret error')")
        con.commit()

    status = operational_status(root, min_free_bytes=0)
    assert status["status"] == "degraded"
    assert status["sessions"] == {"interrupted": 1}
    assert status["compute_jobs"] == {"failed": 1}
    assert "private prompt" not in str(status)
    assert "secret error" not in str(status)
