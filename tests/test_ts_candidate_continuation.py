
import pytest

from tests.test_ts_pipeline_driver import waiting_process


def test_validation_budget_shortfall_blocks_before_ts_submission(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage, configure_budget
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_process import TsProcessRecord, _submit_step

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    from cloudra.tools.core.ts_inputs import TsExecutionLimits
    record.input.execution.limits = TsExecutionLimits(source="explicit_user", max_compute_actions=6)
    configure_budget(db, process_id=pid, project_id="project", owner_id="owner", budget=ExplorationBudget(source="explicit_user", max_compute_actions=6))
    path = tmp_path / "new-ts.inp"
    path.write_text("! OptTS B3LYP def2SVP D3BJ\n* xyz 0 1\nO 0 0 0\n*\n")
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    error, job = _submit_step(record, "ts_opt", str(path), "orca")
    assert job == -1
    assert "budget" in error
    assert budget_usage(db, pid).compute_actions == 0
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1












@pytest.mark.parametrize("role", ["reactant", "product"])
def test_formal_endpoint_rejects_mirrored_declared_stereochemistry(tmp_path, monkeypatch, role):
    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_process import TsProcessRecord

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    smiles = "F[C@](Cl)(Br)I"
    record.input.reaction.reactant_smiles = smiles
    record.input.reaction.product_smiles = smiles
    graph = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(graph, randomSeed=11) == 0
    positions = graph.GetConformer().GetPositions().tolist()
    symbols = [a.GetSymbol() for a in graph.GetAtoms()]
    mol_path = tmp_path / "endpoint.mol"
    mol_path.write_text(Chem.MolToMolBlock(graph))
    monkeypatch.setattr(ts_process, "_read_built_xyz", lambda *args: (symbols, positions, "", str(mol_path)))
    remap = list(reversed(range(len(symbols)))) if role == "product" else list(range(len(symbols)))
    from cloudra.tools.core.molecule import renumber_atoms
    from cloudra.tools.core.reaction_state import ReactionStructures
    record.structures = ReactionStructures(reactant=renumber_atoms(graph, [remap.index(i) for i in range(len(remap))]), product=graph, product_to_reactant=tuple(remap))

    def ordered(points):
        return (
            [symbols[remap.index(i)] for i in range(len(symbols))],
            [points[remap.index(i)] for i in range(len(symbols))],
        )

    assert ts_process._endpoint_identity_error(record, role, ordered(positions)) == ""
    mirrored = [[-p[0], p[1], p[2]] for p in positions]
    assert "stereochemistry" in ts_process._endpoint_identity_error(record, role, ordered(mirrored))

pytestmark = pytest.mark.usefixtures("ts_producer_authority")
