"""Immutable artifact snapshots and short-lived download grants."""

from __future__ import annotations

import hashlib
import mimetypes
import secrets
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB, retry_on_locked
from cloudra.services import session_store


class ArtifactNotFound(ValueError):
    pass


class ArtifactDownloadDenied(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    conversation_id: str
    session_id: str
    name: str
    mime_type: str
    size: int
    sha256: str
    storage_path: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "name": self.name,
            "mime_type": self.mime_type,
            "size": self.size,
            "sha256": self.sha256,
            "created_at": self.created_at,
        }


class ArtifactService:
    def __init__(self, data_dir: Path | None = None):
        configured = data_dir or Path(get_config().data_dir)
        self.root = Path(configured).expanduser().resolve() / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _from_row(conversation_id: str, row) -> Artifact:
        return Artifact(
            artifact_id=row[0],
            conversation_id=conversation_id,
            session_id=row[1],
            name=row[2],
            mime_type=row[3],
            size=int(row[4]),
            sha256=row[5],
            storage_path=row[6],
            created_at=row[7],
        )

    def register_file(
        self,
        *,
        conversation_id: str,
        session_id: str,
        source: Path,
        allowed_root: Path,
        name: str | None = None,
    ) -> Artifact:
        """Snapshot one regular file after enforcing its workspace boundary."""

        root = Path(allowed_root).expanduser().resolve(strict=True)
        source_path = Path(source)
        if source_path.is_symlink():
            raise ArtifactDownloadDenied("不允许把符号链接登记为 artifact")
        resolved = source_path.expanduser().resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ArtifactDownloadDenied("Artifact 来源越过工作区边界") from exc
        if not resolved.is_file():
            raise ArtifactDownloadDenied("Artifact 来源不是普通文件")

        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            raise ArtifactDownloadDenied("Artifact 对应的 Conversation 不存在")
        # 文件存在 ≠ 表存在：裸 connect() 会创建空库文件。版本检查是只读的，
        # 版本落后/空库时一次性补齐 schema。
        db.migrate_if_needed()
        with db.connect() as con:
            session_exists = con.execute(
                "SELECT 1 FROM session WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if session_exists is None:
            raise ArtifactDownloadDenied("Artifact 对应的 Session 不存在")

        filename = Path(name or resolved.name).name
        if not filename or filename in {".", ".."} or "\x00" in filename:
            raise ArtifactDownloadDenied("Artifact 文件名无效")
        artifact_id = f"art_{uuid.uuid4().hex}"
        destination_dir = self.root / artifact_id
        destination_dir.mkdir(parents=True)
        destination = destination_dir / filename
        shutil.copyfile(resolved, destination)
        size = destination.stat().st_size
        sha256 = _sha256_file(destination)
        mime_type = (
            mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        created_at = _iso(_utc_now())
        storage_path = destination.relative_to(self.root).as_posix()

        def write() -> None:
            with db.connect() as con:
                con.execute(
                    """INSERT INTO artifacts
                    (artifact_id, session_id, name, mime_type, size, sha256,
                     storage_path, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        artifact_id,
                        session_id,
                        filename,
                        mime_type,
                        size,
                        sha256,
                        storage_path,
                        created_at,
                    ),
                )
                con.commit()

        retry_on_locked(write)
        artifact = Artifact(
            artifact_id=artifact_id,
            conversation_id=conversation_id,
            session_id=session_id,
            name=filename,
            mime_type=mime_type,
            size=size,
            sha256=sha256,
            storage_path=storage_path,
            created_at=created_at,
        )
        session_store.insert_session_event(
            db,
            session_id,
            "artifact_created",
            artifact.to_dict(),
        )
        return artifact

    def get(self, conversation_id: str, artifact_id: str) -> Artifact | None:
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return None

        def read():
            with db.connect() as con:
                return con.execute(
                    """SELECT artifact_id, session_id, name, mime_type, size,
                    sha256, storage_path, created_at FROM artifacts
                    WHERE artifact_id=?""",
                    (artifact_id,),
                ).fetchone()

        row = retry_on_locked(read)
        return self._from_row(conversation_id, row) if row else None

    def list(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[Artifact]:
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            return []
        db.migrate_if_needed()

        def read():
            with db.connect() as con:
                if session_id is None:
                    return con.execute(
                        """SELECT artifact_id, session_id, name, mime_type,
                        size, sha256, storage_path, created_at FROM artifacts
                        ORDER BY created_at DESC"""
                    ).fetchall()
                return con.execute(
                    """SELECT artifact_id, session_id, name, mime_type,
                    size, sha256, storage_path, created_at FROM artifacts
                    WHERE session_id=? ORDER BY created_at DESC""",
                    (session_id,),
                ).fetchall()

        return [
            self._from_row(conversation_id, row)
            for row in retry_on_locked(read)
        ]

    def issue_download_token(
        self,
        conversation_id: str,
        artifact_id: str,
        *,
        ttl_seconds: int = 300,
    ) -> tuple[str, str]:
        artifact = self.get(conversation_id, artifact_id)
        if artifact is None:
            raise ArtifactNotFound("Artifact 不存在")
        ttl_seconds = min(max(int(ttl_seconds), 30), 900)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        created_at = _utc_now()
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        db = ConversationDB(conversation_id)

        def write() -> None:
            with db.connect() as con:
                con.execute(
                    "DELETE FROM artifact_download_tokens WHERE expires_at<=?",
                    (_iso(created_at),),
                )
                con.execute(
                    """INSERT INTO artifact_download_tokens
                    (token_hash, artifact_id, expires_at, created_at)
                    VALUES (?, ?, ?, ?)""",
                    (
                        token_hash,
                        artifact_id,
                        _iso(expires_at),
                        _iso(created_at),
                    ),
                )
                con.commit()

        retry_on_locked(write)
        return token, _iso(expires_at)

    def resolve_download(
        self,
        conversation_id: str,
        artifact_id: str,
        token: str,
    ) -> tuple[Artifact, Path]:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        db = ConversationDB(conversation_id)
        if not Path(db.path).is_file():
            raise ArtifactDownloadDenied("下载令牌无效或已过期")
        now = _iso(_utc_now())

        def read():
            with db.connect() as con:
                return con.execute(
                    """SELECT artifact_id FROM artifact_download_tokens
                    WHERE token_hash=? AND artifact_id=? AND expires_at>?""",
                    (token_hash, artifact_id, now),
                ).fetchone()

        if retry_on_locked(read) is None:
            raise ArtifactDownloadDenied("下载令牌无效或已过期")
        artifact = self.get(conversation_id, artifact_id)
        if artifact is None:
            raise ArtifactDownloadDenied("Artifact 不存在")
        storage_path = Path(artifact.storage_path)
        if storage_path.is_absolute() or ".." in storage_path.parts:
            raise ArtifactDownloadDenied("Artifact 存储路径越界")
        candidate = self.root / storage_path
        current = self.root
        for part in storage_path.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactDownloadDenied("Artifact 存储路径包含符号链接")
        destination = candidate.resolve(strict=True)
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactDownloadDenied("Artifact 存储路径越界") from exc
        if not destination.is_file():
            raise ArtifactDownloadDenied("Artifact 文件不可用")
        return artifact, destination
