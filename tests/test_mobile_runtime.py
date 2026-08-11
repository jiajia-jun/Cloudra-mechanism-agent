"""Android single-process runtime capability tests."""

from __future__ import annotations

import compileall
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import tomllib

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.runtime_profile import filter_tools_for_runtime, is_mobile_runtime
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.tools import ToolEntry


class _NoArgs(input_schema):
    pass


class _Result(output_schema):
    message: str


class _ForbiddenBash(Tool):
    tool_id: str = "mobile-forbidden"
    tool_name: str = "bashtools"
    tool_description: str = "test-only forbidden tool"
    input_schema: Any = _NoArgs
    output_schema: Any = _Result
    called: bool = False

    async def tool_call(self, user_input, session):
        self.called = True
        return _Result(message="must not run")


def _entry(tool_cls: type[Tool]) -> ToolEntry:
    return ToolEntry(
        cls=tool_cls,
        tool_name=tool_cls._get_field_default("tool_name") or "",
        tool_id=tool_cls._get_field_default("tool_id") or "",
        input_schema=tool_cls._get_field_default("input_schema"),
    )


def test_mobile_runtime_can_be_exercised_on_desktop(monkeypatch):
    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    assert is_mobile_runtime() is True

    entries = [
        SimpleNamespace(tool_name="edit_file"),
        SimpleNamespace(tool_name="SubAgentLauncher"),
        SimpleNamespace(tool_name="schedule"),
        SimpleNamespace(tool_name="bashtools"),
        SimpleNamespace(tool_name="submit_compute_job"),
    ]
    assert [entry.tool_name for entry in filter_tools_for_runtime(entries)] == [
        "edit_file",
        "SubAgentLauncher",
        "schedule",
    ]


def test_desktop_runtime_keeps_registered_tools(monkeypatch):
    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "false")
    entries = [
        SimpleNamespace(tool_name="edit_file"),
        SimpleNamespace(tool_name="bashtools"),
    ]
    assert filter_tools_for_runtime(entries) == entries


