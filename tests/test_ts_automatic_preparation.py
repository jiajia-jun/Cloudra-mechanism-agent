"""Missing mechanical inputs use the existing structure and mapping algorithms."""

import pytest

from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsStartRequest, load_record, start

pytestmark = pytest.mark.usefixtures('ts_producer_authority', 'rdkit_chemistry')


def _start(tmp_path, **groups):
    return start(TsStartRequest(request_key='automatic-preparation', workspace_dir=str(tmp_path),
        owner_conversation_id='project', owner_session_id='owner', input=TsInput(
            reaction=dict(reactant_smiles='[F-].CCl', product_smiles='CF.[Cl-]', charge=-1, multiplicity=1),
            **groups)))


def test_omitted_sources_mapping_and_center_are_prepared_before_requesting_guess(tmp_path):
    from cloudra.tools.core.reaction_state import source_snapshot
    from cloudra.tools.core.ts_process import _active_reaction_center

    record = _start(tmp_path)

    assert record.blocked.stage == 'guess'
    assert record.blocked.needs == ['guess']
    assert record.structures.product_to_reactant is not None
    assert set(_active_reaction_center(record)) == {(0, 1), (1, 2)}
    # Keep the user's original declaration; generated defaults are actual source facts.
    assert record.input.conformers.reactant is None
    assert record.input.reaction.reaction_center == []
    for role in ('reactant', 'product'):
        source = source_snapshot(getattr(record.structures, role))
        assert source['kind'] == 'generate'
        assert source['generation'] == 'ETKDGv3'
        assert source['seed'] == 42
    restored = load_record(str(tmp_path), record.run_id)
    assert _active_reaction_center(restored) == _active_reaction_center(record)
    assert source_snapshot(restored.structures.reactant) == source_snapshot(record.structures.reactant)


def test_explicit_seed_is_used_and_missing_other_source_is_generated(tmp_path):
    from cloudra.tools.core.reaction_state import source_snapshot

    record = _start(tmp_path, conformers={'reactant': {'kind': 'generate', 'seed': 17}})

    assert record.blocked.stage == 'guess'
    assert source_snapshot(record.structures.reactant)['seed'] == 17
    assert source_snapshot(record.structures.product)['seed'] == 42


def test_explicit_missing_file_is_reported_instead_of_replaced(tmp_path):
    record = _start(tmp_path, conformers={'reactant': {'kind': 'file', 'xyz_path': 'missing.xyz'}})

    assert record.blocked.failure_class == 'conformer_source_invalid'
    assert record.blocked.needs == ['conformers.reactant']
    assert record.structures.reactant is None


def test_reaction_center_uses_bound_full_atom_map_including_transferred_hydrogen():
    from rdkit import Chem

    from cloudra.tools.core.reaction_state import ReactionStructures, mapped_reaction_center

    # O-H + F -> O + H-F, with explicit H; mapping is product row -> reactant row.
    left = Chem.MolFromSmiles('[O-][H].[F-]', sanitize=False)
    right = Chem.MolFromSmiles('[O-].[H][F-]', sanitize=False)
    state = ReactionStructures(reactant=left, product=right, product_to_reactant=(0, 1, 2))

    assert set(mapped_reaction_center(state)) == {(0, 1), (1, 2)}
    # Clearing the correspondence must also stop use of its derived centre.
    state.product_to_reactant = None
    assert mapped_reaction_center(state) == []


def test_explicit_center_takes_precedence_over_automatic_center(tmp_path):
    from cloudra.tools.core.ts_process import _active_reaction_center

    record = _start(tmp_path)
    record.input.reaction.reaction_center = [(0, 1)]

    assert _active_reaction_center(record) == [(0, 1)]


def test_species_revision_regenerates_omitted_sources(tmp_path):
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_process import resume

    record = _start(tmp_path)
    request = TsResumeRequest(changes={'reaction': {
        'reactant_smiles': 'N', 'product_smiles': 'N', 'charge': 0,
    }}, reason='Revise the declared reaction species', request_key='change-species',
        expected_revision=record.revision)

    revised = resume(record, request)

    assert revised.blocked.stage == 'guess'
    for role in ('reactant', 'product'):
        assert [atom.GetSymbol() for atom in getattr(revised.structures, role).GetAtoms()] == ['N', 'H', 'H', 'H']
    assert revised.input.conformers.reactant is None


def test_intramolecular_preparation_reports_derived_center(tmp_path):
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.tools.core.ts_state_view import inspect_process

    record = start(TsStartRequest(request_key='intramolecular', workspace_dir=str(tmp_path),
        owner_conversation_id='project', owner_session_id='owner', input=TsInput(
            reaction=dict(reactant_smiles='C=CO', product_smiles='CC=O', charge=0, multiplicity=1))))
    view = inspect_process(pipeline_database(), project_id='project', run_id=record.run_id,
                           workspace_dir=str(tmp_path), can_write=True)

    assert record.blocked.stage == 'guess'
    assert 'automatically derived' in record.stage_record('assemble').detail
    assert 'automatically derived' in view.message
