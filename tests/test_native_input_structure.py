"""All native input readers agree on sections and Angstrom coordinates."""

from contextlib import contextmanager

import pytest
from ase.units import Bohr

from cloudra.tools.Chemtool.format_converter import FormatConverter, FormatConverter_input_schema
from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import (
    compare_calculation_input,
    gaussian_routes,
    inspect_input,
    native_input_geometry,
)
from cloudra.tools.core.molecule import read_molecule

GAUSSIAN = '#p hf/sto-3g\n\n7 9\n\n0 1\nH 0.0 0.0 0.0\nH 1.4 0.0 0.0\n\n'


def test_gaussian_numeric_title_does_not_become_charge_or_geometry():
    intent = inspect_input(GAUSSIAN, engine='gaussian')

    assert (intent.charge, intent.multiplicity) == (0, 1)
    assert native_input_geometry(GAUSSIAN, engine='gaussian') == [
        ('H', (0.0, 0.0, 0.0)), ('H', (1.4, 0.0, 0.0)),
    ]
    expected = dict(engine='gaussian', method='HF', basis_set='STO-3G', keywords='', end_setting='')
    assert compare_calculation_input(GAUSSIAN, expected, charge=0, multiplicity=1) == []


@pytest.mark.parametrize('units', ['bohr', '( bohr )', 'au', 'a.u.'])
def test_native_geometry_normalizes_declared_gaussian_units(units):
    text = GAUSSIAN.replace('7 9', 'hydrogen').replace('hf/sto-3g', f'hf/sto-3g units={units}')

    geometry = native_input_geometry(text, engine='gaussian')

    assert geometry[1][1] == pytest.approx((1.4 * Bohr, 0.0, 0.0))


@pytest.mark.parametrize('setting', ['scf=(tight', 'scf="tight'])
def test_native_geometry_and_charge_remain_readable_when_calculation_syntax_is_malformed(setting):
    text = GAUSSIAN.replace('hf/sto-3g', f'hf/sto-3g units=bohr {setting}').replace('0 1\n', '-1 2\n')

    geometry = native_input_geometry(text, engine='gaussian')

    assert geometry[1][1] == pytest.approx((1.4 * Bohr, 0.0, 0.0))
    expected = dict(engine='gaussian', method='HF', basis_set='STO-3G', keywords=f'units=bohr {setting}')
    differences = compare_calculation_input(text, expected, charge=0, multiplicity=1)
    assert {'charge', 'multiplicity'} <= {item.field for item in differences}
    assert inspect_input(text, engine='gaussian').certainty == 'unknown'


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.asyncio
@pytest.mark.parametrize('output_format', ['xyz', 'inp'])
async def test_converter_uses_normalized_gaussian_geometry(tmp_path, output_format):
    source = tmp_path / 'source.gjf'
    source.write_text(GAUSSIAN.replace('7 9', 'hydrogen').replace('hf/sto-3g', 'hf/sto-3g units=bohr'))
    output = tmp_path / f'converted.{output_format}'

    result = await FormatConverter().tool_call(FormatConverter_input_schema(
        input_path=str(source), input_format='gjf', output_path=str(output), output_format=output_format,
    ), session=None)

    assert result.is_success, result.message
    if output_format == 'xyz':
        position = read_molecule(input_path=output).GetConformer().GetAtomPosition(1).x
    else:
        # ASE emits *xyz, which must be readable by the repository's native readers.
        position = native_input_geometry(output.read_text(), engine='orca')[1][1][0]
    assert position == pytest.approx(1.4 * Bohr)


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.asyncio
@pytest.mark.parametrize('units,extra_keywords', [
    ('bohr', ''), ('( bohr )', ''), ('au', ''), ('a.u.', ''), ('angstroms', ''), (None, ''),
    ('bohr', 'scf=(tight'),
])
async def test_gaussian_writer_preserves_angstrom_source_geometry_with_explicit_native_units(tmp_path, units, extra_keywords):
    source = tmp_path / 'source.xyz'
    source.write_text('2\nAngstrom source\nH 0.0 0.0 0.0\nH 1.4 0.0 0.0\n')
    output = tmp_path / 'written.gjf'
    keywords = ' '.join(filter(None, [f'units={units}' if units else '', extra_keywords]))

    result = await QmInputWriter().tool_call(QmInputWriter_input_schema(
        engine='gaussian', method='HF', basis_set='STO-3G', charge=0, multiplicity=1,
        task_type=[{'sp': None}], keywords=keywords, source_type='xyz_file', source_value=str(source),
        output_path=str(output),
    ), session=None)

    assert result.is_success, result.message
    content = output.read_text()
    assert keywords in next(line for line in content.splitlines() if line.startswith('#'))
    molecule = read_molecule(input_path=output)
    assert molecule.GetConformer().GetAtomPosition(1).x == pytest.approx(1.4, abs=1e-8)
    assert native_input_geometry(content, engine='gaussian')[1][1] == pytest.approx((1.4, 0.0, 0.0), abs=1e-8)
    assert molecule.GetProp('cloudra_source_coordinate_units') == ('bohr' if units in {'bohr', '( bohr )', 'au', 'a.u.'} else 'angstrom')


