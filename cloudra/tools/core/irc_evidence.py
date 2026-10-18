"""IRC 证据几何材料组装（benchmark 自洽性与 DAG live 交付门禁共用唯一实现）。

「日志路径 → 几何材料」的探针逻辑唯一来源：

- ``probe_log``：日志的虚频数与末帧几何（TS 几何与端点验证极小值几何的
  取法；无频率块时虚频数为 None，绝不冒充 0）；
- ``irc_endpoint_geometries``：IRC 双侧端点几何，ts_guess strict 同口径——
  Gaussian 取主日志逐点帧 rx<0 / rx>0 两侧最外侧的带坐标帧，ORCA 取终点
  文件/F-B 轨迹边文件；未收敛方向取轨迹末帧作部分端点，收敛与否不做闸门；
- ``verify_short_irc_direction``：核验同一 TS 的双向 IRC 外帧确实经
  收敛优化到两侧正确的零虚频极小值。几何区间只作诊断提示，不否决真实优化链。

缺材料 fail-loud：``verify_short_irc_direction`` 返回 ``(passed, details)``，
``passed=False`` 时 details 结构化写明缺哪份材料，绝不静默降级。details
一律英文（给模型/agent 的文本）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from cloudra.tools.core import gaussian_frames, orca_frames, qm_engine
from cloudra.tools.core.irc_path import parse_xyz, prove_irc_endpoint_direction, same_geometry


def irc_start_geometry(path):
    """Native IRC starting saddle, never a predictor or a terminal path frame."""
    engine = qm_engine.detect_qm_engine(str(path))
    try:
        if engine == 'gaussian':
            frames, _ = gaussian_frames.extract_irc(str(path))
            return next((parse_xyz(frame.xyz) for frame in frames
                         if frame.reaction_coordinate == 0.0 and frame.xyz.strip()),
                        parse_xyz(gaussian_frames.irc_start_xyz(Path(path).read_text(errors='replace'))))
        if engine == 'orca':
            text = Path(path).read_text(errors='replace')
            orca_frames.extract_irc_from_text(text)
            start = text.find('Intrinsic Reaction Coordinate Calculation')
            if start < 0:
                return None
            index = text.rfind('CARTESIAN COORDINATES (ANGSTROEM)', 0, start)
            xyz = orca_frames._xyz_block_at(text, index) if index >= 0 else orca_frames.input_xyz_from_text(text[:start])
            return parse_xyz(xyz)
    except (ValueError, OSError):
        return None
    return None


def frames_for(path):
    """Return (frames, irc_meta). 两种解析各自隔离：opt+freq 日志没有 IRC 段
    是正常情况，不能让 extract_irc 的异常把已解析的 frames 一并丢弃。

    IRC meta 已归一化为 dict：gaussian_frames.extract_irc 返回
    (frames, meta) 二元组，orca_frames.extract_irc 直接返回 meta dict。
    """
    engine = qm_engine.detect_qm_engine(str(path))
    mod = orca_frames if engine == "orca" else gaussian_frames
    try:
        frames = mod.extract_frames(str(path))
    except Exception:
        frames = []
    try:
        raw_irc = mod.extract_irc(str(path))
    except Exception:
        raw_irc = None
    if isinstance(raw_irc, tuple):
        irc_meta = raw_irc[1] if len(raw_irc) == 2 else None
    else:
        irc_meta = raw_irc
    return frames, irc_meta


def _last_freqs(frames) -> list[float]:
    for fr in reversed(frames):
        if fr.frequencies_cm:
            return list(fr.frequencies_cm)
    return []


def freqs_for(path, frames) -> list[float]:
    """末帧频率；cclib 对 ORCA 6.1 日志裸抛 IndexError（帧为空）时回退
    文本权威 VIBRATIONAL FREQUENCIES 块（统一入口在 orca_frames）。"""
    freqs = _last_freqs(frames)
    if freqs:
        return freqs
    engine = qm_engine.detect_qm_engine(str(path))
    if engine == "orca":
        return orca_frames.frequencies_with_text_fallback(str(path))
    if engine == 'gaussian':
        text = Path(path).read_text(errors='replace').rsplit('Harmonic frequencies', 1)[-1]
        return [float(value) for line in text.splitlines() if 'Frequencies --' in line
                for value in line.partition('Frequencies --')[2].split()]
    return []


def imag_freqs(freqs: list[float]) -> list[float]:
    return [f for f in freqs if f < 0]


def last_geometry(path, frames) -> Optional[tuple]:
    """末帧几何 (symbols, positions)；无坐标帧返回 None。

    cclib 对 ORCA 6.1 日志整体崩溃时帧为空——走文本权威
    CARTESIAN COORDINATES 块回退（同频率的文本回退纪律）。
    """
    geometry = None
    for fr in reversed(frames):
        if getattr(fr, "xyz", "").strip():
            geometry = parse_xyz(fr.xyz)
            break
    if geometry is None and qm_engine.detect_qm_engine(str(path)) == "orca":
        geometry = parse_xyz(orca_frames.final_xyz_with_text_fallback(str(path)))
    if geometry is None and qm_engine.detect_qm_engine(str(path)) == 'gaussian':
        text = Path(path).read_text(errors='replace')
        blocks = gaussian_frames.std_orientation_frames(text)
        rows = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(text)
        if rows:
            geometry = parse_xyz(gaussian_frames._coords_to_xyz([row[0] for row in rows], [row[1:] for row in rows]))
    return geometry


def irc_frames_for(path):
    """IRC 逐点帧。Gaussian 主日志内含逐点坐标；ORCA 的逐点坐标在边文件里，
    主日志没有（端点几何走 orca_irc_endpoint_geometries 的边文件通道）。"""
    try:
        raw = gaussian_frames.extract_irc(str(path))
    except Exception:
        return []
    if isinstance(raw, tuple) and raw:
        return list(raw[0]) if raw[0] else []
    return []


def gaussian_irc_endpoints_from_frames(frames) -> Optional[tuple]:
    """ts_guess strict 同口径的 Gaussian IRC 端点：rx<0 / rx>0 两侧各自最外侧
    的带坐标帧（不要求收敛到极小值）。两侧都有可用几何才返回。"""
    valid = [fr for fr in frames if getattr(fr, "xyz", "").strip()]
    neg = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate < 0
    ]
    pos = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate > 0
    ]
    if not neg or not pos:
        return None
    end_a = min(neg, key=lambda fr: fr.reaction_coordinate)
    end_b = max(pos, key=lambda fr: fr.reaction_coordinate)
    geo_a = parse_xyz(end_a.xyz)
    geo_b = parse_xyz(end_b.xyz)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b


def orca_irc_endpoint_geometries(path) -> Optional[tuple]:
    """ts_guess strict 同口径的 ORCA IRC 端点：几何来自终点文件/F-B 轨迹边
    文件（未收敛方向取轨迹末帧，同样是合法的部分端点）；IRC 收敛与否不做闸门，
    方向依据两侧外帧的真实优化链。两侧都有可用几何才返回。

    前提是文件本身确实是 IRC 计算日志：输入文件（.inp）旁边恰好有同名
    轨迹边文件时，没有 IRC 段就没有任何"端点"可言。"""
    try:
        orca_frames.extract_irc(str(path))
    except Exception:
        return None  # 无 IRC 段（输入文件、非 IRC 作业）→ 不是 IRC 证据
    try:
        endpoints = orca_frames.extract_irc_endpoints(str(path))
    except Exception:
        return None
    xyz_a = orca_frames.read_endpoint_geometry(endpoints.get("forward", {}))
    xyz_b = orca_frames.read_endpoint_geometry(endpoints.get("backward", {}))
    if xyz_a is None or xyz_b is None:
        return None
    geo_a = parse_xyz(xyz_a)
    geo_b = parse_xyz(xyz_b)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b


def normal_log(path) -> bool:
    """Native normally terminated QM evidence with matching frequency geometry."""
    path = Path(path)
    if not path.is_file():
        return False
    engine = qm_engine.detect_qm_engine(str(path))
    parser = {'orca': orca_frames, 'gaussian': gaussian_frames}.get(engine)
    text = path.read_text(errors='replace')
    if parser is None or not parser.normal_termination(text):
        return False
    if engine == 'orca' and 'ORCA finished by error termination' in text:
        return False
    return frequency_geometry_matches(path)


def frequency_geometry_matches(path) -> bool:
    """The last spectrum must belong to the final geometry in the native log."""
    engine = qm_engine.detect_qm_engine(str(path))
    text = Path(path).read_text(errors='replace')
    frequency_marker = 'VIBRATIONAL FREQUENCIES' if engine == 'orca' else 'Frequencies --'
    frequency_index = text.rfind(frequency_marker)
    if frequency_index < 0:
        return True  # No frequency claim; probe_log still returns n_imag=None.

    def geometry(region):
        if engine == 'orca':
            return parse_xyz(orca_frames.final_xyz_from_text(region))
        blocks = gaussian_frames.std_orientation_frames(region)
        coords = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(region)
        return parse_xyz(gaussian_frames._coords_to_xyz(
            [row[0] for row in coords], [row[1:] for row in coords])) if coords else None

    return same_geometry(geometry(text), geometry(text[:frequency_index]))


def probe_log(path) -> tuple[Optional[int], Optional[tuple]]:
    """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。

    只解析 gaussian/orca 原生日志；文件大小不改变科学资格。"""
    p = Path(path)
    if not normal_log(p):
        return None, None
    frames, _irc_meta = frames_for(p)
    freqs = freqs_for(p, frames)
    n_imag = len(imag_freqs(freqs)) if freqs else None
    return n_imag, last_geometry(p, frames)


def irc_endpoint_geometries(path) -> Optional[tuple]:
    """双侧 IRC 端点几何 ((symbols, positions) × 2)，ts_guess strict 口径。

    引擎非 gaussian/orca 或任一侧几何不可得时返回 None。"""
    p = Path(path)
    engine = qm_engine.detect_qm_engine(str(p))
    if engine == "gaussian":
        return gaussian_irc_endpoints_from_frames(irc_frames_for(p))
    if engine == "orca":
        return orca_irc_endpoint_geometries(p)
    return None


def _ordered_graph_matches(geometry, mol_block: str, charge: int) -> bool:
    """Associate an independent minimum by its full graph, including H parents."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromMolBlock(mol_block, removeHs=False)
    if expected is None or any(atom.GetIsotope() for atom in expected.GetAtoms()):
        return False  # XYZ/log element rows cannot prove isotope lineage.
    actual = Chem.MolFromXYZBlock(xyz_block(*geometry))
    if actual is None or actual.GetNumAtoms() != expected.GetNumAtoms():
        return False
    try:
        rdDetermineBonds.DetermineBonds(actual, charge=charge)
    except ValueError:
        return False
    if actual.GetNumBonds() != expected.GetNumBonds():
        return False
    property_name = '_cloudra_evidence_atom_order'
    for molecule in (expected, actual):
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
            atom.SetIntProp(property_name, atom.GetIdx())
    parameters = Chem.SubstructMatchParameters()
    parameters.useChirality = True
    parameters.atomProperties = [property_name]
    return actual.HasSubstructMatch(expected, parameters)


