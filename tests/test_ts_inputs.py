import pytest
from pydantic import ValidationError


def input_payload():
    return {
        "reaction": {
            "reactant_smiles": "CCO", "product_smiles": "CCO",
            "charge": 0, "multiplicity": 1,
            "selected_candidate": None, "reaction_center": [],
        },
        "conformers": {
            "reactant": {"kind": "file", "xyz_path": "reactant.xyz"},
            "product": {"kind": "file", "xyz_path": "product.xyz"},
            "guidance": {"ring_order": [1, 2, 3], "distance_filters": []},
        },
        "guess": {
            "kind": "scan",
            "calculation": {"engine": "orca", "method": "GFN2-xTB", "basis_set": "", "keywords": ""},
            "scans": [{"atoms": [0, 1], "scan_end": 2.0, "scan_steps": 7}],
            "freeze": [],
        },
        "ts_optimization": {
            "engine": "orca", "method": "b3lyp", "basis_set": "def2svp", "keywords": "D3BJ",
        },
        "execution": {"cpus": 2, "memory_mb": 2048},
    }


def test_input_changes_cover_every_input_group():
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes

    current = TsInput.model_validate(input_payload())
    changes = TsInputChanges.model_validate({
        "reaction": {"charge": -1},
        "conformers": {"guidance": {"ring_order": []}},
        "guess": {"kind": "provided", "xyz_path": "candidate.xyz", "evidence_refs": ["scan.log"]},
        "ts_optimization": {"replace": {"engine": "gaussian", "method": "b3lyp", "basis_set": "def2svp", "keywords": ""}},
        "verification": {"frequency": {"engine": "gaussian", "method": "b3lyp", "basis_set": "def2svp", "keywords": ""}},
        "execution": {"cpus": 4},
    })
    updated = apply_input_changes(current, changes)
    assert updated.reaction.charge == -1
    assert updated.reaction.product_smiles == "CCO"
    assert updated.conformers.guidance.ring_order == []
    assert updated.guess.kind == "provided"
    assert updated.ts_optimization.engine == "gaussian"
    assert updated.verification.frequency.engine == "gaussian"
    assert updated.execution.cpus == 4
    assert updated.execution.memory_mb == 2048
    assert current.reaction.charge == 0
    with pytest.raises(ValidationError):
        TsInputChanges.model_validate({"pretend_verified": True})


def test_omitted_null_and_empty_list_have_distinct_effects():
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes

    current = TsInput.model_validate(input_payload())
    updated = apply_input_changes(current, TsInputChanges.model_validate({
        "guess": None, "reaction": {"reaction_center": [], "selected_candidate": None},
    }))
    assert updated.guess is None
    assert updated.reaction.selected_candidate is None
    assert updated.reaction.reaction_center == []
    assert updated.ts_optimization.method == "b3lyp"
    with pytest.raises(ValidationError):
        apply_input_changes(current, TsInputChanges.model_validate({"reaction": {"reactant_smiles": None}}))


def test_method_replacement_is_explicit_and_keyword_patch_retains_identity():
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes

    current = TsInput.model_validate(input_payload())
    updated = apply_input_changes(current, TsInputChanges.model_validate({
        "guess": {"kind": "xtb_path", "method": "GFN2-xTB"},
        "ts_optimization": {"replace": {"engine": "orca", "method": "b97-3c", "basis_set": "", "keywords": ""}},
    }))
    assert updated.ts_optimization.keywords == ""
    assert updated.guess.kind == "xtb_path"
    assert "scans" not in updated.guess.model_dump()
    patched = apply_input_changes(current, TsInputChanges.model_validate({"ts_optimization": {"keywords": "TightSCF"}}))
    assert patched.ts_optimization.method == current.ts_optimization.method
    assert patched.ts_optimization.keywords == 'TightSCF'
    with pytest.raises(ValidationError):
        TsInput.model_validate(dict(input_payload(), guess={"kind": "xtb_path", "method": "GFN2-xTB", "scans": []}))


def test_method_is_not_inherited_from_another_group():
    from cloudra.tools.core.ts_inputs import TsInput

    current = TsInput.model_validate(input_payload())
    assert current.verification.frequency is None
    assert current.verification.irc is None
    assert current.verification.reactant_endpoint.optimization is None
    assert current.guess.calculation.method == "GFN2-xTB"


