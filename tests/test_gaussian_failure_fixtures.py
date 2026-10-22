"""Integrity checks for the run4 failure fixtures.

These do not assert the *buggy* behaviour; they pin what each fixture is so a
later fix can rely on the shape (and so nobody trims the evidence away)."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / 'fixtures' / 'gaussian_failures'


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def test_illegal_routes_are_preserved_verbatim():
    assert '#p opt=TS B3LYP/def2SVP EmpiricalDispersion=GD3BJ\n' in _read('opt_ts_without_hessian.gjf')
    assert '#p irc B3LYP/def2SVP empiricaldispersion=gd3bj\n' in _read('irc_without_hessian.gjf')
    assert _read('opt_ts_bare_calcfc.gjf').splitlines()[3].endswith('CalcFC')
    assert _read('opt_ts_modredundant.gjf').splitlines()[3].endswith('ModRedundant')


def test_irc_l1_log_carries_the_force_constant_error():
    log = _read('irc_l1_force_constant_error.log')
    assert 'ReadCartesianFC, FCCards, or CalcFC with IRC' in log


def test_l123_log_has_frames_but_no_summary_table():
    log = _read('irc_l123_no_summary.log')
    assert log.count('CURRENT STRUCTURE') >= 2
    assert log.count('Point Number') >= 4
    assert 'Path Number:   1' in log
    assert 'Delta-x Convergence NOT Met' in log
    assert 'Error termination via Lnk1e' in log
    assert 'Summary of reaction path following' not in log
    assert '# --- fixture:' in log, 'trimmed fixture must keep its marker'


def test_archived_sidecar_records_no_binding():
    sidecar = json.loads(_read('irc_endpoints_null_binding.json'))
    # The archive wrote no binding at all: that is what "atom binding absent" means.
    assert 'atom_binding' not in sidecar
    assert sidecar['endpoints']['forward']['converged'] is False
    assert sidecar['endpoints']['backward']['converged'] is False


def test_checkpoint_fixture_declares_a_path_outside_the_task_workspace():
    text = _read('chk_outside_workspace.gjf')
    chk = next(line for line in text.splitlines() if line.startswith('%chk='))
    assert '/sandboxes/jobs/' in chk, 'the missing <task>/<batch> level is the defect'
    log = _read('chk_outside_workspace_nterr.log')
    assert 'Restoring state from the checkpoint file' in log
    assert 'Error termination in NtrErr' in log
    # The archived state JSON was not checked in. Verify the unchanged native
    # failure log instead of fabricating a historical state receipt.
    from cloudra.tools.core.qm_log_facts import read_qm_log

    facts = read_qm_log(FIXTURES / 'chk_outside_workspace_nterr.log')
    assert facts.normal_termination is False
    assert facts.electronic_energy_hartree is None
    assert json.loads(_read('calc_chk_outside_workspace.exit.json'))['exit_code'] == 1


def test_delivered_graphs_carry_no_barrier():
    for name in ('mechanism_graph_missing_barrier.json', 'mechanism_graph_ts_unbound.json'):
        data = json.loads(_read(name))
        assert data['edges'], 'both fixtures are real deliveries with step edges'
        assert 'barrier_kcal_mol' not in json.dumps(data)
