"""One shared fragment history, serialized by the existing POSIX file lock."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cloudra.infra.flocks import locked
from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.persistence.paths import data_dir


class FragmentLibrary:
    def __init__(self, root: Path | None = None):
        self.root = data_dir(root) / 'fragment_library'
        self.path = self.root / 'fragments.json'

    def _read(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    @staticmethod
    def _view(entry: dict, project_id: str) -> dict:
        return {key: value for key, value in entry.items() if key != 'project_uses'} | {
            'project_use_count': entry['project_uses'].get(project_id, 0),
        }

    def list_fragments(self, project_id: str) -> list[dict]:
        entries = [self._view(entry, project_id) for entry in self._read().values()]
        return sorted(entries, key=lambda entry: (not bool(entry['project_use_count']),
                                                   -entry['use_count'], entry['smiles']))

    def use_fragment(self, project_id: str, smiles: str, name: str = '') -> dict:
        from cloudra.tools.core.workbench_geometry import connection_smiles

        smiles = connection_smiles(smiles)
        identity = hashlib.sha256(smiles.encode()).hexdigest()[:24]
        self.root.mkdir(parents=True, exist_ok=True)
        with locked(str(self.root / 'fragments.lock')):
            entries = self._read()
            if identity not in entries:
                entries[identity] = self._build_entry(identity, smiles)
            entry = entries[identity]
            if name:
                entry['name'] = name
            entry['use_count'] += 1
            entry['project_uses'][project_id] = entry['project_uses'].get(project_id, 0) + 1
            atomic_write_json(str(self.path), entries)
            return self._view(entry, project_id)

    def preview_fragment(self, smiles: str) -> dict:
        """Use the capped-fragment builder/cache without recording a use."""
        from cloudra.tools.core.workbench_geometry import connection_smiles

        smiles = connection_smiles(smiles)
        identity = hashlib.sha256(smiles.encode()).hexdigest()[:24]
        entry = self._read().get(identity)
        return (entry if entry is not None else self._build_entry(identity, smiles))['geometry']

    @staticmethod
    def _build_entry(identity: str, smiles: str) -> dict:
        from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates
        from cloudra.tools.core.molecule import with_positions
        from cloudra.tools.core.workbench_geometry import geometry_view

        mol, attachment, _, order, direction = InternalCoordinates._embed_substituent_3d(smiles)
        positions = mol.GetConformer().GetPositions()
        mol = with_positions(mol, positions - positions[attachment])
        return {'id': identity, 'smiles': smiles, 'name': '', 'use_count': 0, 'project_uses': {},
                'attachment_atom': attachment + 1, 'bond_order': order,
                'connection_vector': direction.tolist(), 'geometry': geometry_view(mol)}

    def delete_fragment(self, fragment_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with locked(str(self.root / 'fragments.lock')):
            entries = self._read()
            if entries.pop(fragment_id, None) is None:
                raise KeyError(fragment_id)
            atomic_write_json(str(self.path), entries)