def test_switching_engine_preserves_bound_atom_identity():
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes, normalize_ts_input_atoms

    current = normalize_ts_input_atoms(TsInput.model_validate(input_payload()), atom_tables={})
    assert current.reaction.selected_candidate is None
    assert current.conformers.guidance.ring_order == [0, 1, 2]
    assert current.guess.scans[0].atoms == [0, 1]
    changed = apply_input_changes(current, TsInputChanges.model_validate({
        "ts_optimization": {"replace": {"engine": "gaussian", "method": "b3lyp", "basis_set": "def2svp", "keywords": ""}},
    }))
    assert changed.reaction.selected_candidate is None
    assert changed.guess.scans[0].atoms == [0, 1]


def test_revision_and_reason_are_required_for_mutation():
    from cloudra.tools.core.ts_inputs import TsResumeRequest

    request = TsResumeRequest.model_validate({
        "changes": {"reaction": {"charge": 1}}, "reason": "correct declared charge",
        "request_key": "revision-1", "expected_revision": 2,
    })
    assert request.expected_revision == 2
    with pytest.raises(ValidationError):
        TsResumeRequest.model_validate({"changes": {"reaction": {"charge": 1}}, "reason": " "})


def test_scan_numbering_belongs_to_scan_engine_and_checks_bound_range():
    from cloudra.tools.core.ts_inputs import TsInput, normalize_ts_input_atoms

    payload = input_payload()
    payload["guess"]["calculation"]["engine"] = "gaussian"
    payload["guess"]["scans"][0]["atoms"] = [1, 2]
    value = normalize_ts_input_atoms(TsInput.model_validate(payload), atom_tables={"reactant": ["C", "C", "O"]})
    assert value.guess.scans[0].atoms == [0, 1]
    payload["reaction"]["reaction_center"] = [[1, 4]]
    with pytest.raises(ValueError, match="bound atom table"):
        normalize_ts_input_atoms(TsInput.model_validate(payload), atom_tables={"reactant": ["C", "C", "O"]})


@pytest.mark.parametrize("engine,atoms", [("orca", [0, 1]), ("gaussian", [1, 2])])
def test_resume_scan_replacement_can_omit_default_freeze(engine, atoms):
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes, normalize_ts_input_atoms

    changes = TsInputChanges.model_validate({"guess": {
        "kind": "scan", "calculation": {"replace": {"engine": engine, "method": "GFN2-xTB", "basis_set": "", "keywords": ""}},
        "scans": [{"atoms": atoms, "scan_end": 2.0, "scan_steps": 7}],
    }})
    normalized = normalize_ts_input_atoms(changes, atom_tables={"reactant": ["C", "O"]})
    assert normalized.guess.scans[0].atoms == [0, 1]
    assert normalized.guess.freeze is None
    updated = apply_input_changes(TsInput.model_validate(input_payload()), normalized)
    assert updated.guess.freeze == []
    assert updated.guess.scans[0].atoms == [0, 1]


def test_xtb_scan_uses_minimal_explicit_scientific_input_and_one_based_atoms():
    from cloudra.tools.core.ts_inputs import TsInput, normalize_ts_input_atoms

    payload = input_payload()
    payload["guess"] = {
        "kind": "scan",
        "calculation": {"engine": "xtb", "method": "GFN2-xTB", "basis_set": ""},
        "scans": [{"coord_type": "bond", "atoms": [1, 2], "scan_start": 1.0,
                   "scan_end": 1.3, "scan_steps": 3}],
        "force_constant": 0.5,
    }
    normalized = normalize_ts_input_atoms(TsInput.model_validate(payload), atom_tables={"reactant": ["C", "C", "O"]})
    assert normalized.guess.scans[0].atoms == [0, 1]
    assert normalized.guess.mode is None
    assert normalized.guess.calculation.keywords == ""


def test_xtb_scan_requires_force_and_two_coordinate_mode():
    from cloudra.tools.core.ts_inputs import TsInput

    payload = input_payload()
    payload["guess"] = {
        "kind": "scan", "calculation": {"engine": "xtb", "method": "GFN2-xTB", "basis_set": ""},
        "scans": [{"atoms": [1, 2], "scan_start": 1.0, "scan_end": 1.3, "scan_steps": 3}],
    }
    with pytest.raises(ValidationError, match="force_constant"):
        TsInput.model_validate(payload)
    payload["guess"]["force_constant"] = 0.5
    payload["guess"]["mode"] = "sequential"
    with pytest.raises(ValidationError, match="one-coordinate"):
        TsInput.model_validate(payload)
    payload["guess"].pop("mode")
    payload["guess"]["scans"].append({"atoms": [2, 3], "scan_start": 1.0, "scan_end": 1.3, "scan_steps": 3})
    with pytest.raises(ValidationError, match="mode"):
        TsInput.model_validate(payload)
