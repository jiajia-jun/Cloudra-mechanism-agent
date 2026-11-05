"""Protected molecular workbench operations over the shared chemistry services."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from cloudra.persistence.artifacts import ArtifactDownloadDenied, ArtifactNotFound
from cloudra.persistence.fragment_library import FragmentLibrary
from cloudra.runtime_v2.hub_bridge import post_user_post
from cloudra.services.workbench import WorkbenchService
from cloudra.tools.core.geometry_inputs import FrozenCoordinateInput, ScanCoordinateInput
from cloudra.tools.core.molecule import Molecule
from cloudra.tools.core.workbench_geometry import EditRequest, edit_geometry
from cloudra.tools.core.workbench_results import document_csv, document_frame

from ..context import ApiContext


class OpenRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str | None = None
    artifact_id: str | None = None
    input_text: str | None = None
    input_format: str = 'xyz'
    smiles: str | None = None
    frame_index: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def one_source(self):
        if sum(bool(value and value.strip()) for value in (self.path, self.artifact_id, self.input_text, self.smiles)) != 1:
            raise ValueError('请选择一个文件，或提供结构文本／SMILES')
        return self


class FrozenSetting(FrozenCoordinateInput):
    value: float


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    title: str = 'Edited structure'
    molecule: Molecule
    source_path: str | None = None
    source_frame: StrictInt | None = Field(default=None, ge=0)
    settings: dict[str, Any] = Field(default_factory=dict)
    frozen_coordinates: list[FrozenSetting] = Field(default_factory=list)
    scan_coordinates: list[ScanCoordinateInput] = Field(default_factory=list)
    generate_input: bool = False


class FragmentUseRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    smiles: str
    name: str = ''


async def _work(function, *args):
    try:
        return await asyncio.to_thread(function, *args)
    except (ArtifactNotFound, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except ArtifactDownloadDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, IndexError, KeyError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter(prefix='/api/v2/projects/{project_id}/workbench', dependencies=ctx.protected)

    def service(project_id: str) -> WorkbenchService:
        return WorkbenchService(ctx.core.require_project(project_id))

    @router.post('/open')
    async def open_source(project_id: str, body: OpenRequest) -> dict:
        workspace = await _work(service, project_id)
        return await _work(workspace.open, body)

    @router.post('/preview')
    async def preview(project_id: str, body: OpenRequest) -> dict:
        workspace = await _work(service, project_id)
        return await _work(workspace.preview, body)

    @router.get('/documents/{document_id}/frames/{index}')
    async def frame(project_id: str, document_id: str, index: int) -> dict:
        workspace = await _work(service, project_id)
        return await _work(document_frame, workspace.cache_root, document_id, index)

    @router.get('/documents/{document_id}/csv')
    async def csv(project_id: str, document_id: str) -> Response:
        workspace = await _work(service, project_id)
        content = await _work(document_csv, workspace.cache_root, document_id)
        return Response(content, media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="calculation.csv"'})

    @router.post('/edit')
    async def edit(project_id: str, body: EditRequest) -> dict:
        ctx.core.require_project(project_id)
        return await _work(edit_geometry, body)

    @router.get('/fragments')
    async def fragments(project_id: str) -> dict:
        ctx.core.require_project(project_id)
        return {'fragments': await _work(lambda: FragmentLibrary().list_fragments(project_id))}

    @router.post('/fragments')
    async def use_fragment(project_id: str, body: FragmentUseRequest) -> dict:
        ctx.core.require_project(project_id)
        return await _work(lambda: FragmentLibrary().use_fragment(project_id, body.smiles, body.name))

    @router.post('/fragments/preview')
    async def preview_fragment(project_id: str, body: FragmentUseRequest) -> dict:
        ctx.core.require_project(project_id)

        def render():
            from rdkit import Chem

            from cloudra.tools.core.workbench_geometry import create_geometry

            graph = Chem.MolFromSmiles(body.smiles)
            if graph is None:
                raise ValueError('Invalid fragment SMILES')
            if any(atom.GetAtomicNum() == 0 for atom in graph.GetAtoms()):
                return FragmentLibrary().preview_fragment(body.smiles)
            return create_geometry(body.smiles, 'smiles')

        return await _work(render)

    @router.delete('/fragments/{fragment_id}')
    async def delete_fragment(project_id: str, fragment_id: str) -> dict:
        ctx.core.require_project(project_id)
        await _work(lambda: FragmentLibrary().delete_fragment(fragment_id))
        return {'deleted': True}

    @router.post('/save')
    async def save(project_id: str, body: SaveRequest) -> dict:
        workspace = await _work(service, project_id)
        saved = await _work(workspace.save, body)
        coordinators = [agent for agent in ctx.core.agents.values()
                        if agent.project_id == project_id and agent.role_id == 'coordinator' and agent.parent_session_id is None]
        target = coordinators[-1].id if coordinators else ''
        receipt = await post_user_post(
            ctx.core, project_id, topic='结构编辑', content=saved.pop('notification_content'),
            kind='finding', to_agent=target,
        )
        saved['notification'] = {'event_id': receipt['post']['id'],
                                 'notified_count': receipt.get('notified_count', 0),
                                 'failed_session_ids': receipt.get('failed_session_ids', [])}
        return saved

    @router.get('/products')
    async def products(project_id: str) -> dict:
        workspace = await _work(service, project_id)
        return await _work(workspace.products)

    return router
