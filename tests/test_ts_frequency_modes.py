"""Frequency diagnostics describe motion without inventing a scientific cutoff."""

import pytest

from cloudra.tools.core.mode_analysis import imaginary_mode_summary


def test_rotor_motion_reports_atoms_outside_the_reaction_center():
    summary = imaginary_mode_summary(
        [-70.0], [[[0, 0, 0], [0, 0, 0], [1, 0, 0], [-1, 0, 0]]],
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0]],
        ['O', 'C', 'H', 'H'], [[1, 2]],
    )[0]
    assert summary['top_displaced_atoms'][:2] == [
        {'atom': 3, 'element': 'H', 'fraction': 0.5},
        {'atom': 4, 'element': 'H', 'fraction': 0.5},
    ]
    assert summary['watch_atom_fraction'] == 0
    assert summary['heavy_atom_fraction'] == 0
    assert 'pseudo_saddle' not in summary


def test_reaction_center_atom_share_counts_shared_atoms_once():
    summary = imaginary_mode_summary(
        [-300.0], [[[1, 0, 0], [2, 0, 0], [0, 1, 0]]],
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]], ['O', 'C', 'H'], [[1, 2], [2, 3]],
    )[0]
    assert summary['watch_atom_fraction'] == pytest.approx(1.0)
    assert summary['top_displaced_atoms'][0] == {
        'atom': 2, 'element': 'C', 'fraction': pytest.approx(4 / 6),
    }