def bound_atom_orders(ts, source, target, binding):
    """Return TS→mobile permutations only for the bound complete endpoint graphs."""
    if not binding:
        return None
    from rdkit import Chem

    mapping = binding.get('atom_map', [])
    count = len(ts[0])
    if (len(mapping) != count or any(type(index) is not int for index in mapping)
            or sorted(mapping) != list(range(1, count + 1))):
        return None
    reactant = Chem.MolFromMolBlock(binding['reactant_mol'], removeHs=False)
    if reactant is None or [atom.GetSymbol() for atom in reactant.GetAtoms()] != list(ts[0]):
        return None
    charge = binding['charge']
    if (not _ordered_graph_matches(source, binding['reactant_mol'], charge)
            or not _ordered_graph_matches(target, binding['product_mol'], charge)):
        return None
    identity = list(range(count))
    inverse = [mapping.index(index + 1) for index in range(count)]
    return [identity, identity, identity, inverse]


def iter_direction_verdicts(
    irc_ends: tuple,
    ts_geometries: Sequence[tuple],
    from_geometries: Sequence[tuple],
    to_geometries: Sequence[tuple],
    *,
    charge: int = 0, atom_binding=None,
):
    """按确定性顺序（TS → from → to）对全部材料组合逐一做方向区间证明，
    逐个产出 verdict（生成器，调用方 any()/遍历即短回路）。

    原子序无关：每组几何经 align_atom_order 重排进 TS 坐标序（距离指纹 +
    Hungarian，元素多重集不符的组合判 undecidable）——agent 用不同原子序
    重优化的端点极小值不再被误拒。"""
    (syms_a, pos_a), (syms_b, pos_b) = irc_ends
    for ts_syms, ts_pos in ts_geometries:
        for from_geo in from_geometries:
            for to_geo in to_geometries:
                yield prove_irc_endpoint_direction(
                    ts_syms, ts_pos,
                    (syms_a, pos_a), (syms_b, pos_b),
                    from_geo, to_geo, [], charge,
                    atom_orders=bound_atom_orders((ts_syms, ts_pos), from_geo, to_geo, atom_binding),
                )


