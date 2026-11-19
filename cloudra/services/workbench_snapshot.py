"""Freeze the geometry and user-picked periodic images accompanying a chat message."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, PositiveInt, StrictInt, model_validator

from cloudra.tools.core.molecule import Molecule, serialize_molecule, to_xyz


class AtomImage(BaseModel):
    index: PositiveInt
    image: tuple[StrictInt, StrictInt, StrictInt] = (0, 0, 0)


class Marker(BaseModel):
    label: str = Field(min_length=1)
    kind: Literal['atoms', 'site']
    atoms: list[AtomImage] = Field(min_length=1)


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    title: str
    molecule: Molecule | None = None
    extxyz: str | None = None
    source_path: str | None = None
    source_frame: StrictInt | None = Field(default=None, ge=0)
    view: Literal['source', 'draft']
    camera: list[FiniteFloat] = Field(min_length=8, max_length=8)
    markers: list[Marker]
    warnings: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    frozen_coordinates: list[dict] = Field(default_factory=list)
    scan_coordinates: list[dict] = Field(default_factory=list)

    @model_validator(mode='after')
    def one_geometry(self):
        if (self.molecule is None) == (self.extxyz is None):
            raise ValueError('快照需要一份分子或周期几何。')
        if len({mark.label for mark in self.markers}) != len(self.markers):
            raise ValueError('标记名称必须唯一。')
        return self


def freeze_snapshot(workspace, request: SnapshotRequest) -> dict:
    """Return a fresh project-local record without saving a product or notifying an agent."""
    directory = workspace.cache_root / 'messages' / uuid4().hex
    metadata = request.model_dump(mode='json', exclude={'markers', 'extxyz', 'molecule'})
    files: dict[Path, str] = {}
    if request.extxyz is not None:
        from io import StringIO

        from ase.io import iread

        from cloudra.tools.core.workbench_geometry import validate_workbench_cell

        frames = iter(iread(StringIO(request.extxyz), format='extxyz'))
        frame = next(frames, None)
        if frame is None or next(frames, None) is not None:
            raise ValueError('周期快照必须恰好包含一帧。')
        validate_workbench_cell(frame)
        positions, symbols = frame.positions, frame.get_chemical_symbols()
        cell, pbc = frame.cell.tolist(), frame.pbc.tolist()
        metadata.update(cell_angstrom=cell, pbc=pbc)
        structure = directory / 'structure.extxyz'
        files[structure] = request.extxyz
    else:
        from rdkit import Chem

        mol = request.molecule
        if not mol.GetNumConformers() or not mol.GetNumAtoms():
            raise ValueError('结构没有原子坐标。')
        positions = mol.GetConformer().GetPositions()
        symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
        cell, pbc = [[0, 0, 0]] * 3, [False] * 3
        structure = directory / 'structure.json'
        files[structure] = json.dumps({**metadata, 'molecule': serialize_molecule(mol)}, ensure_ascii=False)
        files[directory / 'structure.xyz'] = to_xyz(mol)
        files[directory / 'structure.mol'] = Chem.MolToMolBlock(mol, kekulize=False, forceV3000=True)
    markers = []
    for mark in request.markers:
        atoms = []
        for pick in mark.atoms:
            if pick.index > len(symbols) or any(v and not periodic for v, periodic in zip(pick.image, pbc)):
                raise ValueError(f'标记 {mark.label} 引用了不存在的原子或周期镜像。')
            point = [float(x + sum(v * row[axis] for v, row in zip(pick.image, cell)))
                     for axis, x in enumerate(positions[pick.index - 1])]
            atoms.append({**pick.model_dump(), 'element': symbols[pick.index - 1], 'xyz_angstrom': point})
        marker = {'label': mark.label, 'kind': mark.kind, 'atoms': atoms}
        if mark.kind == 'site':
            marker['xyz_angstrom'] = [sum(atom['xyz_angstrom'][axis] for atom in atoms) / len(atoms)
                                      for axis in range(3)]
        markers.append(marker)
    path = directory / 'annotations.json'
    metadata.update(structure_path=str(structure), structure_files=[str(p) for p in files], markers=markers)
    files[path] = json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False)
    for target, content in files.items():
        workspace._write(target, content)
    return {'structure_path': str(structure), 'annotations_path': str(path), 'markers': markers}