@pytest.mark.parametrize('marker', ['*xyz -1 2', '* xyz -1 2', '*XYZ -1 2'])
def test_orca_compact_and_spaced_coordinate_markers_share_charge_and_geometry(marker):
    text = f'! HF STO-3G\n{marker}\nH 0.0 0.0 0.0\nH 0.74 0.0 0.0\n*\n'

    intent = inspect_input(text, engine='orca')

    assert (intent.charge, intent.multiplicity) == (-1, 2)
    assert native_input_geometry(text, engine='orca')[1] == ('H', (0.74, 0.0, 0.0))


def test_inspection_keeps_link1_and_checkpoint_only_routes():
    text = GAUSSIAN.replace('7 9', 'hydrogen') + '--Link1--\n%oldchk=source.chk\n#p hf/sto-3g irc geom=allcheck\n\n'

    assert gaussian_routes(text) == [['hf/sto-3g'], ['hf/sto-3g', 'irc', 'geom=allcheck']]
    intent = inspect_input(text, engine='gaussian')
    assert intent.tasks == {'irc'}
    assert (intent.charge, intent.multiplicity) == (0, 1)
    assert inspect_input('#p hf/sto-3g irc geom=allcheck\n\n', engine='gaussian').tasks == {'irc'}
    with pytest.raises(ValueError, match='Link1|Exactly one'):
        native_input_geometry(text, engine='gaussian')
    with pytest.raises(ValueError, match='checkpoint|explicit'):
        native_input_geometry('#p hf/sto-3g irc geom=allcheck\n\n', engine='gaussian')


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('text', [GAUSSIAN, '1\nframe\nH 0.0 0.0 0.0\n'])
def test_coordinate_readers_accept_utf8_bom(text):
    mol = read_molecule(input_text='\ufeff' + text)

    assert mol.GetAtomWithIdx(0).GetSymbol() == 'H'


def test_existing_irc_reuse_rejects_bohr_numbers_matching_a_different_angstrom_frame(tmp_path, monkeypatch):
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord, _reuse_existing_irc
    from tests.ts_fixtures import calculation_input

    frequency = tmp_path / 'frequency'
    frequency.mkdir()
    geometry = frequency / 'optimized.xyz'
    geometry.write_text('2\naccepted Angstrom frame\nH 0 0 0\nH 1.4 0 0\n')
    native = tmp_path / 'source.gjf'
    native.write_text(GAUSSIAN.replace('7 9', 'hydrogen').replace('hf/sto-3g', 'hf/sto-3g irc units=bohr'))
    log = tmp_path / 'source.log'
    log.write_text('Normal termination of Gaussian 16\n')
    inputs = calculation_input(reactant_smiles='[H][H]', product_smiles='[H][H]', method='HF/STO-3G',
        engine='gaussian', keywords='units=bohr', irc_log=str(log))
    record = TsProcessRecord(run_id='ts_0001', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        owner_conversation_id='project', owner_session_id='owner', input=inputs)
    record.job_steps = [TsJobStep(purpose='frequency', state='done', job_id=99,
        input_path=str(frequency / 'input.gjf'), actual_calculation=inputs.verification.frequency)]

    class FakeDB:
        @contextmanager
        def connect(self):
            yield self

        def execute(self, *_):
            return self

        def fetchall(self):
            return [(77, str(native), 'gaussian')]

    monkeypatch.setattr('cloudra.services.ts_pipeline_context.pipeline_database', FakeDB)
    monkeypatch.setattr('cloudra.services.ts_pipeline_store.verify_stage_input', lambda *_: {'sha256': 'fixture'})
    monkeypatch.setattr('cloudra.infra.compute_utils.resolve_log_path', lambda *_args, **_kwargs: str(log))
    monkeypatch.setattr('cloudra.tools.Chemtool.ts_guess.TsGuess._extract_irc_endpoints',
        lambda *_args, **_kwargs: {'path_a': str(geometry), 'path_b': str(geometry)})

    with use_pipeline_authority(lambda *_: (True, None)):
        with pytest.raises(ValueError, match='geometry differs'):
            _reuse_existing_irc(record)