def _geometry_matches_species(geometry, smiles: str, *, charge: int) -> bool:
    """Match the full bond graph and stereochemistry of a real geometry."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromSmiles(smiles)
    actual = Chem.MolFromXYZBlock(xyz_block(*geometry))
    if expected is None or actual is None or any(atom.GetIsotope() for atom in expected.GetAtoms()):
        return False
    if Chem.AddHs(expected).GetNumAtoms() != actual.GetNumAtoms():
        return False
    try:
        rdDetermineBonds.DetermineBonds(actual, charge=charge)
    except ValueError:
        return False
    for molecule in (expected, actual):
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(Chem.RemoveHs(actual)) == Chem.MolToSmiles(Chem.RemoveHs(expected))


def verify_separated_product_direction(
    irc_ends, ts_geometry, source_geometries, product_smiles, component_geometries,
    *, charge: int = 0, atom_binding=None,
) -> dict:
    """Prove the separated product channel without inventing a complex minimum.

    Callers supply only frequency-verified component and source minima. Product
    identity comes from an actual IRC outer geometry; the opposite direction
    retains the existing source-minimum interval predicate.
    """
    from rdkit import Chem

    from cloudra.tools.core.irc_path import align_atom_order, evaluate_endpoint_between
    from cloudra.tools.core.species_identity import chemical_smiles, species_smiles

    failure = dict(is_decidable=False, is_match=False, details=[])
    products = product_smiles.split('.') if isinstance(product_smiles, str) else species_smiles(product_smiles)
    if len(products) < 2:
        return {**failure, 'details': ['The declaration is one species, not separated products.']}
    declared = [Chem.MolFromSmiles(smiles) for smiles in products]
    if any(molecule is None for molecule in declared):
        return {**failure, 'details': ['A declared product SMILES is invalid.']}
    for smiles, molecule in zip(products, declared, strict=True):
        component_charge = sum(atom.GetFormalCharge() for atom in molecule.GetAtoms())
        if not any(_geometry_matches_species(geometry, smiles, charge=component_charge)
                   for geometry in component_geometries):
            return {**failure, 'details': [f'No frequency-verified independent minimum matches product {smiles}.']}

    symbols, positions = ts_geometry
    all_products = chemical_smiles(products)
    details = []
    for name, target, source in (('direct', irc_ends[1], irc_ends[0]),
                                 ('swapped', irc_ends[0], irc_ends[1])):
        if any(sorted(geometry[0]) != sorted(symbols) for geometry in (target, source)):
            details.append('IRC endpoint atom counts or elements differ from the TS.')
            continue
        if not _geometry_matches_species(target, all_products, charge=charge):
            details.append(f'{name}: the actual IRC product endpoint does not match all declared products.')
            continue
        if atom_binding:
            mapping = atom_binding.get('atom_map', [])
            if (len(mapping) != len(symbols) or any(type(index) is not int for index in mapping)
                    or sorted(mapping) != list(range(1, len(symbols) + 1))
                    or list(target[0]) != list(symbols)):
                details.append('The bound product correspondence does not cover the native IRC atom order.')
                continue
            product_order = ([target[0][index - 1] for index in mapping],
                             [target[1][index - 1] for index in mapping])
            if not _ordered_graph_matches(product_order, atom_binding['product_mol'], charge):
                details.append('The actual IRC product endpoint differs from the bound product atom identities.')
                continue
        for minimum in source_geometries:
            identity = list(range(len(symbols))) if atom_binding else None
            if atom_binding and not _ordered_graph_matches(minimum, atom_binding['reactant_mol'], charge):
                continue
            aligned_source = align_atom_order(symbols, positions, *source, atom_order=identity)
            aligned_minimum = align_atom_order(symbols, positions, *minimum, atom_order=identity)
            if aligned_source is None or aligned_minimum is None:
                details.append('The reactant IRC endpoint or minimum cannot be aligned to the TS.')
                continue
            result = evaluate_endpoint_between(symbols, positions,
                [source[1][index] for index in aligned_source[0]],
                [minimum[1][index] for index in aligned_minimum[0]], [], charge)
            if result['is_decidable'] and result['is_between']:
                return dict(is_decidable=True, is_match=True, assignment=name,
                    proof_scope='separated_products', details=[
                        'The actual IRC endpoint matches every declared separated product, each supported '
                        'by an independent zero-imaginary minimum; the reactant direction passes the '
                        'existing interval proof. This does not verify a bound product complex minimum.',
                        *result['details']])
            failure['is_decidable'] = failure['is_decidable'] or result['is_decidable']
            details.extend(result['details'])
    return {**failure, 'details': details or ['No verified reactant minimum supports the IRC direction.']}


def _usable_ts_geometries(ts_logs, *, details: list[str]) -> list[tuple]:
    geometries = []
    for path in ts_logs:
        n_imag, geometry = probe_log(path)
        if n_imag == 1 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"TS candidate {path} is not usable: a first-order saddle log "
                f"(exactly one imaginary frequency) with a final geometry is "
                f"required; got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries


def _usable_minimum_geometries(logs, *, side: str, details: list[str]) -> list[tuple]:
    geometries = []
    for path in logs:
        n_imag, geometry = probe_log(path)
        if n_imag == 0 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"{side} candidate {path} is not usable: a verified minimum log "
                f"(zero imaginary frequencies) with a final geometry is required; "
                f"got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries


def _optimization_geometries(path):
    """Native converged Opt input/final geometries, independent of frequency parsing."""
    if not normal_log(path):
        return None
    text = Path(path).read_text(errors='replace')
    engine = qm_engine.detect_qm_engine(str(path))
    if engine == 'orca':
        if orca_frames.opt_converged(text) is not True:
            return None
        index = text.find('CARTESIAN COORDINATES (ANGSTROEM)')
        first = parse_xyz(orca_frames.input_xyz_from_text(text))
        if first is None and index >= 0:
            first = parse_xyz(orca_frames._xyz_block_at(text, index))
        last = parse_xyz(orca_frames.final_xyz_from_text(text))
    elif engine == 'gaussian':
        if ('Optimization stopped.' in text or not any(marker in text for marker in
                ('Optimization completed.', 'Stationary point found.'))):
            return None
        lines = text.splitlines()
        first_rows = next((gaussian_frames._parse_coord_block_after(lines, index + 1, has_type_col=True)
            for index, line in enumerate(lines)
            if 'Input orientation:' in line or 'Standard orientation:' in line), None)
        blocks = gaussian_frames.std_orientation_frames(text)
        last_rows = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(text)

        def geometry(rows):
            return parse_xyz(gaussian_frames._coords_to_xyz(
                [row[0] for row in rows], [row[1:] for row in rows])) if rows else None

        first, last = geometry(first_rows), geometry(last_rows)
    else:
        return None
    return (first, last) if first is not None and last is not None else None


def _optimized_minima(logs, *, smiles, side, charge, details):
    minima = _usable_minimum_geometries(logs, side=side, details=details)
    if smiles is not None:
        from cloudra.tools.core.species_identity import chemical_smiles
        expected = chemical_smiles(smiles)
        minima = [geometry for geometry in minima if _geometry_matches_species(geometry, expected, charge=charge)]
        if not minima:
            details.append(f'{side}: no zero-imaginary minimum matches the declared species.')
    results = []
    for path in logs:
        geometries = _optimization_geometries(path)
        if geometries is not None and any(same_geometry(geometries[1], minimum) for minimum in minima):
            results.append((geometries[0], geometries[1], path))
    if not results:
        details.append(f'{side}: supply a normally converged Opt log starting from the actual IRC outer frame '
                       'and a zero-imaginary Freq log at that optimization final geometry; combined Opt/Freq is accepted.')
    return results


def _endpoint_optimization_proof(ends, ts_geometry, source_logs, target_logs, *,
        charge=0, atom_binding=None, reactant_smiles=None, product_smiles=None):
    """Both real IRC sides must terminate in the declared verified minima via Opt."""
    from cloudra.tools.core.irc_path import align_atom_order

    details = []
    source = _optimized_minima(source_logs, smiles=reactant_smiles, side='SOURCE/reactant',
        charge=charge, details=details)
    target = _optimized_minima(target_logs, smiles=product_smiles, side='TARGET/product',
        charge=charge, details=details)
    for name, source_end, target_end in (('direct', ends[0], ends[1]), ('swapped', ends[1], ends[0])):
        for source_start, source_minimum, source_log in source:
            if not same_geometry(source_start, source_end):
                continue
            for target_start, target_minimum, target_log in target:
                if not same_geometry(target_start, target_end):
                    continue
                if atom_binding:
                    # Native Opt rows retain the correspondence of their actual IRC input.
                    # Reorder by the input match, never by similarity of the relaxed minimum.
                    mapping = atom_binding.get('atom_map', [])
                    count = len(ts_geometry[0])
                    if (len(mapping) != count or any(type(index) is not int for index in mapping)
                            or sorted(mapping) != list(range(1, count + 1))):
                        continue
                    source_order = align_atom_order(*source_end, *source_start)
                    target_order = align_atom_order(*target_end, *target_start)
                    if source_order is None or target_order is None:
                        continue
                    source_bound = (source_end[0], [source_minimum[1][index] for index in source_order[0]])
                    target_bound = (target_end[0], [target_minimum[1][index] for index in target_order[0]])
                    target_bound = ([target_bound[0][index - 1] for index in mapping],
                                    [target_bound[1][index - 1] for index in mapping])
                    if (not _ordered_graph_matches(source_bound, atom_binding['reactant_mol'], charge)
                            or not _ordered_graph_matches(target_bound, atom_binding['product_mol'], charge)):
                        details.append('Optimized IRC endpoints differ from the bound complete atom identities.')
                        continue
                result = [f'{name} pairing: both actual IRC outer frames were independently optimized '
                    f'to the correct zero-imaginary minima ({source_log}; {target_log}).']
                try:
                    interval = prove_irc_endpoint_direction(*ts_geometry, *ends, source_minimum, target_minimum,
                        [], charge, atom_orders=bound_atom_orders(ts_geometry, source_minimum, target_minimum, atom_binding))
                    result.extend('[advisory] ' + item for item in interval.get('details', []))
                    if not (interval['is_decidable'] and interval['is_match']):
                        result.append('[warning] Endpoint optimization establishes direction, but the geometric interval '
                            'check failed or is undecidable; inspect the trajectory for suspicious geometry.')
                except Exception as exc:
                    result.append(f'[warning] Endpoint optimization establishes direction, but the geometric interval '
                                  f'could not be evaluated ({exc}); inspect the trajectory.')
                return True, result
    return False, ['The actual IRC outer frames are not connected to both declared zero-imaginary minima '
                   'by converged optimization logs; geometric interval agreement alone is not direction proof.', *details]


def verify_short_irc_direction(
    irc_log,
    ts_logs: Sequence,
    endpoint_a_logs: Sequence,
    endpoint_b_logs: Sequence,
    *,
    charge: int = 0,
    atom_bindings=None,
    reactant_smiles: str | list[str] | None = None,
    product_smiles: str | list[str] | None = None,
) -> tuple[bool, list[str]]:
    """同一 TS 双向 IRC 的真实外帧经 Opt/Freq 到正确极小值即方向通过。

    材料：IRC 双侧端点与同一 TS 的单虚频日志；endpoint_a_logs /
    endpoint_b_logs 分别提供产物/反应物的 Opt/Freq 原生日志。首帧须匹配
    真实 IRC 外帧，收敛末帧须匹配零虚频几何，两侧可 direct/swapped 配对。

    返回 (passed, details)：passed=False 时 details 结构化写明缺哪份材料
    或证明为何不成立（缺 TS/端点材料 ⇒ 引导先补对应阶段的绑定证据）。
    """
    details: list[str] = []
    ends = irc_endpoint_geometries(irc_log)
    if ends is None:
        return False, [
            f"the IRC log {irc_log} does not yield usable endpoint geometries on "
            "both sides (Gaussian: outermost coordinated frames on the rx<0 and "
            "rx>0 sides; ORCA: endpoint files or outermost F/B trajectory frames — "
            "an unconverged direction's last frame is a legitimate partial "
            "endpoint); bind the parser output of a finished IRC job log"
        ]
    atom_binding = (atom_bindings or {}).get(str(irc_log))
    ts_geometries = [(geometry, (atom_bindings or {}).get(str(path)))
        for path in ts_logs
        for geometry in _usable_ts_geometries([path], details=details)]
    anchor = irc_start_geometry(irc_log)
    ts_geometries = [item for item in ts_geometries if same_geometry(item[0], anchor)]
    if not ts_geometries:
        details.append('IRC starting saddle is missing or differs from the submitted TS geometry; submit evidence from the same TS calculation geometry.')
    from_geometries = _usable_minimum_geometries(
        endpoint_b_logs, side="endpoint_b (SOURCE/reactant side)",
        details=details,
    )
    to_geometries = _usable_minimum_geometries(
        endpoint_a_logs, side="endpoint_a (TARGET/product side)",
        details=details,
    )
    if not ts_geometries:
        details.append(
            "missing TS material: bind the step's ts_opt/frequency stage evidence "
            "first (a normally terminated first-order saddle log with a final geometry)"
        )
    if not from_geometries:
        details.append(
            "missing endpoint_b material (SOURCE/reactant side): bind endpoint_b "
            "evidence or the source species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not to_geometries:
        details.append(
            "missing endpoint_a material (TARGET/product side): bind endpoint_a "
            "evidence or the target species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not (ts_geometries and from_geometries):
        return False, details
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for ts_geometry, ts_binding in ts_geometries:
            passed, proof_details = _endpoint_optimization_proof(
                ends, ts_geometry, endpoint_b_logs, endpoint_a_logs, charge=charge,
                reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None,
            )
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for ts_geometry, ts_binding in ts_geometries:
            verdict = verify_separated_product_direction(ends, ts_geometry, from_geometries,
                product_smiles, to_geometries, charge=charge,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict["is_match"]:
                return True, verdict["details"]
            details.extend(verdict["details"])
    return False, list(dict.fromkeys(details))


def verify_short_irc_pair(forward_log, reverse_log, ts_logs, endpoint_a_logs, endpoint_b_logs, *,
        atom_bindings=None, charge=0, reactant_smiles: str | list[str] | None = None,
        product_smiles: str | list[str] | None = None):
    """Combine native directional logs using the same endpoint-optimization proof."""
    def outer_geometry(path, direction):
        engine = qm_engine.detect_qm_engine(str(path))
        if engine == 'orca':
            orca_frames.extract_irc(str(path))
            endpoints = orca_frames.extract_irc_endpoints(str(path))
            for side in (direction, 'backward' if direction == 'forward' else 'forward'):
                xyz = orca_frames.read_endpoint_geometry(endpoints[side])
                if xyz:
                    return parse_xyz(xyz)
        elif engine == 'gaussian':
            frames = [f for f in irc_frames_for(path) if f.xyz.strip() and f.reaction_coordinate]
            preferred = [f for f in frames if (f.reaction_coordinate > 0) == (direction == 'forward')]
            candidates = preferred or frames
            if candidates:
                return parse_xyz(max(candidates, key=lambda f: abs(f.reaction_coordinate)).xyz)
        return None

    details = []
    try:
        forward = outer_geometry(forward_log, 'forward')
        reverse = outer_geometry(reverse_log, 'backward')
    except (ValueError, OSError) as exc:
        return False, [f'Directional IRC evidence could not be read: {exc}']
    if forward is None or reverse is None:
        return False, ['Both submitted directional logs must supply an outer endpoint geometry.']
    atom_binding = (atom_bindings or {}).get(str(forward_log))
    if atom_binding != (atom_bindings or {}).get(str(reverse_log)):
        atom_binding = None
    ts = [(geometry, (atom_bindings or {}).get(str(path))) for path in ts_logs
          for geometry in _usable_ts_geometries([path], details=details)]
    starts = [irc_start_geometry(path) for path in (forward_log, reverse_log)]
    ts = [item for item in ts if all(same_geometry(item[0], start) for start in starts)]
    source = _usable_minimum_geometries(endpoint_b_logs, side='SOURCE', details=details)
    target = _usable_minimum_geometries(endpoint_a_logs, side='TARGET', details=details)
    if not (ts and source):
        return False, [*details, 'Bind the TS and frequency-verified source/target minimum logs.']
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for geometry, ts_binding in ts:
            passed, proof_details = _endpoint_optimization_proof((forward, reverse), geometry,
                endpoint_b_logs, endpoint_a_logs, charge=charge,
                reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for geometry, ts_binding in ts:
            verdict = verify_separated_product_direction((forward, reverse), geometry, source,
                product_smiles, target, charge=(atom_binding or {}).get('charge', 0),
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict['is_match']:
                return True, verdict['details']
            details.extend(verdict['details'])
    return False, ['The paired IRC endpoint optimization proof is incomplete.', *details]
