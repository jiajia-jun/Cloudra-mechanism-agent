"""Native writer fidelity and engineering boundaries; no QM processes."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from ase.units import Bohr

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import native_input_geometry, orca_directives
from cloudra.tools.core.molecule import read_molecule

pytest.importorskip('rdkit')

XYZ = '2\nAngstrom source\nH 0 0 0\nH 1.4 0 0\n'


def request_for(tmp_path, engine='orca', **settings):
    source = tmp_path / 'source.xyz'
    source.write_text(XYZ)
    values = dict(engine=engine, method='HF', basis_set='STO-3G', charge=0,
        source_type='xyz_file', source_value=str(source), task_type=[{'sp': None}],
        output_path=str(tmp_path / ('job.inp' if engine == 'orca' else 'job.gjf')))
    values.update(settings)
    return QmInputWriter_input_schema(**values)


async def write_request(request, tmp_path):
    writer = QmInputWriter(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    result = await writer.tool_call(request, None)
    content = Path(result.input_path).read_text() if result.is_success else ''
    return result, content


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,settings', [
    ('orca', {}),
    ('orca', {'keywords': 'Angs'}),
    ('orca', {'keywords': 'Bohrs'}),
    ('orca', {'keywords': 'BOHRS'}),
    ('orca', {'orca_blocks': '%coords\n Units Bohrs\nend'}),
    ('orca', {'orca_blocks': '%coords\n Units = Bohrs\nend'}),
    ('orca', {'orca_blocks': '%coords Units=Bohrs end'}),
    ('orca', {'orca_blocks': '%coords\n pardef\n r = 1.0;\n end\n Units Bohrs\nend'}),
    ('orca', {'orca_blocks': '%coords pardef r = 1.0; end Units Bohrs end'}),
    ('orca', {'keywords': 'Bohrs', 'orca_blocks': '%coords Units Bohrs end'}),
    ('gaussian', {'keywords': 'Units=Bohr'}),
])
async def test_native_units_preserve_source_physical_geometry(tmp_path, engine, settings):
    request = request_for(tmp_path, engine, **settings)

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    geometry = native_input_geometry(content, engine=engine)
    assert geometry[1][1] == pytest.approx((1.4, 0, 0), abs=1e-8)
    # An independent serialization check also catches a reader and writer
    # mistakenly agreeing to ignore the same valid native unit syntax.
    if any('bohr' in value.lower() for value in settings.values()):
        positions = [float(line.split()[1]) for line in content.splitlines() if line.startswith('H ')]
        assert positions[-1] == pytest.approx(1.4 / Bohr, abs=1e-8)
    for value in settings.values():
        assert value in content


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,settings', [
    ('orca', {'orca_blocks': '%coords Units UnknownUnits end'}),
    ('orca', {'orca_blocks': '%coords Units=UnknownUnits end'}),
    ('orca', {'orca_blocks': '%coords\n pardef\n r = 1.0;\n end\n Units UnknownUnits\nend'}),
    ('orca', {'keywords': 'Bohrs', 'orca_blocks': '%coords Units = Angs end'}),
    ('orca', {'keywords': 'Bohrs Angs'}),
    ('orca', {'keywords': 'Bohrs', 'orca_blocks': '%coords Units Angs end'}),
    ('gaussian', {'keywords': 'Units=UnknownUnits'}),
    ('gaussian', {'keywords': 'Units=Bohr Units=Angstrom'}),
])
async def test_unknown_or_conflicting_units_refuse_without_writing(tmp_path, engine, settings):
    request = request_for(tmp_path, engine, **settings)

    result, _ = await write_request(request, tmp_path)

    assert not result.is_success
    assert 'unit' in result.message.lower()
    assert not Path(request.output_path).exists()
    with pytest.raises(ValueError, match='[Uu]nit'):
        QmInputWriter.render_input(request, read_molecule(input_text=XYZ, charge=0))


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['chk_name', 'rwf_name', 'fchk_name'])
@pytest.mark.parametrize('via_symlink', [False, True])
async def test_gaussian_artifact_cannot_alias_input_destination(tmp_path, field, via_symlink):
    target = tmp_path / 'job.gjf'
    artifact = target
    if via_symlink:
        artifact = tmp_path / 'alias'
        artifact.symlink_to(target)
    request = request_for(tmp_path, 'gaussian', **{field: str(artifact)})

    result, _ = await write_request(request, tmp_path)

    assert not result.is_success
    assert field in result.message
    assert 'input' in result.message.lower()
    assert not target.exists()
    with pytest.raises(ValueError, match=field):
        QmInputWriter.render_input(request, read_molecule(input_text=XYZ, charge=0))


@pytest.mark.asyncio
async def test_default_checkpoint_cannot_alias_chk_named_input(tmp_path):
    request = request_for(tmp_path, 'gaussian', output_path=str(tmp_path / 'job.chk'))

    result, _ = await write_request(request, tmp_path)

    assert not result.is_success
    assert 'chk_name' in result.message
    assert not Path(request.output_path).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['chk_name', 'rwf_name', 'fchk_name'])
async def test_existing_identical_input_cannot_be_reused_with_hardlinked_artifact(tmp_path, field):
    artifact = tmp_path / 'hardlinked-native-file'
    request = request_for(tmp_path, 'gaussian', **{field: str(artifact)})
    output = Path(request.output_path)
    content = QmInputWriter.render_input(request, read_molecule(input_text=XYZ, charge=0))
    output.write_text(content)
    artifact.hardlink_to(output)

    result, _ = await write_request(request, tmp_path)

    assert not result.is_success
    assert field in result.message and 'input' in result.message.lower()
    assert artifact.samefile(output)
    assert output.read_text() == content


@pytest.mark.asyncio
async def test_unrepresentable_orca_memory_refuses_before_reading_source(tmp_path, monkeypatch):
    request = request_for(tmp_path, mem='3MB', nproc=4)

    def unexpected_source_read(*_):
        raise AssertionError('source must not be read for an invalid resource request')

    monkeypatch.setattr(QmInputWriter, '_get_molecule', staticmethod(unexpected_source_read))
    result, _ = await write_request(request, tmp_path)

    assert not result.is_success
    assert 'maxcore' in result.message.lower()
    assert not Path(request.output_path).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('mem,nproc,maxcore', [('4MB', 4, 1), ('5MB', 4, 1), ('512MB', 4, 128)])
async def test_orca_memory_keeps_budget_without_minimum_override(tmp_path, mem, nproc, maxcore):
    result, content = await write_request(request_for(tmp_path, mem=mem, nproc=nproc), tmp_path)

    assert result.is_success, result.message
    assert f'%maxcore {maxcore}\n' in content
    assert bool(result.warnings) == (mem == '5MB')


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['chk_name', 'rwf_name', 'fchk_name'])
async def test_orca_reports_gaussian_only_file_fields(tmp_path, field):
    request = request_for(tmp_path, **{field: 'GaussianOnly.dat'})

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert 'GaussianOnly.dat' not in content
    assert any(warning['field'] == field and warning['code'] == 'gaussian_only_field'
               for warning in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize('settings', [
    {},
    {'nproc': 8, 'mem': '16GB'},
])
async def test_explicit_native_resources_are_not_duplicated_by_defaults(tmp_path, settings):
    block = '%pal nprocs 8 end\n%maxcore 2048'
    request = request_for(tmp_path, orca_blocks=block, **settings)

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert block in content
    assert content.lower().count('%pal') == 1
    assert content.lower().count('%maxcore') == 1
    assert any(warning['code'] == 'native_resource_settings' for warning in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize('settings', [{'nproc': 4}, {'nproc': 8, 'mem': '8GB'}])
async def test_conflicting_explicit_resource_sources_refuse(tmp_path, settings):
    request = request_for(tmp_path, orca_blocks='%pal nprocs 8 end\n%maxcore 2048', **settings)

    result, _ = await write_request(request, tmp_path)

    assert not result.is_success
    assert 'conflict' in result.message.lower()
    assert not Path(request.output_path).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('settings,nprocs,maxcore', [
    ({'orca_blocks': '%pal nprocs 8 end'}, 8, 512),
    ({'keywords': 'PAL8'}, 8, 512),
    ({'orca_blocks': '%maxcore 2048'}, 4, 2048),
])
async def test_partial_native_resources_use_remaining_documented_defaults(tmp_path, settings, nprocs, maxcore):
    request = request_for(tmp_path, **settings)

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    simple, blocks = orca_directives(content)
    assert blocks['maxcore'] == [str(maxcore)]
    if 'keywords' in settings:
        assert 'pal8' in simple
        assert 'pal' not in blocks
    else:
        assert blocks['pal'] == ['nprocs', str(nprocs), 'end']


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,settings', [
    ('orca', {'keywords': 'GOAT'}),
    ('gaussian', {'keywords': 'IRCMax(HF/STO-3G//HF/STO-3G)'}),
    ('orca', {'keywords': 'TightSCF'}),
    ('orca', {'orca_blocks': '%scf MaxIter 42 end'}),
    ('gaussian', {'end_setting': 'B 1 2 F'}),
])
async def test_native_declaration_does_not_acquire_implicit_opt(tmp_path, engine, settings):
    source = tmp_path / 'source.xyz'
    source.write_text(XYZ)
    request = QmInputWriter_input_schema(engine=engine, method='HF', basis_set='STO-3G', charge=0,
        source_type='xyz_file', source_value=str(source),
        output_path=str(tmp_path / ('job.inp' if engine == 'orca' else 'job.gjf')), **settings)

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert result.interpreted_intent['tasks'] == []
    header = next(line for line in content.splitlines() if line.startswith(('!', '#p')))
    assert ' opt ' not in header.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,task_type,keywords,token', [
    ('orca', [{'opt': 'ts'}], 'OptTS', 'optts'),
    ('gaussian', [{'opt': 'TS,CalcFC'}], 'Opt=(TS,CalcFC)', 'opt=(ts,calcfc)'),
])
async def test_identical_task_tokens_are_serialized_once(tmp_path, engine, task_type, keywords, token):
    request = request_for(tmp_path, engine, task_type=task_type, keywords=keywords)

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert content.lower().count(token) == 1
    assert result.calculation.keywords.lower().count(token) == 1


@pytest.mark.asyncio
async def test_different_native_task_suboptions_are_preserved_without_merging(tmp_path):
    request = request_for(tmp_path, 'gaussian', task_type=[{'opt': 'TS'}], keywords='Opt=(TS,CalcFC)')

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert 'opt=TS' in content and 'Opt=(TS,CalcFC)' in content
    assert 'opt=TS' in result.calculation.keywords and 'Opt=(TS,CalcFC)' in result.calculation.keywords


@pytest.mark.asyncio
async def test_orca_task_with_extra_parameters_is_not_partially_deduplicated(tmp_path):
    request = request_for(tmp_path, task_type=[{'opt': 'ts,CalcFC'}], keywords='OptTS')

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert content.lower().count('optts') == 2
    assert 'OptTS CalcFC' in content
    assert result.warnings


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,task_type,keywords,tasks', [
    ('gaussian', [{'opt': 'TS'}], '! Opt is only a comment', ['ts_opt']),
    ('gaussian', [{'freq': None}], '! Freq', ['frequency']),
    ('orca', [{'opt': 'TS'}], '# OptTS is only a comment #', ['ts_opt']),
])
async def test_task_words_inside_comments_do_not_remove_requested_task(tmp_path, engine, task_type, keywords, tasks):
    request = request_for(tmp_path, engine, task_type=task_type, keywords=keywords)

    result, _ = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert result.interpreted_intent['tasks'] == tasks


@pytest.mark.asyncio
async def test_distinct_quoted_task_values_are_never_deduplicated(tmp_path):
    request = request_for(tmp_path, 'gaussian', task_type=[{'FutureTask': '"Case.File"'}],
        keywords='FutureTask="case.file"')

    result, content = await write_request(request, tmp_path)

    assert result.is_success, result.message
    assert 'futuretask="Case.File"' in content and 'FutureTask="case.file"' in content
