"""J/L 族：L1 为 HCNO 与降冰片烯的两面 [3+2] 环加成。

2026-10-18：用户授权替换旧 Beckmann 题。本轮结果已交付，
正式 Gold 回填两面立体产物和接触体起算的逐步电子能垒，不新增优势面评分。
"""

TASKS = {
    # 原报告 11.89/6.95 相对分离单体；本参考 16.18/10.77 各减本通道稳定接触体。
    # 入口构象不同，不将两逐步能垒之差作为共同参考的面选择性。
    "L1": {
        "name_en": "formonitrile oxide + norbornene [3+2] cycloaddition: determine both facial pathways",
        "conditions_en": "gas phase, neutral singlet HCNO plus unsubstituted norbornene; investigate "
        "approach from both faces of the C4=C5 bond relative to the methano bridge C10 in "
        "the atom mapping; establish each product's stereochemical relationship to that "
        "bridge from actual 3D geometries and give explicit stereochemical SMILES rather "
        "than relying on an unverified endo/exo or syn/anti name; use each pathway's own "
        "stable contact minimum as the energy reference for its elementary-step "
        "barrier; record the energy difference between the distinct contact conformers "
        "separately and do not treat the difference between their substrate-specific "
        "barriers as a common-reference facial selectivity; investigate C-C and C-O bond "
        "formation and the identity of both endpoints; do not substitute benzonitrile oxide "
        "or substituted norbornene; reference DOI 10.1039/FT9938900029",
        "anchor": "barrier",
        "score_selectivity": False,
        "mapped_reactants": "[CH:1]#[N+:2][O-:3].[CH:4]1=[CH:5][CH:6]2[CH2:7][CH2:8][CH:9]1[CH2:10]2",
        "steps": [],
        "gold_graph": {
            "nodes": [
                {
                    "id": "HL1_RC_endo",
                    "role": "reactant",
                    "smiles": ["C#[N+][O-].C1=CC2CCC1C2"],
                    "properties": {
                        "energy_hartree": -441.019350272,
                        "evidence_log": "gold_compute/queue_20261018/evidence/ts_runs/ts_0036/jobs/declaration_0009/reactant_frequency/reactant_frequency.log",
                        "reference_note": "this channel's own stable contact "
                        "minimum; not a separated-monomer "
                        "reference",
                    },
                },
                {
                    "id": "HL1_RC_exo",
                    "role": "reactant",
                    "smiles": ["C#[N+][O-].C1=CC2CCC1C2"],
                    "properties": {
                        "energy_hartree": -441.020095712,
                        "evidence_log": "gold_compute/queue_20261018/evidence/ts_runs/ts_0037/jobs/declaration_0001/reactant_frequency/reactant_frequency.log",
                        "reference_note": "this channel's own stable contact "
                        "minimum; not a separated-monomer "
                        "reference",
                    },
                },
                {
                    "id": "HL1_TS_endo",
                    "role": "transition_state",
                    "smiles": [],
                    "properties": {
                        "energy_hartree": -441.002183678,
                        "evidence_log": "gold_compute/queue_20261018/evidence/ts_runs/ts_0036/jobs/declaration_0006/frequency/frequency.log",
                    },
                },
                {
                    "id": "HL1_TS_exo",
                    "role": "transition_state",
                    "smiles": [],
                    "properties": {
                        "energy_hartree": -440.9943166,
                        "evidence_log": "gold_compute/queue_20261018/evidence/ts_runs/ts_0037/jobs/declaration_0001/frequency/frequency.log",
                    },
                },
                {
                    "id": "HL1_P_endo",
                    "role": "product",
                    "smiles": ["C1=NO[C@H]2[C@@H]3CC[C@@H](C3)[C@@H]12"],
                    "properties": {
                        "energy_hartree": -441.09827373,
                        "evidence_log": "gold_compute/queue_20261018/evidence/results/HL1/jobs/HL1_armend_relax_ts0036.log",
                    },
                },
                {
                    "id": "HL1_P_exo",
                    "role": "product",
                    "smiles": ["C1=NO[C@@H]2[C@@H]3CC[C@@H](C3)[C@H]12"],
                    "properties": {
                        "energy_hartree": -441.095689377,
                        "evidence_log": "gold_compute/queue_20261018/evidence/ts_runs/ts_0037/jobs/declaration_0001/product_frequency/product_frequency.log",
                    },
                },
            ],
            "edges": [
                {
                    "id": "e_exo",
                    "from": "HL1_RC_exo",
                    "to": "HL1_P_exo",
                    "via": "HL1_TS_exo",
                    "bond_changes": {"break": [[1, 2], [4, 5]], "form": [[1, 4], [3, 5]]},
                    "channel": "exo",
                    "barrier_kcal_mol": 16.18,
                    "step_type": "concerted_[3+2]_cycloaddition",
                    "favored": None,
                },
                {
                    "id": "e_endo",
                    "from": "HL1_RC_endo",
                    "to": "HL1_P_endo",
                    "via": "HL1_TS_endo",
                    "bond_changes": {"break": [[1, 2], [4, 5]], "form": [[1, 4], [3, 5]]},
                    "channel": "endo",
                    "barrier_kcal_mol": 10.77,
                    "step_type": "concerted_[3+2]_cycloaddition",
                    "favored": None,
                },
            ],
        },
    },
}
