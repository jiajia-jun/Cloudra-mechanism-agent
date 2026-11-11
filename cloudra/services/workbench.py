"""Project files and recorded chemical references for the molecular workbench.

All methods here are synchronous IO/chemistry and must be called in a worker.
Source lineage never establishes a species identity or scientific acceptance.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cloudra.persistence.artifacts import ArtifactService, _sha256_file
from cloudra.persistence.database import ComputeDB, ConversationDB
from cloudra.persistence.paths import project_workspace_dir
from cloudra.persistence.workspace import WorkspaceService
from cloudra.services import session_store
from cloudra.tools.core.molecule import serialize_molecule, to_xyz


class WorkbenchService:
    def __init__(self, project):
        self.project = project
        self.root = (Path(project.workspace_dir) if project.workspace_dir else project_workspace_dir(project.id)).expanduser().resolve()
        self.cache_root = self.root / '.cloudra' / 'workbench'

    def source_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        path = (path if path.is_absolute() else self.root / path).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError('文件必须位于当前项目工作目录中')
        if not path.is_file():
            raise FileNotFoundError(f'文件不存在：{path}')
        return path

    def _write(self, path: Path, text: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        workspace = WorkspaceService(self.root)
        change = workspace.prepare_write(str(path.relative_to(self.root)), text, 'missing')
        workspace.apply(change)

    def open(self, request) -> dict[str, Any]:
        from cloudra.tools.core.workbench_geometry import create_geometry
        from cloudra.tools.core.workbench_results import open_document

        if request.path:
            source = self.source_path(request.path)
        elif request.artifact_id:
            service = ArtifactService()
            token, _ = service.issue_download_token(self.project.id, request.artifact_id)
            artifact, original = service.resolve_download(self.project.id, request.artifact_id, token)
            source = self.cache_root / 'imports' / request.artifact_id / artifact.name
            source.parent.mkdir(parents=True, exist_ok=True)
            if not source.is_file():
                shutil.copyfile(original, source)
        elif request.smiles:
            geometry = create_geometry(request.smiles, 'smiles')
            source = self.cache_root / 'imports' / f'{uuid4().hex}.json'
            self._write(source, json.dumps({'title': request.smiles, 'molecule': geometry['molecule'], 'settings': {}}, ensure_ascii=False))
        else:
            fmt = request.input_format or 'xyz'
            suffix = {'gaussian-in': 'gjf', 'gaussian': 'gjf', 'orca': 'inp', 'smiles': 'smi'}.get(fmt, fmt)
            if suffix not in {'xyz', 'mol', 'sdf', 'gjf', 'com', 'inp', 'smi', 'pdb', 'cif', 'json', 'log', 'out'}:
                raise ValueError(f'不支持的导入格式：{fmt}')
            if fmt == 'smiles':
                geometry = create_geometry(request.input_text, fmt)
                source = self.cache_root / 'imports' / f'{uuid4().hex}.json'
                self._write(source, json.dumps({'title': request.input_text, 'molecule': geometry['molecule'], 'settings': {}}, ensure_ascii=False))
            else:
                source = self.cache_root / 'imports' / f'{uuid4().hex}.{suffix}'
                self._write(source, request.input_text)
        result = open_document(source, self.cache_root, request.frame_index)
        if request.artifact_id:
            result['source_artifact_id'] = request.artifact_id
        return result

    def preview(self, request) -> dict[str, Any]:
        document = self.open(request)
        geometry = document['geometry']
        if geometry is None:
            raise ValueError('该计算点没有可用的原生几何')
        return {'title': document['title'], 'task_type': document['task_type'],
                'engine': document['settings'].get('engine'), 'frame_count': len(document['frames']),
                'mode_count': len(document['modes']),
                'selected_frame_facts': document['frames'][document['selected_frame']],
                **{key: geometry[key] for key in ('xyz', 'atoms', 'bonds', 'graph_status', 'manual_bonds')}}

    def save(self, request) -> dict[str, Any]:
        from rdkit import Chem

        from cloudra.tools.core.workbench_geometry import geometry_view

        if request.source_path:
            self.source_path(request.source_path)
        mol = request.molecule
        atom_count = mol.GetNumAtoms()
        if atom_count == 0:
            raise ValueError('结构必须包含至少一个原子才能保存')
        for coordinate in [*request.frozen_coordinates, *request.scan_coordinates]:
            if any(not 1 <= atom <= atom_count for atom in coordinate.atoms):
                raise ValueError(f'坐标引用的原子已不存在：{coordinate.atoms}')
        identifier = uuid4().hex
        directory = self.root / '.cloudra' / 'structures' / identifier
        state_path = directory / 'structure.json'
        files = {'state': str(state_path), 'xyz': str(directory / 'structure.xyz'), 'mol': str(directory / 'structure.mol')}
        frozen = [item.model_dump(mode='json') for item in request.frozen_coordinates]
        scans = [item.model_dump(mode='json') for item in request.scan_coordinates]
        input_text = None
        if request.generate_input:
            from cloudra.tools.core.workbench_input import render_workbench_input

            engine = request.settings.get('engine')
            extension = 'gjf' if engine == 'gaussian' else 'inp'
            files['input'] = str(directory / f'calculation.{extension}')
            input_text = render_workbench_input(mol, request.settings, frozen, scans, files['input'])
        geometry = geometry_view(mol)
        state = {
            'title': request.title.strip() or 'Edited structure',
            'molecule': serialize_molecule(mol),
            'source_path': request.source_path,
            'source_frame': request.source_frame,
            'settings': request.settings,
            'frozen_coordinates': frozen,
            'scan_coordinates': scans,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'created_by': 'user',
        }
        payloads = {
            'xyz': to_xyz(mol, state['title']),
            'mol': Chem.MolToMolBlock(mol, kekulize=False, forceV3000=True),
        }
        if input_text is not None:
            payloads['input'] = input_text
        # The JSON manifest is written last: listing never sees a partial save.
        for kind, content in payloads.items():
            self._write(Path(files[kind]), content)
        self._write(state_path, json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False))
        session_id = 'workbench-user'
        session_store.ensure_session_record(ConversationDB(self.project.id), session_id, None)
        artifacts = ArtifactService()
        artifact_ids = {}
        for kind, path in files.items():
            artifact = artifacts.register_file(
                conversation_id=self.project.id, session_id=session_id,
                source=Path(path), allowed_root=self.root,
            )
            artifact_ids[kind] = artifact.artifact_id
        source = request.source_path or '新建结构'
        frame = f'，第 {request.source_frame + 1} 帧' if request.source_frame is not None else ''
        message = (
            f'用户在分子工作台保存了结构“{state["title"]}”。\n'
            f'来源：{source}{frame}\n'
            f'完整结构与设置：{state_path}\n'
            f'文件：{json.dumps(files, ensure_ascii=False)}\n'
            f'冻结坐标：{json.dumps(frozen, ensure_ascii=False)}\n'
            f'扫描坐标：{json.dumps(scans, ensure_ascii=False)}\n'
            '这是人工编辑的候选结构；尚未建立新的化学归属或计算验证结论。'
        )
        return {'path': str(state_path), 'files': files, 'artifact_ids': artifact_ids, 'geometry': geometry,
                'message': '已保存完整结构、连接关系与计算设置。', 'notification_content': message}

    def _graph_context(self) -> tuple[dict[tuple[str, str], list[dict]], list[dict]]:
        from cloudra.dag.evidence_ingest import FileEvidenceSnapshot
        from cloudra.dag.models import GraphRef
        from cloudra.dag.store import DagStore, GraphBundleNotFound

        db = ConversationDB(self.project.id)
        if not Path(db.path).is_file():
            return {}, []
        db.ensure_schema()
        store = DagStore(db)
        try:
            snapshot = store.load_snapshot()
        except GraphBundleNotFound:
            return {}, []
        result: dict[tuple[str, str], list[dict]] = {}
        objects = []
        for kind, elements in [('node', snapshot.delivery.nodes), ('edge', snapshot.delivery.edges)]:
            for element in elements:
                row = element.model_dump(mode='json')
                element_id = row.get('node_id') or row.get('edge_id')
                label = row.get('label') or row.get('name') or element_id
                objects.append({'kind': kind, 'id': element_id, 'label': label})
                refs = [(ref, None) for ref in row.get('refs', [])]
                refs.extend((stage['ref'], stage.get('kind')) for stage in row.get('stages', []) if stage.get('ref'))
                for ref, stage in refs:
                    entry = {'kind': kind, 'id': element_id, 'label': label,
                             'stage': stage, **ref}
                    result.setdefault((ref['ref_type'], ref['ref_id']), []).append(entry)
                    if ref['ref_type'] == 'file':
                        # "file" points to a canonical evidence record, never
                        # a pathname. Resolve its actual immutable snapshot.
                        payload = store.resolve_evidence(GraphRef.model_validate(ref))
                        if not isinstance(payload, dict) or not {'snapshot_path', 'original_path', 'sha256'} <= payload.keys():
                            continue
                        evidence = FileEvidenceSnapshot.model_validate(payload)
                        for value in (evidence.snapshot_path, evidence.original_path):
                            file = Path(value).resolve()
                            if file.is_relative_to(self.root) and file.is_file() and _sha256_file(file) == evidence.sha256:
                                result.setdefault(('file_path', str(file)), []).append(entry)
        return result, objects

    def products(self) -> dict[str, list[dict]]:
        from cloudra.infra.compute_utils import resolve_log_path
        from cloudra.services.compute_store import _db_ready, list_compute_jobs

        references, objects = self._graph_context()
        artifacts = ArtifactService().list(self.project.id)
        artifact_sources: dict[str, list] = {}
        for artifact in artifacts:
            artifact_sources.setdefault(artifact.source_path, []).append(artifact)
        fingerprints = {}

        def matching_artifacts(file: Path):
            key = str(file)
            candidates = artifact_sources.get(key, [])
            if not candidates or not file.is_file():
                return []
            if key not in fingerprints:
                fingerprints[key] = _sha256_file(file)
            return [artifact for artifact in candidates if artifact.sha256 == fingerprints[key]]

        def artifact_ref(artifact):
            return {'ref_type': 'artifact', 'ref_id': artifact.artifact_id, 'content_hash': artifact.sha256}
        products = []
        saved_files: set[str] = set()
        for path in sorted((self.root / '.cloudra' / 'structures').glob('*/structure.json'), reverse=True):
            state = json.loads(path.read_text(encoding='utf-8'))
            saved_files.update(str(file) for file in path.parent.iterdir() if matching_artifacts(file))
            # Keep the exact member-file reference on its association. A record
            # groups files; this does not turn every member into that species.
            associations = []
            for member in path.parent.iterdir():
                if not member.is_file():
                    continue
                associations.extend(references.get(('file_path', str(member)), []))
                for artifact in matching_artifacts(member):
                    associations.extend(references.get(('artifact', artifact.artifact_id), []))
            state_artifacts = matching_artifacts(path)
            products.append({
                'id': str(path), 'kind': 'structure', 'title': state.get('title', path.parent.name),
                'path': str(path), 'source_path': state.get('source_path'), 'source_frame': state.get('source_frame'),
                'created_at': state.get('created_at', ''), 'state': 'draft', 'can_open': True,
                'preview_xyz': (path.parent / 'structure.xyz').read_text(encoding='utf-8') if (path.parent / 'structure.xyz').is_file() else '',
                'associations': associations,
                'association_ref': artifact_ref(state_artifacts[-1]) if state_artifacts else None,
                'files': [{'path': str(file), 'role': file.suffix.lstrip('.')} for file in path.parent.iterdir() if file.is_file()],
            })
        db = ComputeDB()
        jobs = list_compute_jobs(db, conversation_id=self.project.id, order='recent', limit=100) if _db_ready(db) else []
        for job in jobs:
            input_path = Path(job.get('path') or '')
            input_path = (input_path if input_path.is_absolute() else self.root / input_path).resolve()
            job_type = job.get('jobtype') or job.get('job_type') or 'calculation'
            log_path = Path(resolve_log_path(str(input_path), job_type, job.get('id')))
            local_files = [file for file in (input_path, log_path) if file.is_relative_to(self.root) and file.is_file()]
            chosen = log_path if log_path in local_files else input_path
            associations = [*references.get(('compute_job', str(job['id'])), []),
                            *references.get(('file_path', str(chosen)), [])]
            products.append({
                'id': f'job:{job["id"]}', 'kind': 'calculation', 'title': input_path.stem,
                'job_id': job['id'], 'job_type': job_type, 'state': job.get('state'),
                'created_at': job.get('created_at') or '', 'path': str(chosen),
                'can_open': chosen in local_files, 'associations': associations,
                'association_ref': {'ref_type': 'compute_job', 'ref_id': str(job['id'])},
                'files': [{'path': str(file), 'role': 'input' if file == input_path else 'output'} for file in local_files],
            })
        molecular_suffixes = {'.xyz', '.mol', '.sdf', '.pdb', '.cif', '.gjf', '.com', '.inp', '.log', '.out'}
        for artifact in artifacts:
            if artifact.source_path in saved_files and artifact in matching_artifacts(Path(artifact.source_path)):
                continue
            associations = [*references.get(('artifact', artifact.artifact_id), []),
                            *(references.get(('file_path', artifact.source_path), [])
                              if artifact in matching_artifacts(Path(artifact.source_path)) else [])]
            products.append({
                'id': artifact.artifact_id, 'kind': 'artifact', 'title': artifact.name,
                'artifact_id': artifact.artifact_id, 'path': artifact.source_path,
                'created_at': artifact.created_at, 'state': '',
                'can_open': Path(artifact.name).suffix.lower() in molecular_suffixes,
                'associations': associations, 'files': [],
                'association_ref': artifact_ref(artifact),
                'mime_type': artifact.mime_type, 'size': artifact.size,
            })
        # Explicit file references are useful even without artifact registration.
        known_paths = {item['path'] for item in products}
        for (ref_type, ref_id), associations in references.items():
            if ref_type != 'file_path' or ref_id in known_paths:
                continue
            file = Path(ref_id)
            if file.is_relative_to(self.root) and file.is_file():
                products.append({'id': ref_id, 'kind': 'artifact', 'title': file.name, 'path': ref_id,
                                 'created_at': '', 'state': '', 'can_open': file.suffix.lower() in molecular_suffixes,
                                 'associations': associations, 'files': [],
                                 'association_ref': {key: associations[0][key] for key in ('ref_type', 'ref_id', 'content_hash') if key in associations[0]}})
        products.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)
        return {'products': products, 'objects': objects}
