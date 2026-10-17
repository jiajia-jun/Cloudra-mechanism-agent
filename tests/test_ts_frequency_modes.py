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
    if has_displacements:
        assert report['modes'][0]['top_displaced_atoms'][0] == {
            'atom': 1, 'element': 'O', 'fraction': 1.0,
        }
        assert report['modes'][0]['watch_atom_fraction'] == 0
    else:
        assert report['modes'] is None  # 无位移证据不能伪装成反应中心占比为零。
    assert reloaded.terminal != 'verified'
