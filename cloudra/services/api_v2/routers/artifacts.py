"""Artifact listing, project image uploads, and artifact downloads."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..context import ApiContext

_UPLOAD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


async def _artifacts_service():
    from cloudra.infra.config import get_config
    from cloudra.persistence.artifacts import ArtifactService

    def build():
        return ArtifactService(Path(get_config().data_dir))

    return await asyncio.to_thread(build)


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/projects/{project_id}/artifacts", dependencies=ctx.protected)
    async def list_artifacts(
        project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        ctx.core.require_project(project_id)
        service = await _artifacts_service()
        artifacts = await asyncio.to_thread(service.list, project_id, session_id=session_id)
        return [artifact.to_dict() for artifact in artifacts]

    @router.post("/api/v2/projects/{project_id}/uploads", dependencies=ctx.protected, status_code=status.HTTP_201_CREATED)
    async def upload_project_image(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        """User image upload: stored under the project workspace and registered as an artifact.

        The returned ``path`` is what ``agent.message`` accepts in ``images``;
        ``artifact_id`` lets the frontend render the bubble from storage.
        """
        from cloudra.persistence.fs_utils import atomic_write_bytes
        from cloudra.runtime_v2.invocation import register_workspace_image_artifact

        project = ctx.core.require_project(project_id)
        filename = Path(file.filename or "").name
        ext = Path(filename).suffix.lower()
        if ext not in _UPLOAD_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported image type {ext or '(none)'}; allowed: png, jpg, jpeg, webp",
            )
        data = await file.read()
        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty upload")
        if len(data) > _UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="upload exceeds the 20MB limit",
            )
        # 存量 workspace_dir=None 的项目与文件工具同一兜底：per-project 默认
        # 工作区（GH #24），artifact 边界检查也因此与工具写入同一根。
        from cloudra.persistence.paths import project_workspace_dir

        root = Path(project.workspace_dir) if project.workspace_dir else project_workspace_dir(project_id)
        upload_dir = root / ".cloudra" / "uploads"
        path = upload_dir / f"{uuid.uuid4().hex[:12]}-{filename}"

        def write() -> None:
            upload_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(str(path), data)

        await asyncio.to_thread(write)
        artifact_id = await asyncio.to_thread(
            lambda: register_workspace_image_artifact(
                project_id=project_id,
                session_id="uploads",
                agent_id=None,
                workspace_root=str(root),
                image_path=str(path),
            )
        )
        return {"path": str(path), "artifact_id": artifact_id}

    @router.get("/api/v2/artifacts/{artifact_id}/download", dependencies=ctx.protected)
    async def download_artifact(artifact_id: str, project_id: str) -> StreamingResponse:
        from fastapi.responses import FileResponse

        from cloudra.persistence.artifacts import ArtifactDownloadDenied, ArtifactNotFound

        artifacts = await _artifacts_service()
        try:
            token, _ = await asyncio.to_thread(
                artifacts.issue_download_token, project_id, artifact_id
            )
            artifact, source = await asyncio.to_thread(
                artifacts.resolve_download, project_id, artifact_id, token
            )
        except ArtifactNotFound:
            raise HTTPException(status_code=404, detail="artifact not found") from None
        except ArtifactDownloadDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        return FileResponse(source, filename=artifact.name)

    return router