def test_packaged_app_uses_durable_flet_storage(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config
    from cloudra.infra.mobile_storage import configure_app_storage

    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    storage = configure_app_storage()

    assert storage.packaged is True
    assert storage.workspace == (tmp_path / "workspace").resolve()
    assert storage.workspace.is_dir()
    assert get_config().data_dir == (tmp_path / "cloudra-data").resolve()
    assert get_config().config_file == (tmp_path / "config.yaml").resolve()


def test_packaged_app_defaults_to_remote_backend_without_local_service(
    tmp_path,
    monkeypatch,
):
    from cloudra.infra.mobile_storage import AppStorage
    from cloudra.services.backends import RemoteCloudraBackend, create_default_backend

    monkeypatch.setenv("CLOUDRA_SERVER_URL", "https://cloudra.example.test")
    storage = AppStorage(
        data_dir=tmp_path,
        config_file=tmp_path / "config.yaml",
        workspace=tmp_path / "workspace",
        packaged=True,
    )

    backend = create_default_backend(storage)

    assert isinstance(backend, RemoteCloudraBackend)
    assert backend.profile.server_url == "https://cloudra.example.test"
    assert not hasattr(backend, "service")


def test_android_credential_keys_are_origin_scoped_and_non_secret():
    from cloudra.infra.native_bridge import credential_key

    first = credential_key("server", "HTTPS://Cloudra.Example/api/")
    same = credential_key("server", "https://cloudra.example/api")
    other = credential_key("server", "https://other.example/api")
    device = credential_key(
        "device",
        "https://cloudra.example/api",
        "dev_123456789012",
    )

    assert first == same
    assert first != other
    assert first != device
    assert "cloudra.example" not in first


def test_android_secret_transport_envelope_hides_and_authenticates_value():
    from cloudra.infra.native_bridge import (
        CloudraNative,
        NativeBridgeError,
        _open_transport,
        _seal_transport,
    )

    key = b"k" * 32
    secret = b"devtok_plaintext_must_not_reach_flet_logs"
    envelope = _seal_transport(key, secret, aad=b"set:credential-a")

    assert secret.decode() not in json.dumps(envelope)
    assert (
        _open_transport(key, envelope, aad=b"set:credential-a")
        == secret
    )
    with pytest.raises(NativeBridgeError, match="校验失败"):
        _open_transport(key, envelope, aad=b"set:credential-b")
    damaged = dict(envelope)
    damaged["tag"] = damaged["tag"][:-2] + "AA"
    with pytest.raises(NativeBridgeError, match="校验失败"):
        _open_transport(key, damaged, aad=b"set:credential-a")

    pytest.importorskip("flet", reason="repr 用例依赖 Flet（gui 额外依赖）")
    bridge = CloudraNative()
    bridge._secure_session_id = "session_must_not_be_repr_visible"
    bridge._secure_session_key = bytearray(b"key_must_not_be_repr_visible")
    rendered = repr(bridge)
    assert "session_must_not_be_repr_visible" not in rendered
    assert "key_must_not_be_repr_visible" not in rendered


def test_android_build_stage_is_remote_only_and_sourceless_importable(
    tmp_path,
):
    from cloudra.infra.android_build import (
        ANDROID_EXTENSION_DIRS,
        ANDROID_RUNTIME_FILES,
        prepare_stage,
    )

    project_root = Path(__file__).resolve().parents[1]
    stage = prepare_stage(project_root, project_root / "build" / "test-android-stage")
    try:
        staged_files = {
            path.relative_to(stage).as_posix()
            for path in stage.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        extension_files = {
            (
                Path(extension_dir)
                / source.relative_to(project_root / extension_dir)
            ).as_posix()
            for extension_dir in ANDROID_EXTENSION_DIRS
            for source in (project_root / extension_dir).rglob("*")
            if source.is_file()
            and "__pycache__" not in source.parts
            and source.suffix not in {".pyc", ".pyo"}
        }
        assert staged_files == {
            *ANDROID_RUNTIME_FILES,
            *extension_files,
            "pyproject.toml",
        }
        assert "cloudra/agent.py" not in staged_files
        assert "cloudra/service.py" not in staged_files
        assert "cloudra/config.py" not in staged_files
        with (stage / "pyproject.toml").open("rb") as handle:
            android_project = tomllib.load(handle)
        assert android_project["project"]["dependencies"] == [
            "certifi>=2024",
            "cloudra-native==0.1.0",
            "httpx>=0.24",
        ]
        assert android_project["tool"]["flet"]["android"]["dependencies"] == [
            "flet==0.86.3"
        ]
        assert android_project["tool"]["flet"]["android"]["dev_packages"] == {
            "cloudra-native": "extensions/cloudra_native"
        }
        assert android_project["tool"]["flet"]["android"][
            "deep_linking"
        ] == {"scheme": "cloudra", "host": "runtime"}

        assert compileall.compile_dir(stage, quiet=1, legacy=True, force=True)
        for source_file in stage.rglob("*.py"):
            source_file.unlink()

        probe = """
import json
import os
import sys
os.environ["CLOUDRA_MOBILE_MODE"] = "true"
os.environ["FLET_APP_STORAGE_DATA"] = os.environ["CLOUDRA_TEST_STORAGE"]
from cloudra.services.backends import RemoteCloudraBackend, create_default_backend
from cloudra.infra.mobile_storage import configure_app_storage
import cloudra.ui.app
storage = configure_app_storage()
backend = create_default_backend(storage)
print(json.dumps({
    "remote": isinstance(backend, RemoteCloudraBackend),
    "agent_loaded": "cloudra.core.agent" in sys.modules,
    "service_loaded": "cloudra.services.service" in sys.modules,
    "config_loaded": "cloudra.infra.config" in sys.modules,
    "workspace_exists": storage.workspace.is_dir(),
}))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(stage)
        env["CLOUDRA_TEST_STORAGE"] = str(tmp_path / "storage")
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=stage,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(completed.stdout.splitlines()[-1])
        assert payload == {
            "remote": True,
            "agent_loaded": False,
            "service_loaded": False,
            "config_loaded": False,
            "workspace_exists": True,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def test_android_build_stage_preserves_only_generated_build_cache(tmp_path):
    from cloudra.infra.android_build import (
        ANDROID_EXTENSION_DIRS,
        ANDROID_RUNTIME_FILES,
        prepare_stage,
    )

    project_root = Path(__file__).resolve().parents[1]
    stage = project_root / "build" / "test-android-stage-cache"
    try:
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "build").mkdir()
        (stage / "build" / "cache.marker").write_text("keep", encoding="utf-8")
        (stage / "stale.py").write_text("remove", encoding="utf-8")
        (stage / "stale-dir").mkdir()
        (stage / "stale-dir" / "old.txt").write_text("remove", encoding="utf-8")

        prepare_stage(project_root, stage)

        assert (stage / "build" / "cache.marker").read_text(encoding="utf-8") == "keep"
        assert not (stage / "stale.py").exists()
        assert not (stage / "stale-dir").exists()
        assert all((stage / relative_name).is_file() for relative_name in ANDROID_RUNTIME_FILES)
        assert all((stage / relative_name).is_dir() for relative_name in ANDROID_EXTENSION_DIRS)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def test_built_apk_contains_current_pyc_only_remote_runtime():
    """Regression gate against shipping stale source or server modules."""
    root = Path(__file__).resolve().parents[1]
    apk = root / "build" / "apk" / "cloudra-android.apk"
    if not apk.is_file():
        pytest.skip("APK is not built in this checkout")
    with zipfile.ZipFile(apk) as outer:
        assert "assets/app.zip" in outer.namelist()
        with zipfile.ZipFile(io.BytesIO(outer.read("assets/app.zip"))) as app:
            names = set(app.namelist())
            assert "cloudra/ui/app.pyc" in names
            assert "cloudra/backends.pyc" in names
            assert "cloudra/device/runtime.pyc" in names
            assert not any(name.endswith(".py") for name in names)
            assert "cloudra/agent.pyc" not in names
            assert "cloudra/service.pyc" not in names
            assert "cloudra/config.pyc" not in names
            ui_bytecode = app.read("cloudra/ui/app.pyc")
            assert "移除此服务器".encode() in ui_bytecode
            assert "已移除服务器".encode() in ui_bytecode


def test_bundled_android_extension_has_phase7_native_boundaries():
    root = Path(__file__).resolve().parents[1]
    extension = root / "extensions" / "cloudra_native"
    kotlin_root = (
        extension
        / "src/flutter/cloudra_native/android/src/main/kotlin"
        / "io/github/yyywaa/cloudra_native"
    )
    plugin = (kotlin_root / "CloudraNativePlugin.kt").read_text(
        encoding="utf-8"
    )
    service = (kotlin_root / "CloudraForegroundService.kt").read_text(
        encoding="utf-8"
    )
    manifest = (
        extension
        / "src/flutter/cloudra_native/android/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    dart_service = (
        extension
        / "src/flutter/cloudra_native/lib/src/service.dart"
    ).read_text(encoding="utf-8")
    mobile_ui = (root / "cloudra/ui/app.py").read_text(encoding="utf-8")

    assert "AndroidKeyStore" in plugin
    assert "secure_transport_public_key" in plugin
    assert "secure_set_encrypted" in plugin
    assert 'arguments["value"]' not in plugin
    assert "secureStore.set(TREE_RECORD" in plugin
    assert ".putString(TREE_RECORD" not in plugin
    assert "cipher.updateAAD" in plugin
    assert '"cancel_notification"' in plugin
    assert "takePersistableUriPermission" in plugin
    assert "releasePersistableUriPermission" in plugin
    assert "persistedUriPermissions" in plugin
    assert "ACTION_OPEN_DOCUMENT" in plugin
    assert "ACTION_IMAGE_CAPTURE" in plugin
    assert "ACTION_SEND" in plugin
    assert "START_NOT_STICKY" in service
    assert 'android:foregroundServiceType="remoteMessaging"' in manifest
    assert 'android:allowBackup="false"' in manifest
    assert 'android:usesCleartextTraffic="true"' in manifest
    assert "FOREGROUND_SERVICE_REMOTE_MESSAGING" in manifest
    assert "io.github.yyywaa.cloudra/native" in dart_service
    assert "value=profile.token" not in mobile_ui
    assert "remove_registered_server" in mobile_ui
    assert "await backend.revoke_device" in mobile_ui
    assert 'credential_key("server", selected.server_url)' in mobile_ui


def test_mobile_ui_import_does_not_load_agent_or_local_service(tmp_path):
    probe = """
import json
import sys
import cloudra.ui.app
print(json.dumps({
    "agent_loaded": "cloudra.core.agent" in sys.modules,
    "service_loaded": "cloudra.services.service" in sys.modules,
}))
"""
    env = os.environ.copy()
    env["CLOUDRA_MOBILE_MODE"] = "true"
    env["CLOUDRA_DATA_DIR"] = str(tmp_path / "data")
    env["CLOUDRA_CONFIG_FILE"] = str(tmp_path / "config.yaml")
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload == {"agent_loaded": False, "service_loaded": False}


@pytest.mark.asyncio
async def test_dispatcher_cannot_execute_mobile_hidden_tool(tmp_path, monkeypatch):
    """Hiding a schema is insufficient: the dispatcher must reject it too."""

    from cloudra.core.agent import Follower
    from cloudra.core.react import reAct
    from cloudra.infra.config import get_config

    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    db_path = str(tmp_path / "mobile.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr("cloudra.core.react.get_tools_lst", lambda: [_entry(_ForbiddenBash)])
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)

    agent = Follower(
        id="a-mobile",
        name="mobile",
        prompt="test",
        query="test",
        conversation_id="mobile-dispatch",
    )
    react = reAct(agent)

    async def ignore_telemetry(*_args, **_kwargs):
        return None

    # This test owns the runtime/permission boundary, not SQLite telemetry.
    # Keeping telemetry live made a hidden-tool assertion depend on an unrelated
    # aiosqlite worker thread and could hang constrained Android/CI harnesses.
    monkeypatch.setattr(react, "_record_event", ignore_telemetry)
    stopped = await react.act_result(
        [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "bashtools", "arguments": "{}"},
            }
        ]
    )

    assert stopped is False
    context = await agent.get_context()
    tool_messages = [block for block in context if block.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "找不到工具: bashtools" in tool_messages[0]["content"]
    assert "must not run" not in json.dumps(tool_messages, ensure_ascii=False)


def test_pyc_only_package_loads_explicit_registries(tmp_path):
    """An APK-like sourceless package must expose the same built-in manifests."""

    project_root = Path(__file__).resolve().parents[1]
    package_root = tmp_path / "apk-site"
    packaged_cloudra = package_root / "cloudra"
    shutil.copytree(
        project_root / "cloudra",
        packaged_cloudra,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    assert compileall.compile_dir(packaged_cloudra, quiet=1, legacy=True, force=True)
    for source_file in packaged_cloudra.rglob("*.py"):
        source_file.unlink()
    assert not any(packaged_cloudra.rglob("*.py"))

    probe = """
import json
import cloudra.subagents as subagents
import cloudra.tools as tools
from cloudra.subagents.registry import SUBAGENT_REGISTRY
from cloudra.tools.registry import TOOL_REGISTRY

tool_entries = tools.get_tools_lst()
payload = {
    "origins": [tools.__file__, subagents.__file__],
    "tool_names": sorted(entry.tool_name for entry in tool_entries),
    "loaded_tool_targets": sorted(
        [entry.cls.__module__, entry.cls.__name__] for entry in tool_entries
    ),
    "tool_errors": tools.get_tool_load_errors(),
    "tool_manifest": sorted([item.module, item.class_name] for item in TOOL_REGISTRY),
    "subagent_ids": sorted(subagents.get_subagent_classes()),
    "subagent_manifest_ids": sorted(item.agent_id for item in SUBAGENT_REGISTRY),
}
print(json.dumps(payload, ensure_ascii=False))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(package_root), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env["CLOUDRA_DATA_DIR"] = str(tmp_path / "apk-data")
    env["CLOUDRA_CONFIG_FILE"] = str(tmp_path / "apk-config.yaml")
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=package_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout.splitlines()[-1])

    assert all(origin.endswith(".pyc") for origin in payload["origins"])
    assert "bashtools" in payload["tool_names"]
    assert "edit_file" in payload["tool_names"]
    assert payload["subagent_ids"] == [f"a-{index}" for index in range(1, 9)]
    assert payload["subagent_ids"] == payload["subagent_manifest_ids"]

    loaded_targets = {tuple(target) for target in payload["loaded_tool_targets"]}
    failed_modules = set(payload["tool_errors"])
    manifest_targets = {tuple(target) for target in payload["tool_manifest"]}
    assert {
        target for target in manifest_targets if target[0] not in failed_modules
    } == loaded_targets
    assert {target[0] for target in manifest_targets} == {
        target[0] for target in loaded_targets
    } | failed_modules


@pytest.mark.asyncio
async def test_waiting_subagent_runs_in_current_process(tmp_path, monkeypatch):
    """The Android launcher directly awaits run_executor; it never calls subprocess."""

    from cloudra.infra.config import get_config
    from cloudra.tools.Managetool.subagent_launcher import (
        SubAgentLauncher,
        SubAgentLauncher_input_schema,
    )

    monkeypatch.setenv("CLOUDRA_MOBILE_MODE", "true")
    cfg = get_config()
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    cfg._ensure_dirs()
    ConversationDB("mobile-parent").init()

    calls: list[tuple[int, str, str]] = []

    async def fake_run_executor(task_id: int, database_path: str, session_id: str):
        calls.append((task_id, database_path, session_id))
        db = ConversationDB.from_path(database_path)
        session_store.create_session_record(
            db,
            session_id=session_id,
            agent_id="a-1",
            agent_type="explorer",
            parent_session_id=None,
            query="inspect the mobile workspace",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await session_store.afinalize_session(
            db, session_id, "completed", result="mobile child result"
        )
        await session_store.afinalize_task(db, task_id, session_id, "done")

    monkeypatch.setattr("cloudra.runtime.executor.run_executor", fake_run_executor)

    tool = SubAgentLauncher()
    tool.subagent = SimpleNamespace(
        conversation_id="mobile-parent",
        working_directory=str(tmp_path),
    )
    result = await tool.tool_call(
        SubAgentLauncher_input_schema(
            agent_id="a-1",
            query="inspect the mobile workspace",
            is_wait=True,
        ),
        session=None,
    )

    assert len(calls) == 1
    assert calls[0][2] == result.session_id
    assert result.result == "mobile child result"
