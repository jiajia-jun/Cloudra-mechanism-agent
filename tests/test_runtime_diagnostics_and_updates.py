"""Tests for environment diagnostics and read-only GitHub release update check."""

from __future__ import annotations

import urllib.error
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from cloudra.infra import diagnostics as diag
from cloudra.services.api_v2 import create_v2_app


def test_parse_version_key_and_comparisons():
    assert diag.parse_version_key("v0.1.1") == ((0, 1, 1), 1, "")
    assert diag.parse_version_key("0.2") == ((0, 2, 0), 1, "")
    assert diag.parse_version_key("0.1.0rc1") == ((0, 1, 0), 0, "rc1")
    assert diag.parse_version_key("0.2.0-beta.1") == ((0, 2, 0), 0, "beta.1")
    assert diag.parse_version_key("") is None
    assert diag.parse_version_key("v") is None
    assert diag.parse_version_key("not-a-version") is None

    assert diag.is_newer_version("v0.1.2", "0.1.1") is True
    assert diag.is_newer_version("0.1.0", "0.1.0rc1") is True
    assert diag.is_newer_version("0.2.0", "0.2.0-beta.1") is True
    assert diag.is_newer_version("0.1.1", "0.1.1") is False
    assert diag.is_newer_version("0.1.0", "0.1.1") is False
    assert diag.is_newer_version("invalid", "0.1.1") is False


def test_detect_install_mode():
    assert diag.detect_install_mode(
        executable="/Applications/Cloudra.app/Contents/MacOS/python",
        package_file="/Applications/Cloudra.app/Contents/Resources/cloudra/infra/diagnostics.py",
    ) == "macos_app"
    assert diag.detect_install_mode(
        executable="/opt/cloudra/venv/bin/python",
        package_file="/opt/cloudra/venv/lib/python3.11/site-packages/cloudra/infra/diagnostics.py",
    ) == "linux_deb"
    assert diag.detect_install_mode() == "source"


def test_check_for_updates_states_and_cache(monkeypatch: pytest.MonkeyPatch):
    diag.clear_update_cache()

    calls = 0

    def fake_fetch():
        nonlocal calls
        calls += 1
        return {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/yyywaa/Cloudra-mechanism-agent/releases/tag/v0.2.0",
            "body": "A" * 2000,
            "published_at": "2026-11-21T00:00:00Z",
        }

    monkeypatch.setattr(diag, "_fetch_latest_release_json", fake_fetch)

    first = diag.check_for_updates(current_version="0.1.1", active_compute_jobs=2)
    assert first["status"] == "update_available"
    assert first["latest_version"] == "0.2.0"
    assert first["active_compute_jobs"] == 2
    assert first["release_notes"].endswith("…")
    assert len(first["release_notes"]) <= diag.MAX_RELEASE_NOTES_CHARS + 1
    assert calls == 1

    # Second non-forced call uses cache but refreshes active_compute_jobs.
    second = diag.check_for_updates(current_version="0.1.1", active_compute_jobs=0)
    assert second["status"] == "update_available"
    assert second["active_compute_jobs"] == 0
    assert calls == 1

    # Forced call bypasses cache.
    third = diag.check_for_updates(force=True, current_version="0.2.0", active_compute_jobs=1)
    assert third["status"] == "up_to_date"
    assert calls == 2

    # Offline / network failure degrades gracefully.
    def failing_fetch():
        raise urllib.error.URLError("offline")

    offline = diag.check_for_updates(
        force=True,
        current_version="0.1.1",
        active_compute_jobs=0,
        fetcher=failing_fetch,
    )
    assert offline["status"] == "unavailable"
    assert "offline" in offline["error"]
    assert offline["release_url"] == diag.GITHUB_RELEASES_PAGE


def test_run_environment_diagnostics_groups_and_optional_handling(monkeypatch: pytest.MonkeyPatch, tmp_path):
    fake_cfg = SimpleNamespace(
        coordinator=SimpleNamespace(provider="deepseek", model="deepseek-4-pro", url="https://api.deepseek.com/", key=""),
        follower=SimpleNamespace(provider="deepseek", model="deepseek-4-pro", url="https://api.deepseek.com/", key=""),
        data_dir=str(tmp_path),
    )
    monkeypatch.setattr("cloudra.infra.config.get_config", lambda: fake_cfg)
    monkeypatch.setattr("cloudra.infra.codex_auth.codex_auth_status", lambda: {"authenticated": False})
    monkeypatch.setattr(diag.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)

    report = diag.run_environment_diagnostics()
    assert report["overall_status"] == "needs_setup"
    checks_by_id = {c["id"]: c for c in report["checks"]}
    assert checks_by_id["llm_config"]["status"] == "warning"
    assert checks_by_id["xtb_binary"]["status"] == "optional_missing"
    assert checks_by_id["xtb_binary"]["optional"] is True
    assert checks_by_id["local_qm_engines"]["status"] == "optional_missing"
    assert checks_by_id["data_dir"]["status"] == "ready"


def test_runtime_diagnostics_and_update_endpoints(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "off")
    diag.clear_update_cache()
    monkeypatch.setattr(
        diag,
        "_fetch_latest_release_json",
        lambda: {
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/yyywaa/Cloudra-mechanism-agent/releases/tag/v9.9.9",
            "body": "Test release notes",
            "published_at": "2026-11-21T00:00:00Z",
        },
    )

    with TestClient(create_v2_app()) as client:
        d_resp = client.get("/api/v2/runtime/diagnostics")
        assert d_resp.status_code == 200
        d_body = d_resp.json()
        assert d_body["overall_status"] in {"ready", "needs_setup", "degraded"}
        assert isinstance(d_body["checks"], list)
        assert any(c["id"] == "llm_config" for c in d_body["checks"])

        u_resp = client.get("/api/v2/runtime/update-check?force=true")
        assert u_resp.status_code == 200
        u_body = u_resp.json()
        assert u_body["status"] == "update_available"
        assert u_body["latest_version"] == "9.9.9"
