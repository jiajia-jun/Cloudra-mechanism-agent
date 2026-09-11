from datetime import datetime, timedelta, timezone

import pytest

from cloudra.infra.config import _reset_for_tests, get_config
from cloudra.persistence.artifacts import (
    ArtifactDownloadDenied,
    ArtifactService,
)
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store


@pytest.fixture
def artifact_environment(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    _reset_for_tests()
    config = get_config()
    config.data_dir = data_dir
    conversation_id = "conv_artifact"
    session_id = "a-0_run_artifact"
    db = ConversationDB(conversation_id).init()
    session_store.create_session_record(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="生成文件",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "data_dir": data_dir,
        "workspace": workspace,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "db": db,
    }


def test_artifact_is_immutable_and_token_is_hashed(artifact_environment):
    env = artifact_environment
    source = env["workspace"] / "result.txt"
    source.write_text("snapshot", encoding="utf-8")
    service = ArtifactService(env["data_dir"])
    artifact = service.register_file(
        conversation_id=env["conversation_id"],
        session_id=env["session_id"],
        source=source,
        allowed_root=env["workspace"],
    )
    source.write_text("changed later", encoding="utf-8")

    token, expires_at = service.issue_download_token(
        env["conversation_id"],
        artifact.artifact_id,
        ttl_seconds=60,
    )
    resolved_artifact, path = service.resolve_download(
        env["conversation_id"],
        artifact.artifact_id,
        token,
    )

    assert path.read_text(encoding="utf-8") == "snapshot"
    assert resolved_artifact.sha256 == artifact.sha256
    assert "storage_path" not in artifact.to_dict()
    assert datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
    with env["db"].connect() as con:
        stored_token = con.execute(
            "SELECT token_hash FROM artifact_download_tokens"
        ).fetchone()[0]
        event_type = con.execute(
            """SELECT event_type FROM session_events
            WHERE event_type='artifact_created'"""
        ).fetchone()[0]
    assert token not in stored_token
    assert len(stored_token) == 64
    assert event_type == "artifact_created"


def test_artifact_rejects_workspace_escape_and_expired_or_mismatched_token(
    artifact_environment,
):
    env = artifact_environment
    service = ArtifactService(env["data_dir"])
    outside = env["workspace"].parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(ArtifactDownloadDenied, match="边界"):
        service.register_file(
            conversation_id=env["conversation_id"],
            session_id=env["session_id"],
            source=outside,
            allowed_root=env["workspace"],
        )

    first_path = env["workspace"] / "first.txt"
    second_path = env["workspace"] / "second.txt"
    first_path.write_text("first", encoding="utf-8")
    second_path.write_text("second", encoding="utf-8")
    first = service.register_file(
        conversation_id=env["conversation_id"],
        session_id=env["session_id"],
        source=first_path,
        allowed_root=env["workspace"],
    )
    second = service.register_file(
        conversation_id=env["conversation_id"],
        session_id=env["session_id"],
        source=second_path,
        allowed_root=env["workspace"],
    )
    token, _ = service.issue_download_token(
        env["conversation_id"],
        first.artifact_id,
    )

    with pytest.raises(ArtifactDownloadDenied):
        service.resolve_download(
            env["conversation_id"],
            second.artifact_id,
            token,
        )

    expired = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    with env["db"].connect() as con:
        con.execute(
            "UPDATE artifact_download_tokens SET expires_at=?",
            (expired,),
        )
        con.commit()
    with pytest.raises(ArtifactDownloadDenied, match="过期"):
        service.resolve_download(
            env["conversation_id"],
            first.artifact_id,
            token,
        )


def test_artifact_rejects_source_and_storage_symlinks(
    artifact_environment,
):
    env = artifact_environment
    service = ArtifactService(env["data_dir"])
    source = env["workspace"] / "source.txt"
    source.write_text("safe", encoding="utf-8")
    source_link = env["workspace"] / "source-link.txt"
    try:
        source_link.symlink_to(source)
    except OSError:
        pytest.skip("当前平台不允许创建符号链接")

    with pytest.raises(ArtifactDownloadDenied, match="符号链接"):
        service.register_file(
            conversation_id=env["conversation_id"],
            session_id=env["session_id"],
            source=source_link,
            allowed_root=env["workspace"],
        )

    artifact = service.register_file(
        conversation_id=env["conversation_id"],
        session_id=env["session_id"],
        source=source,
        allowed_root=env["workspace"],
    )
    token, _ = service.issue_download_token(
        env["conversation_id"],
        artifact.artifact_id,
    )
    stored = service.root / artifact.storage_path
    replacement = stored.with_name("replacement.txt")
    replacement.write_text("replacement", encoding="utf-8")
    stored.unlink()
    stored.symlink_to(replacement)

    with pytest.raises(ArtifactDownloadDenied, match="符号链接"):
        service.resolve_download(
            env["conversation_id"],
            artifact.artifact_id,
            token,
        )



def test_register_file_heals_empty_shell_db(artifact_environment):
    """裸 connect() 留下的空库文件（无任何表）不能再炸出
    'no such table: session'——register_file 先补 schema，ensure_session_record
    再补 legacy session 行（v2 agent 没有 reAct 时代的 session 记录）。"""
    env = artifact_environment
    conversation_id = "conv_shell"
    session_id = "as_shell"
    db = ConversationDB(conversation_id)
    # 模拟肇事路径：裸 connect 创建空库文件后退出，一张表都没有。
    with db.connect():
        pass

    session_store.ensure_session_record(db, session_id, "coordinator")

    source = env["workspace"] / "edit.txt"
    source.write_text("edited", encoding="utf-8")
    artifact = ArtifactService(env["data_dir"]).register_file(
        conversation_id=conversation_id,
        session_id=session_id,
        source=source,
        allowed_root=env["workspace"],
    )
    assert artifact.artifact_id
    assert (ArtifactService(env["data_dir"]).root / artifact.storage_path).is_file()


def test_register_file_migrates_schema_before_session_check(artifact_environment):
    """空壳库先被 migrate_if_needed 补齐表，再按业务规则拒绝缺失的
    session 行（ArtifactDownloadDenied），而不是 sqlite OperationalError。"""
    env = artifact_environment
    conversation_id = "conv_shell2"
    db = ConversationDB(conversation_id)
    with db.connect():
        pass

    source = env["workspace"] / "edit2.txt"
    source.write_text("edited", encoding="utf-8")
    with pytest.raises(ArtifactDownloadDenied, match="Session"):
        ArtifactService(env["data_dir"]).register_file(
            conversation_id=conversation_id,
            session_id="as_missing",
            source=source,
            allowed_root=env["workspace"],
        )


def test_download_missing_artifact_returns_404(artifact_environment):
    """下载不存在 artifact 必须是 404，不是未捕获的 ArtifactNotFound 500。"""
    from fastapi.testclient import TestClient

    from cloudra.services.api_v2 import create_v2_app

    client = TestClient(create_v2_app())
    resp = client.get(
        "/api/v2/artifacts/art_missing/download",
        params={"project_id": artifact_environment["conversation_id"]},
    )
    assert resp.status_code == 404
