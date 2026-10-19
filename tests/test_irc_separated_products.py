"""Separated products retain real IRC and independent minimum evidence."""
from pathlib import Path

import numpy as np
import pytest

from cloudra.tools.core import irc_evidence

FIXTURE = Path(__file__).parent / 'fixtures' / 'nu3_atom_binding'
MAP = [1, 4, 5, 6, 10, 11, 3, 2, 7, 8, 9]
PRODUCTS = ['C=C', 'O=[PH3]']


def materials():
    from rdkit import Chem

    product = Chem.MolFromMolFile(str(FIXTURE / 'product.mol'), removeHs=False)
    symbols = [atom.GetSymbol() for atom in product.GetAtoms()]
    positions = product.GetConformer().GetPositions()
    components = [(list(symbols[i] for i in indices), positions[list(indices)])
                  for indices in Chem.GetMolFrags(product)]
    binding = dict(atom_map=MAP, charge=0,
        reactant_mol=(FIXTURE / 'reactant.mol').read_text(),
        product_mol=(FIXTURE / 'product.mol').read_text())
    return (irc_evidence.irc_endpoint_geometries(FIXTURE / 'irc.out'),
            irc_evidence.probe_log(FIXTURE / 'ts.out')[1],
            irc_evidence.probe_log(FIXTURE / 'reactant.out')[1], components, binding)


def verify(ends, ts, source, products, components, binding):
    verifier = getattr(irc_evidence, 'verify_separated_product_direction', None)
    assert verifier is not None, 'Separated-product IRC acceptance is missing.'
    return verifier(ends, ts, [source], products, components, atom_binding=binding)