def test_no_watch_pairs_or_zero_motion_does_not_invent_a_fraction():
    summary = imaginary_mode_summary(
        [-10.0], [[[0, 0, 0], [0, 0, 0]]], [[0, 0, 0], [1, 0, 0]], ['C', 'H'],
    )[0]
    assert summary['watch_atom_fraction'] is None
    assert all(row['fraction'] is None for row in summary['top_displaced_atoms'])


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('has_displacements', [True, False])
@pytest.mark.parametrize('stage', ['refine', 'refine_without_irc', 'verdict'])
def test_frequency_motion_is_recorded_before_irc_and_visible_after_reload(
    tmp_path, monkeypatch, has_displacements, stage,
):
    from pathlib import Path
    from types import SimpleNamespace

    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_state_view import build_process_view
    from tests.test_log_parser import _GAUSSIAN_FREQ_WITH_DISPS
    from tests.test_ts_stage_inputs import record_fixture
    from tests.ts_fixtures import calculation_input

    value = calculation_input(reactant_smiles='O', product_smiles='O', charge=0,
                              method='HF/STO-3G', engine='gaussian', reaction_center=[(1, 2)])
    if stage == 'refine_without_irc':
        value.verification.irc = None
    record = record_fixture(tmp_path, input=value)
    step = ts_process.TsJobStep(purpose='frequency', job_id=17,
        input_path=str(tmp_path / 'frequency.gjf'), state='done',
        actual_calculation=value.verification.frequency)
    record.job_steps.append(step)
    log = Path(ts_process._refinement_log_path(record, step))
    log.parent.mkdir(parents=True, exist_ok=True)
    water_log = _GAUSSIAN_FREQ_WITH_DISPS.replace('1          6', '1          8').replace('1   6', '1   8')
    log.write_text(water_log if has_displacements else 'frequency without mode vectors')
    monkeypatch.setattr(ts_process, '_step_state', lambda *_: 'done')
    monkeypatch.setattr('cloudra.dag.evidence_ingest.snapshot_evidence_file', lambda *_, **__: SimpleNamespace(
        frequencies=[-294.67, 289.5, 458.1], imaginary_frequencies=[-294.67]))
    monkeypatch.setattr(ts_process, '_write_irc_input', lambda *_: ('fixture stops before real compute', ''))
    result = ts_process._verdict(record) if stage == 'verdict' else ts_process._refine(record)
    if stage == 'refine':
        assert result.blocked.failure_class == 'irc_input_failed'
    elif stage == 'refine_without_irc':
        assert result.blocked.needs == ['verification.irc']
    else:
        assert result.terminal == 'candidate_only'  # 组成报告不能代替 IRC 证明。
    # 组成信息是独立记录的事实，后续 IRC 输入失败也不能把它丢掉。
    reloaded = ts_process.TsProcessRecord.model_validate_json(result.model_dump_json())
    view = build_process_view(reloaded.model_dump(mode='json'), [], can_write=False)
    report = view.frequency_analysis
    assert report['job_id'] == 17 and report['source_input_revision'] == 1
    assert report['reaction_center_pairs'] == [[2, 3]]  # 对外原子编号始终从 1 开始。
    assert report['mode_alignment']['status'] == ('misaligned' if has_displacements else 'missing')
    assert report['mode_alignment']['aligned'] is (False if has_displacements else None)
    if has_displacements:
        assert report['modes'][0]['top_displaced_atoms'][0] == {
            'atom': 1, 'element': 'O', 'fraction': 1.0,
        }
        assert report['modes'][0]['watch_atom_fraction'] == 0
    else:
        assert report['modes'] is None  # 无位移证据不能伪装成反应中心占比为零。
    assert reloaded.terminal != 'verified'


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('alignment', ['aligned', 'misaligned', 'undecidable', 'missing'])
@pytest.mark.parametrize('imaginary_count', [1, 0, 2])
def test_mode_diagnostic_does_not_replace_the_existing_one_imaginary_gate(
    tmp_path, monkeypatch, alignment, imaginary_count,
):
    from pathlib import Path
    from types import SimpleNamespace

    from cloudra.tools.core import ts_process
    from tests.test_log_parser import _GAUSSIAN_FREQ_WITH_DISPS
    from tests.test_ts_stage_inputs import record_fixture
    from tests.ts_fixtures import calculation_input

    value = calculation_input(reactant_smiles='O', product_smiles='O', charge=0,
        method='HF/STO-3G', engine='gaussian',
        reaction_center=[(1, 2)] if alignment == 'misaligned' else [(0, 1)])
    record = record_fixture(tmp_path, input=value)
    step = ts_process.TsJobStep(purpose='frequency', job_id=17,
        input_path=str(tmp_path / 'frequency.gjf'), state='done',
        actual_calculation=value.verification.frequency)
    record.job_steps.append(step)
    log = Path(ts_process._refinement_log_path(record, step))
    log.parent.mkdir(parents=True, exist_ok=True)
    text = _GAUSSIAN_FREQ_WITH_DISPS.replace('1          6', '1          8').replace('1   6', '1   8')
    if alignment == 'undecidable':
        text = text.replace('1   8     1.00', '1   8     0.00')
        text = text.replace('2   1     0.00', '2   1     1.00')
        text = text.replace('3   1     0.00', '3   1    -1.00')
    if alignment == 'missing':
        text = text[:text.index('  Atom  AN')] + ' Normal termination of Gaussian 16\n'
    frequencies = {
        0: [294.67, 289.5, 458.1],
        1: [-294.67, 289.5, 458.1],
        2: [-294.67, -289.5, 458.1],
    }[imaginary_count]
    text = text.replace('-294.6700', '294.6700') if imaginary_count == 0 else text
    text = text.replace('289.5000', '-289.5000') if imaginary_count == 2 else text
    log.write_text(text)
    monkeypatch.setattr(ts_process, '_step_state', lambda _, current: current.state)
    monkeypatch.setattr('cloudra.dag.evidence_ingest.snapshot_evidence_file', lambda *_, **__: SimpleNamespace(
        frequencies=frequencies, imaginary_frequencies=[f for f in frequencies if f < 0]))
    monkeypatch.setattr(ts_process, '_write_irc_input', lambda *_: ('', str(tmp_path / 'irc.gjf')))
    submitted = []

    def submit(_, purpose, *_args):
        submitted.append(purpose)
        return '', 18

    monkeypatch.setattr(ts_process, '_submit_step', submit)
    result = ts_process._refine(record)
    diagnostic = step.frequency_analysis['mode_alignment']
    assert diagnostic['status'] == (alignment if imaginary_count else 'missing')
    if imaginary_count == 1:
        assert submitted == ['irc']
        assert result.waiting_for == 'job:18'
        assert result.job_steps[-1].purpose == 'irc'
        assert result.stage_record('refine').status == 'waiting'
        assert result.blocked is None
    else:
        assert submitted == []
        assert result.blocked.failure_class == 'wrong_mode'
    assert result.terminal != 'verified'


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('partial_cclib', [False, True])
@pytest.mark.parametrize('center,expected', [((0, 1), 'aligned'), ((1, 2), 'misaligned')])
def test_orca_report_keeps_native_mode_axis_and_one_based_center_and_frozen_charge(
    tmp_path, monkeypatch, partial_cclib, center, expected,
):
    from types import SimpleNamespace

    import cclib

    from cloudra.tools.Chemtool import ts_guess
    from cloudra.tools.core import ts_process
    from tests.test_log_parser import _orca_numfreq_log_with_disps
    from tests.test_ts_stage_inputs import record_fixture
    from tests.ts_fixtures import calculation_input

    value = calculation_input(reactant_smiles='O', product_smiles='O', charge=0,
        method='HF/STO-3G', engine='orca', reaction_center=[center])
    record = record_fixture(tmp_path, input=value)
    step = ts_process.TsJobStep(purpose='frequency', job_id=17,
        actual_calculation=value.verification.frequency, atom_binding={'charge': -1})
    # ORCA NORMAL MODES 包含 6 个零频；频率摘要里的振动轴已去掉它们。
    text = _orca_numfreq_log_with_disps().replace(
        '   0:      -294.67 cm**-1 ***imaginary mode***', '   0:       0.00 cm**-1')
    for mode in range(1, 6):
        text = text.replace(f'   {mode}:       {100.0 + mode:.2f} cm**-1',
                            f'   {mode}:       0.00 cm**-1')
    text = text.replace('   6:       106.00 cm**-1',
                        '   6:      -294.67 cm**-1 ***imaginary mode***')
    text = text.replace('     0      1.000000' + '  0.000000' * 5,
                        '     0      0.000000' + '  0.000000' * 5)
    text = text.replace('     0      0.000000  0.000000  0.000000\n',
                        '     0      1.000000  0.000000  0.000000\n')
    log = tmp_path / 'frequency.out'
    log.write_text(text)
    # cclib 可能只解析到去掉零频的频率轴，没得到位移；不能混用原生 3N 位移。
    parsed = SimpleNamespace(vibfreqs=[-294.67, 107.0, 108.0]) if partial_cclib else None
    monkeypatch.setattr(cclib.io, 'ccread', lambda *_: parsed)
    assess = ts_guess._assess_imag_mode_alignment
    received = []

    def assess_recorded_mode(*args, **kwargs):
        received.append(kwargs)
        return assess(*args, **kwargs)

    monkeypatch.setattr(ts_guess, '_assess_imag_mode_alignment', assess_recorded_mode)
    ts_process._record_frequency_analysis(record, step, str(log), SimpleNamespace(
        frequencies=[-294.67, 107.0, 108.0], imaginary_frequencies=[-294.67]))
    report = step.frequency_analysis
    assert report['reaction_center_pairs'] == [[atom + 1 for atom in center]]
    assert report['mode_alignment']['status'] == expected
    assert report['mode_alignment']['aligned'] is (expected == 'aligned')
    assert report['modes'][0]['frequency_cm'] == -294.67
    assert report['modes'][0]['top_displaced_atoms'][0] == {
        'atom': 1, 'element': 'C', 'fraction': 1.0,
    }
    assert report['modes'][0]['watch_atom_fraction'] == (1.0 if expected == 'aligned' else 0.0)
    assert received[0]['charge'] == -1  # 作业提交时的绑定，而不是当前声明的 0。
    assert received[0]['index_base'] == 1  # 管线报告的原子编号不跟随 ORCA 改成 0-based。
    standalone = ts_guess.TsGuess()._verify(ts_guess.TsGuess_input_schema(
        mode='verify', freq_log=str(log), watch_pairs=[list(center)], charge=-1))
    assert standalone.imag_mode_aligned is (expected == 'aligned')
    assert standalone.verification_status == 'candidate'
