"""Final electronic energy reaches evidence consumers without becoming SCF energy."""
from pathlib import Path

import pytest

from cloudra.benchmark.barrier_evidence import HARTREE_TO_KCAL_MOL, _engine_energy_kcal
from cloudra.dag.fact_adapters import log_parser_facts
from cloudra.dag.models import GraphRef


@pytest.mark.parametrize(('engine', 'text'), [
    ('gaussian', 'Gaussian 16\n # MP2/STO-3G\nSCF Done: E(RHF) = -75.00000000 A.U.\n'
     'E2 = -0.1D+00 EUMP2 = -0.7510000000D+02\nNormal termination\n'),
    ('orca', 'ORCA VERSION 6\n! MP2 STO-3G\nTotal Energy : -75.00000000 Eh\n'
     'FINAL SINGLE POINT ENERGY -75.10000000\nORCA TERMINATED NORMALLY\n'),
])
def test_barrier_reader_uses_final_method_energy(tmp_path, monkeypatch, engine, text):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    path = tmp_path / f'{engine}.out'
    path.write_text(text)
    energy, error = _engine_energy_kcal(tmp_path, path.name)
    assert not error, error
    assert energy == pytest.approx(-75.1 * HARTREE_TO_KCAL_MOL)


def test_electronic_energy_without_scf_is_still_a_measured_energy_fact():
    ref = GraphRef(ref_type='tool_result', ref_id='external', content_hash='sha256:external')
    facts = log_parser_facts({'result': {'is_success': True, 'scf_energy_hartree': None,
        'electronic_energy_hartree': -75.1}}, ref)
    energy = next(item for item in facts if item.check == 'energy')
    assert energy.details == {'electronic_energy_hartree': -75.1}


def test_benchmark_probe_checks_native_engine_despite_mislabeled_evidence(tmp_path):
    from cloudra.benchmark.integrity import EvidenceFile
    from cloudra.benchmark.selfconsistency import _LogProbe

    path = tmp_path / 'mislabeled.out'
    path.write_bytes((Path(__file__).parent / 'fixtures/xtb/ts_hess_xtb.out').read_bytes())
    probe = _LogProbe(tmp_path, {path.name: EvidenceFile(path=path.name, kind='orca')})
    assert probe.n_imag(path.name) is None


@pytest.mark.parametrize(('engine', 'fixture', 'later_sp'), [
    ('gaussian', 'gaussian/water_opt_freq_g16.out',
     'Link1: Proceeding to internal job step number 3.\n # HF/STO-3G SP\n'
     'Standard orientation:\n -----\n Center Atomic Atomic Coordinates\n -----\n'
     '1 8 0 0.0 0.0 0.0\n2 1 0 0.0 0.0 8.0\n3 1 0 0.0 8.0 0.0\n -----\n'
     'SCF Done: E(RHF) = -74.0 A.U.\nNormal termination of Gaussian 16\n'),
    ('orca', 'orca/co2_freq_orca42.out',
     'JOB NUMBER 2\n! HF STO-3G SP\nCARTESIAN COORDINATES (ANGSTROEM)\n'
     '----------------\nC 0 0 0\nO 0 0 8\nO 0 0 -8\n\n'
     'FINAL SINGLE POINT ENERGY -184.0\nORCA TERMINATED NORMALLY\n'),
])
def test_dag_does_not_attach_prior_optimization_to_a_different_sp_geometry(
    tmp_path, monkeypatch, engine, fixture, later_sp,
):
    from cloudra.dag.file_science import _optimization_converged

    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    path = tmp_path / 'different-geometry.out'
    path.write_text((Path(__file__).parent / 'fixtures' / fixture).read_text() + later_sp)
    assert _optimization_converged(str(path), engine) is None


@pytest.mark.asyncio
async def test_delivery_energy_matches_the_bound_final_method(tmp_path):
    import asyncio
    import json

    from cloudra.dag.delivery_artifact import prepare_delivery_artifact
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import AttachRef, GraphActor, MutationBatch
    from tests.test_dag_delivery_artifact import controller, graph

    c = await controller(tmp_path)

    def bind():
        original = Path(__file__).parent / 'fixtures/gaussian/water_opt_freq_g16.out'
        text = original.read_text()
        text = text.replace('Normal termination',
            'E2 = -0.1D+00 EUMP2 = -0.750659011806D+02\n Normal termination')
        log = tmp_path / 'correlated.out'
        log.write_text(text)
        snap = snapshot_evidence_file(log, tmp_path)
        ref = c.store.register_evidence('s1', 'method energy', snap.model_dump(mode='json'), source_type='file')
        result = DagEngine(c.store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
            actor_id='harness', base_revisions=c.store.load_bundle().revisions,
            rationale='bind final method energy independently of SCF',
            operations=[AttachRef(op='attach_ref', graph='delivery', target_type='node', target_id='r', ref=ref)]))
        assert result.accepted
        assert snap.final_energy_hartree == pytest.approx(-75.0659011806)
        return log, snap

    log, snap = await asyncio.to_thread(bind)
    document = graph()
    document['nodes'][0]['properties'] = {'energy_hartree': snap.final_energy_hartree, 'evidence_log': str(log)}
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))
    snapshot = await asyncio.to_thread(c.store.load_snapshot)
    report = await asyncio.to_thread(c.delivery_report)
    artifact = await asyncio.to_thread(prepare_delivery_artifact, c.store, snapshot.delivery, report, tmp_path)
    assert artifact.scientific_checks['R']['geometry']['status'] == 'passed'
