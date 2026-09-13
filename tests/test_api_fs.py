"""Tests for filesystem navigation API endpoints (/api/v2/fs/*)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cloudra.services.api_v2 import create_v2_app


@pytest.fixture
def client():
    app = create_v2_app()
    return TestClient(app)


def test_fs_browse_default(client):
    resp = client.get("/api/v2/fs/browse")
    assert resp.status_code == 200
    data = resp.json()
    assert "current" in data
    assert "home" in data
    assert "cwd" in data
    assert "shortcuts" in data
    assert any(s["name"] == "Home" for s in data["shortcuts"])
    assert any(s["name"] == "Root" for s in data["shortcuts"])
    assert isinstance(data["entries"], list)


def test_fs_browse_custom_path(client, tmp_path):
    d1 = tmp_path / "alpha"
    d2 = tmp_path / "beta"
    hidden = tmp_path / ".secret"
    d1.mkdir()
    d2.mkdir()
    hidden.mkdir()
    (tmp_path / "regular_file.txt").write_text("hello")

    resp = client.get(f"/api/v2/fs/browse?path={tmp_path}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] == str(tmp_path)
    assert data["parent"] == str(tmp_path.parent)
    names = [e["name"] for e in data["entries"]]
    assert "alpha" in names
    assert "beta" in names
    assert "regular_file.txt" not in names  # only directories returned
    assert ".secret" not in names  # hidden ignored by default

    # with show_hidden=true
    resp_hidden = client.get(f"/api/v2/fs/browse?path={tmp_path}&show_hidden=true")
    assert resp_hidden.status_code == 200
    names_hidden = [e["name"] for e in resp_hidden.json()["entries"]]
    assert ".secret" in names_hidden


def test_fs_browse_nonexistent_path_fallback(client, tmp_path):
    nonexistent = tmp_path / "does_not_exist"
    resp = client.get(f"/api/v2/fs/browse?path={nonexistent}")
    assert resp.status_code == 200
    data = resp.json()
    # Falls back to parent (which is tmp_path)
    assert data["current"] == str(tmp_path)


def test_fs_mkdir(client, tmp_path):
    new_dir = tmp_path / "nested" / "project_ws"
    resp = client.post("/api/v2/fs/mkdir", json={"path": str(new_dir)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["path"] == str(new_dir)
    assert new_dir.is_dir()


def test_fs_system_picker_endpoint(client):
    resp = client.post("/api/v2/fs/system-picker")
    assert resp.status_code == 200
    data = resp.json()
    assert "supported" in data
    assert "canceled" in data