@pytest.mark.parametrize('swapped', [False, True])
def test_real_irc_accepts_separated_products_without_combined_minimum(swapped, rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    verdict = verify(ends[::-1] if swapped else ends, ts, source, PRODUCTS, components, binding)
    assert verdict['is_match'], verdict['details']
    assert verdict['proof_scope'] == 'separated_products'
    assert verdict['assignment'] == ('direct' if swapped else 'swapped')


@pytest.mark.parametrize('products', [
    ['C=C.O=[PH3]'], ['C=C'],
    ['C=C', 'O=[PH3]', 'C=C'], ['CC', 'O=[PH3]'],
])
def test_declared_complex_or_wrong_component_graph_does_not_pass(products, rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    assert not verify(ends, ts, source, products, components, binding)['is_match']


@pytest.mark.parametrize('missing', [0, 1])
def test_each_product_requires_its_own_minimum_geometry(missing, rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    assert not verify(ends, ts, source, PRODUCTS, components[:missing] + components[missing+1:], binding)['is_match']


def test_product_identity_comes_from_real_irc_endpoint(rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    assert not verify((ends[1], ends[1]), ts, source, PRODUCTS, components, binding)['is_match']


def test_separated_product_does_not_replace_reactant_direction_proof(rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    assert not verify((ends[0], ends[0]), ts, source, PRODUCTS, components, binding)['is_match']


def test_separated_product_rejects_changed_bound_hydrogen_parents(rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    changed = np.array(ends[0][1], dtype=float)
    changed[[4, 8]] = changed[[8, 4]]
    assert not verify(((ends[0][0], changed), ends[1]), ts, source, PRODUCTS, components, binding)['is_match']


@pytest.mark.parametrize('paired', [False, True])
@pytest.mark.parametrize('component_imag', [0, 1, None])
def test_log_wrappers_only_accept_frequency_verified_components(monkeypatch, paired, component_imag, rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    logs = {'ts': (1, ts), 'source': (0, source),
            'ethene': (component_imag, components[0]), 'phosphine_oxide': (0, components[1])}
    monkeypatch.setattr(irc_evidence, 'probe_log', lambda path, **_: logs[path])
    monkeypatch.setattr(irc_evidence, 'irc_endpoint_geometries', lambda *_, **__: ends)
    monkeypatch.setattr(irc_evidence, 'irc_start_geometry', lambda _: ts)
    if paired:
        monkeypatch.setattr(irc_evidence.qm_engine, 'detect_qm_engine', lambda _: 'gaussian')
        from types import SimpleNamespace

        from cloudra.tools.core.irc_path import xyz_block
        monkeypatch.setattr(irc_evidence, 'irc_frames_for', lambda path: [SimpleNamespace(
            xyz=xyz_block(*(ends[0] if path == 'forward' else ends[1])),
            reaction_coordinate=1 if path == 'forward' else -1)])
        passed, details = irc_evidence.verify_short_irc_pair(
            'forward', 'reverse', ['ts'], ['ethene', 'phosphine_oxide'], ['source'],
            product_smiles=PRODUCTS, atom_bindings={'forward': binding, 'reverse': binding, 'ts': binding})
    else:
        passed, details = irc_evidence.verify_short_irc_direction(
            'irc', ['ts'], ['ethene', 'phosphine_oxide'], ['source'],
            product_smiles=PRODUCTS, atom_bindings={'irc': binding, 'ts': binding})
    assert passed is (component_imag == 0), details


def test_explicit_classifier_can_identify_components_of_an_unverified_complex(rdkit_chemistry):
    ends, ts, source, components, binding = materials()
    verdict = verify(ends, ts, source, 'C=C.O=[PH3]', components, binding)
    assert verdict['is_match'], verdict['details']
    assert verdict['proof_scope'] == 'separated_products'


def test_component_log_cannot_reuse_frequencies_from_another_geometry(tmp_path):
    text = (FIXTURE / 'product.out').read_text()
    changed = text[text.index('CARTESIAN COORDINATES (ANGSTROEM)'):text.index('FINAL SINGLE POINT ENERGY')]
    changed = changed.replace('0.140226', '5.140226')
    log = tmp_path / 'stale_frequency.out'
    log.write_text(text.replace('                             ****ORCA TERMINATED NORMALLY****',
        changed + '                             ****ORCA TERMINATED NORMALLY****'))
    n_imag, geometry = irc_evidence.probe_log(log)
    assert n_imag is None and geometry is None


def embedded_geometry(smiles, seed=7):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(molecule, randomSeed=seed) == 0
    return [atom.GetSymbol() for atom in molecule.GetAtoms()], molecule.GetConformer().GetPositions()


def test_repeated_products_keep_endpoint_stoichiometry(rdkit_chemistry):
    source = embedded_geometry('C1CCC1')
    ts = source[0], source[1] * 1.1
    source_end = source[0], (source[1] + ts[1]) / 2
    ethene = embedded_geometry('C=C')
    product_end = ethene[0] * 2, np.concatenate([ethene[1], ethene[1] + [8., 0., 0.]])
    # One minimum calculation can support the same chemical species twice;
    # the real IRC endpoint must nevertheless contain both complete molecules.
    verdict = verify((source_end, product_end), ts, source, ['C=C', 'C=C'], [ethene], None)
    assert verdict['is_match'], verdict['details']
    assert not verify((source_end, product_end), ts, source, ['C=C', 'C=C', 'C=C'], [ethene], None)['is_match']


def test_product_stereochemistry_is_checked_from_irc_coordinates(rdkit_chemistry):
    left = embedded_geometry('F[C@](Cl)(Br)I')
    right = embedded_geometry('F[C@@](Cl)(Br)I')
    water = embedded_geometry('O')
    product_end = left[0] + water[0], np.concatenate([left[1], water[1] + [8., 0., 0.]])
    ts = product_end[0], product_end[1] * 1.1
    source_end = product_end[0], (product_end[1] + ts[1]) / 2
    verdict = verify((source_end, product_end), ts, product_end,
                     ['F[C@@](Cl)(Br)I', 'O'], [right, water], None)
    assert not verdict['is_match']


@pytest.mark.parametrize('paired', [False, True])
@pytest.mark.parametrize('products', [PRODUCTS, ['C=C.O=[PH3]', 'N']])
def test_separated_declaration_cannot_bypass_component_checks_with_a_complex_minimum(paired, products, rdkit_chemistry):
    _, _, _, _, binding = materials()
    ts, irc = FIXTURE / 'ts.out', FIXTURE / 'irc.out'
    associations = {str(ts): binding, str(irc): binding}
    arguments = ([ts], [FIXTURE / 'product.out'], [FIXTURE / 'reactant.out'])
    if paired:
        passed, details = irc_evidence.verify_short_irc_pair(irc, irc, *arguments,
            product_smiles=products, atom_bindings=associations)
    else:
        passed, details = irc_evidence.verify_short_irc_direction(irc, *arguments,
            product_smiles=products, atom_bindings=associations)
    assert not passed, details


def charged_native_bundle(directory):
    """Parser fixtures: captured NU3 geometries plus a distant hydroxide spectator.

    These native-shaped logs test charge propagation, not new QM calculations.
    """
    from cloudra.tools.core.irc_path import xyz_block
    from tests.ts_fixtures import native_qm_log

    ends, ts, source, components, _ = materials()
    hydroxide = embedded_geometry('[OH-]')
    hydroxide = hydroxide[0], hydroxide[1] + [20., 0., 0.]

    def with_spectator(geometry):
        return geometry[0] + hydroxide[0], np.concatenate([geometry[1], hydroxide[1]])

    def log(name, geometry, frequencies):
        path = directory / name
        path.write_text(native_qm_log('orca', *geometry, optimization=None, frequencies=frequencies))
        return path

    ts = with_spectator(ts)
    paths = {
        'ts': log('ts.out', ts, [-100., 200., 300.]),
        'source': log('source.out', with_spectator(source), [100., 200., 300.]),
        'components': [log(f'component_{index}.out', geometry, [100., 200., 300.])
                       for index, geometry in enumerate([*components, hydroxide])],
    }
    irc = directory / 'irc.out'
    text = native_qm_log('orca', *ts, optimization=None).replace('! Freq', '! IRC')
    irc.write_text(text.replace('ORCA TERMINATED NORMALLY',
        'Intrinsic Reaction Coordinate Calculation\n'
        '* FORWARD IRC *\n0 -92.0 -1.0 0.1 0.1\n'
        '* BACKWARD IRC *\n0 -92.0 -1.0 0.1 0.1\nORCA TERMINATED NORMALLY'))
    for suffix, geometry in zip(('F', 'B'), ends, strict=True):
        (directory / f'irc_IRC_{suffix}.xyz').write_text(xyz_block(*with_spectator(geometry)))
    paths['irc'] = irc
    return paths


@pytest.mark.parametrize('paired', [False, True])
@pytest.mark.parametrize('charge', [-1, 0])
def test_native_separated_irc_preserves_explicit_charge_without_binding(tmp_path, paired, charge, rdkit_chemistry):
    paths = charged_native_bundle(tmp_path)
    arguments = ([paths['ts']], paths['components'], [paths['source']])
    keywords = dict(charge=charge, product_smiles=[*PRODUCTS, '[OH-]'])

    if paired:
        passed, details = irc_evidence.verify_short_irc_pair(paths['irc'], paths['irc'], *arguments, **keywords)
    else:
        passed, details = irc_evidence.verify_short_irc_direction(paths['irc'], *arguments, **keywords)

    assert passed is (charge == -1), details
