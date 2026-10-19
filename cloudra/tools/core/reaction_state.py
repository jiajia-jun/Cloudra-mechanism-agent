"""反应拥有的结构与映射；文件和原子表均为导入、导出的边界视图。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

from cloudra.tools.core.molecule import (
    Molecule,
    copy_conformer,
    renumber_atoms,
    serialize_molecule,
    to_xyz,
    with_positions,
)


class ReactionStructures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reactant: Molecule | None = None
    product: Molecule | None = None
    product_to_reactant: tuple[StrictInt, ...] | None = None
    candidate: Molecule | None = None

    @model_validator(mode="after")
    def complete_correspondence(self):
        if self.product_to_reactant is None:
            return self
        if self.reactant is None or self.product is None:
            raise ValueError("完整原子对应需要两端结构")
        mapping = self.product_to_reactant
        if len(mapping) != self.product.GetNumAtoms() or sorted(mapping) != list(range(self.reactant.GetNumAtoms())):
            raise ValueError("原子对应必须覆盖两端每个原子一次")
        for index, target in enumerate(mapping):
            left, right = self.reactant.GetAtomWithIdx(target), self.product.GetAtomWithIdx(index)
            if (left.GetAtomicNum(), left.GetIsotope()) != (right.GetAtomicNum(), right.GetIsotope()):
                raise ValueError("原子对应改变了元素或同位素身份")
        return self


def path_endpoints(state: ReactionStructures) -> tuple[Molecule, Molecule]:
    # 映射只在绑定时校验；所有路径算法共用相同的同序副本。
    state.complete_correspondence()
    if state.reactant is None or state.product is None or state.product_to_reactant is None:
        raise ValueError("两端结构及其全原子对应尚未确认")
    order = [state.product_to_reactant.index(i) for i in range(state.reactant.GetNumAtoms())]
    return copy_conformer(state.reactant), renumber_atoms(state.product, order)


def mapped_reaction_center(state: ReactionStructures) -> list[tuple[int, int]]:
    """从已绑定的全原子对应推导成断键；复用映射算法，不另存一份反应中心。"""
    if state.product_to_reactant is None:
        return []
    from cloudra.tools.Chemtool.reaction_mapping import _edit_facts

    state.complete_correspondence()
    facts = _edit_facts(state.reactant, state.product, list(state.product_to_reactant))
    return sorted({tuple(index - 1 for index in pair)
                   for pair in facts['formed_bonds'] + facts['broken_bonds']})


def heavy_binding(mol) -> list[int]:
    if mol is None:
        return []
    pairs = sorted((atom.GetIntProp("cloudra_smiles_heavy_index"), atom.GetIdx() + 1)
                   for atom in mol.GetAtoms() if atom.HasProp("cloudra_smiles_heavy_index"))
    return [index for _, index in pairs]


def set_heavy_binding(mol, indices: list[int]):
    out = copy_conformer(mol)
    for atom in out.GetAtoms():
        if atom.HasProp("cloudra_smiles_heavy_index"):
            atom.ClearProp("cloudra_smiles_heavy_index")
    for position, index in enumerate(indices):
        out.GetAtomWithIdx(index - 1).SetIntProp("cloudra_smiles_heavy_index", position)
    return out


def source_snapshot(mol) -> dict:
    return json.loads(mol.GetProp("cloudra_import_source")) if mol is not None and mol.HasProp("cloudra_import_source") else {}


def import_file_structure(record, role, source):
    """捕获一次来源；此后执行只读分子对象，不回读可变源文件。"""
    from cloudra.tools.Chemtool.reaction_mapping import _read_structure
    from cloudra.tools.core.ts_process import _workspace_input_path, _write_immutable_input

    paths = {"xyz": _workspace_input_path(record, source.xyz_path)}
    if source.mol_path:
        paths["mol"] = _workspace_input_path(record, source.mol_path)
    data = {name: path.read_bytes() for name, path in paths.items()}
    directory = Path(record.run_dir) / "build" / f"input_{record.declaration_revision:04d}" / role
    directory.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for name, content in data.items():
        target = directory / ("source_" + hashlib.sha256(content).hexdigest()[:16] + "." + name)
        _write_immutable_input(str(target), content.decode("utf-8"))
        snapshots[name] = str(target)
    reaction = record.input.reaction
    from rdkit import Chem

    from cloudra.tools.core.electronic_state import electronic_state_details
    from cloudra.tools.core.species_identity import chemical_smiles

    declared = Chem.MolFromSmiles(chemical_smiles(getattr(reaction, role + '_smiles')))
    declared_state = electronic_state_details(declared, charge=reaction.charge, multiplicity=reaction.multiplicity, electronic_character=reaction.electronic_character)
    mol = _read_structure(None, data.get("mol", data["xyz"]).decode("utf-8"),
        "mol" if "mol" in data else "xyz", reaction.charge, role,
        multiplicity=reaction.multiplicity, electronic_character=reaction.electronic_character,
        require_declared_identity=declared_state['requires_spin_aware_geometry'])
    if "mol" in data:
        from cloudra.tools.core.molecule import read_molecule
        geometry = read_molecule(input_text=data["xyz"].decode("utf-8"), input_format="xyz", charge=reaction.charge)
        if [a.GetSymbol() for a in mol.GetAtoms()] != [a.GetSymbol() for a in geometry.GetAtoms()]:
            raise ValueError(f"{role}: MOL and XYZ atom orders differ")
        mol = with_positions(mol, geometry.GetConformer().GetPositions())
    # 构建器的明确原子身份随 Mol 保存，换序证明不再回读行尾标记。
    rows = data['xyz'].decode('utf-8').splitlines()[2:2 + mol.GetNumAtoms()]
    labels = [[token for token in row.split()[4:] if token.startswith('in:')] for row in rows]
    if any(labels):
        if len(labels) != mol.GetNumAtoms() or any(len(values) != 1 for values in labels) or len({values[0] for values in labels}) != len(labels):
            raise ValueError(f'{role}: source atom identity annotations must be complete and unique')
        for atom, values in zip(mol.GetAtoms(), labels, strict=True):
            parent, mark, ordinal = values[0][3:].partition('#H')
            if not parent.isdigit() or (mark and (not ordinal.isdigit() or int(ordinal) < 1)):
                raise ValueError(f'{role}: invalid source atom identity annotation {values[0]}')
            atom.SetProp('cloudra_atom_id', values[0])
    mol.SetProp("cloudra_import_source", json.dumps(dict(
        paths={name: str(path) for name, path in paths.items()},
        hashes={name: hashlib.sha256(content).hexdigest() for name, content in data.items()},
        snapshots=snapshots, input_revision=record.declaration_revision)))
    return mol


def export_structure(record, role) -> tuple[str, str]:
    """导出由内容决定的执行文件；从不把文件指针当作当前状态。"""
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _write_immutable_input
    mol = getattr(record.structures, role)
    if mol is None:
        raise ValueError(f"{role} structure is missing")
    digest = hashlib.sha256(serialize_molecule(mol).encode()).hexdigest()[:20]
    directory = Path(record.run_dir) / "structures"
    directory.mkdir(parents=True, exist_ok=True)
    xyz, graph = directory / f"{role}_{digest}.xyz", directory / f"{role}_{digest}.mol"
    _write_immutable_input(str(xyz), to_xyz(mol))
    _write_immutable_input(str(graph), Chem.MolToMolBlock(mol))
    return str(xyz), str(graph)


def structure_tables(record) -> dict[str, dict]:
    """只读的人类视图；展示表不参与后续执行。"""
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import concrete_structure_digest
    from cloudra.tools.core.electronic_state import electronic_state_details
    reaction = record.input.reaction
    tables = {}
    for role in ("reactant", "product"):
        mol = getattr(record.structures, role)
        if mol is None:
            continue
        smiles = getattr(reaction, role + "_smiles")
        source = getattr(record.input.conformers, role)
        from cloudra.tools.core.species_identity import chemical_smiles

        declared = Chem.MolFromSmiles(chemical_smiles(smiles))
        snapshot = source_snapshot(mol)
        tables[role] = dict(role=role, source_kind=source.kind if source else snapshot.get('kind'),
            input_revision=snapshot.get("input_revision", record.declaration_revision),
            structure_digest=concrete_structure_digest(role, smiles, reaction.charge, reaction.multiplicity,
                mol, electronic_character=reaction.electronic_character),
            atom_count=mol.GetNumAtoms(), components=len(Chem.GetMolFrags(mol)), index_base=1,
            atoms=[dict(number=atom.GetIdx() + 1, symbol=atom.GetSymbol(), isotope=atom.GetIsotope(),
                atom_id=atom.GetProp("cloudra_atom_id") if atom.HasProp("cloudra_atom_id") else None)
                for atom in mol.GetAtoms()],
            smiles_heavy_atoms=[dict(position=i + 1, symbol=a.GetSymbol(), isotope=a.GetIsotope(), atom_map_label=a.GetAtomMapNum())
                for i, a in enumerate(a for a in declared.GetAtoms() if a.GetAtomicNum() != 1)] if declared else [],
            heavy_atom_indices=heavy_binding(mol), binding_status="complete" if record.structures.product_to_reactant is not None else "unverified",
            source=snapshot, electronic_state=electronic_state_details(mol, charge=reaction.charge,
                multiplicity=reaction.multiplicity, electronic_character=reaction.electronic_character))
    return tables
