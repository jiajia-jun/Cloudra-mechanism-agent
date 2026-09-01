"""H/I/J 族登记：笼状价异构（H7 pagodane / H8 propellane）+ 反常键与基态之争
（I2 硫代臭氧 / I8 磷宾）+ 重排小势能面（J6 甲氮烯 / J7 二硅烯）。

H7 为键重组无法从 SMILES 级映射差集推导的笼状价异构（显式 no_mapping）；
H7/H8/I8/J6/J7 是定稿风险登记的 6 条灰色地带题（wrongly_solve_penalty=medium、
evidence_strength=gray_zone）。
"""

TASKS = {
    # pagodane ⇌ dodecahedrane：2σ→2σ 二电子价异构，TS 必经 biradicaloid 区；
    # 笼状键重组无法做 SMILES 级原子映射（诚实声明 no_mapping，bond_changes 双空）
    "H7": {
        "name_zh": "Pagodane ⇌ Dodecahedrane 二电子异构",
        "name_en": "pagodane to dodecahedrane valence isomerization",
        "kind": "reaction",
        "question_en": (
            "Determine the mechanism and activation barrier of the direct valence "
            "isomerization of pagodane to dodecahedrane (C20H20 cage isomers)."
        ),
        "deliverable_en": (
            "the isomerization barrier in kcal/mol (transition state relative to the "
            "pagodane minimum)"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C1C2C3C4CC5C3C1C67C28C49C56C1CC9C2C8CC7C12"],
        "products": ["C12C3C4C5C1C6C7C2C8C3C9C4C1C5C6C2C7C8C9C12"],
        "reactant_accessible": True,
        "steps": [
            {
                "out": "C12C3C4C5C1C6C7C2C8C3C9C4C1C5C6C2C7C8C9C12",
                "type": "concerted two-sigma-bond reorganization of the C20H20 cage (2-sigma to 2-sigma valence isomerization)",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
                "no_mapping": True,
            },
        ],
        "wrongly_solve_penalty": "medium",
        "evidence_strength": "gray_zone",
        "sibling": {
            "name_zh": "Pagodane ⇌ Dodecahedrane 二电子异构",
            "name_en": "relative energies and strain of pagodane vs dodecahedrane",
            "kind": "property",
            "question_en": (
                "Determine the relative energies and strain content of the two C20H20 "
                "cage isomers pagodane and dodecahedrane (closed-shell endpoints)."
            ),
            "deliverable_en": (
                "the energy difference between pagodane and dodecahedrane in kcal/mol "
                "(state which cage is more stable)"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C1C2C3C4CC5C3C1C67C28C49C56C1CC9C2C8CC7C12"],
            "products": ["C12C3C4C5C1C6C7C2C8C3C9C4C1C5C6C2C7C8C9C12"],
            "steps": [
                {
                    "out": "C12C3C4C5C1C6C7C2C8C3C9C4C1C5C6C2C7C8C9C12",
                    "type": "valence isomerization between the two closed-shell C20H20 cages (endpoint comparison)",
                    "no_mapping": True,
                },
            ],
        },
    },
    # [1.1.1]propellane 中央反转键：电荷转移键（共价-离子共振），无单一 Lewis 表示 → 物种不可达
    "H8": {
        "name_zh": "[1.1.1]Propellane 中央\"反转键\"",
        "name_en": "central inverted bond of [1.1.1]propellane",
        "kind": "property",
        "question_en": (
            "Determine the nature and effective strength of the central inverted C1-C3 "
            "bond of [1.1.1]propellane: is there a bond, and how strong is it?"
        ),
        "deliverable_en": (
            "a characterization of the central C1-C3 bond: whether a shared-electron "
            "bond exists between the bridgehead carbons and its effective strength in "
            "kcal/mol"
        ),
        "conditions_en": "gas phase",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C1C23C1(C2)C3"],
        "products": ["C1C23C1(C2)C3"],
        "steps": [],
        "reactant_accessible": False,
        "wrongly_solve_penalty": "medium",
        "evidence_strength": "gray_zone",
        "sibling": {
            "name_zh": "[1.1.1]Propellane 中央\"反转键\"",
            "name_en": "strain energy and structure of bicyclo[1.1.1]pentane",
            "kind": "property",
            "question_en": (
                "Determine the strain energy and equilibrium structure of "
                "bicyclo[1.1.1]pentane."
            ),
            "deliverable_en": (
                "the strain energy of bicyclo[1.1.1]pentane in kcal/mol and its "
                "principal geometric parameters"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C1C2CC1C2"],
            "products": ["C1C2CC1C2"],
            "steps": [],
        },
    },
    # 硫代臭氧 S3：SCF/CISD 会把基态误判为环状 D3h，只有 CASSCF/MR-CISD 给对开式 C2v
    # → 开式/环状两个候选结构的相对排序均不可达
    "I2": {
        "name_zh": "硫代臭氧 S3 的开式 C2v vs 环状 D3h 基态之争",
        "name_en": "thiozone S3 ground-state structure (open C2v vs cyclic D3h)",
        "kind": "property",
        "question_en": (
            "Determine the equilibrium structure of thiozone S3: compare the open "
            "bent C2v form with the cyclic D3h form and identify the global minimum; "
            "also determine the S-S bond dissociation energy."
        ),
        "deliverable_en": (
            "which S3 structure (open C2v or cyclic D3h) is the global minimum and by "
            "how much in kcal/mol, plus the S-S dissociation energy in kcal/mol"
        ),
        "conditions_en": "gas phase",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["S=S=S"],
        "products": ["s1ss1"],
        "mapped_reactants": "[S:1]=[S:2]=[S:3]",
        "reactant_accessible": False,
        "steps": [
            {
                "out": "[S:1]1[S:2][S:3]1",
                "type": "ring closure between the two candidate S3 structures (open C2v vs cyclic D3h)",
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "硫代臭氧 S3 的开式 C2v vs 环状 D3h 基态之争",
            "name_en": "equilibrium structure and thermochemistry of disulfur monoxide",
            "kind": "property",
            "question_en": (
                "Determine the equilibrium structure and thermochemistry of disulfur "
                "monoxide S2O (a closed-shell sulfur oxide of the same family)."
            ),
            "deliverable_en": (
                "the equilibrium bond lengths and angle of S2O and its heat of "
                "formation in kcal/mol"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["S=S=O"],
            "products": ["S=S=O"],
            "steps": [],
        },
    },
    # 磷宾 HP：三线态基态（UKS 可算）→ 闭壳单线态（σ²/p² 组态混合，中等 MR）→ 灰色地带
    "I8": {
        "name_zh": "磷宾 HP 的单线态问题",
        "name_en": "phosphinidene HP singlet-triplet gap",
        "kind": "property",
        "question_en": (
            "Determine the singlet-triplet energy gap of phosphinidene HP and state "
            "which spin state is the ground state."
        ),
        "deliverable_en": (
            "the singlet-triplet gap of HP in kcal/mol and which state lies lower"
        ),
        "conditions_en": "gas phase",
        "charge": 0,
        "multiplicity": 3,
        "closed_shell": False,
        "reactants": ["[PH]"],
        "products": ["[PH]"],
        "mapped_reactants": "[PH:1]",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[PH:1]",
                "type": "vertical spin-state change: triplet ground state to closed-shell singlet of the same species",
                "conformational": True,
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "medium",
        "evidence_strength": "gray_zone",
        "sibling": {
            "name_zh": "磷宾 HP 的单线态问题",
            "name_en": "equilibrium structure and heat of formation of phosphaethyne",
            "kind": "property",
            "question_en": (
                "Determine the equilibrium structure and heat of formation of "
                "phosphaethyne HCP (phosphaalkyne)."
            ),
            "deliverable_en": (
                "the C-P bond length in Angstrom and the heat of formation of HCP in "
                "kcal/mol"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C#P"],
            "products": ["C#P"],
            "steps": [],
        },
    },
    # 甲氮烯 ⇌ 甲亚胺：单线态 1,2-H 迁移；小能垒对方法敏感 + 中间体存在性争议 → TS 不可达（灰色）
    "J6": {
        "name_zh": "甲氮烯 ⇌ 甲亚胺重排",
        "name_en": "methylnitrene to methanimine 1,2-hydrogen migration",
        "kind": "reaction",
        "question_en": (
            "Determine whether singlet methylnitrene is a discrete intermediate on the "
            "CH3N surface and the barrier of its 1,2-hydrogen migration to methanimine."
        ),
        "deliverable_en": (
            "the 1,2-H migration barrier in kcal/mol (transition state relative to the "
            "singlet methylnitrene minimum) and whether the nitrene is a discrete "
            "intermediate"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C[N]"],
        "products": ["C=N"],
        "mapped_reactants": "[CH2:1]([H:3])[N:2]",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[CH2:1]=[N:2][H:3]",
                "type": "1,2-hydrogen migration from carbon to nitrogen (methanimine formation)",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
            },
        ],
        "wrongly_solve_penalty": "medium",
        "evidence_strength": "gray_zone",
        "sibling": {
            "name_zh": "甲氮烯 ⇌ 甲亚胺重排",
            "name_en": "equilibrium geometry and dipole moment of methanimine",
            "kind": "property",
            "question_en": (
                "Determine the equilibrium geometry and dipole moment of methanimine "
                "H2C=NH (the closed-shell product of the nitrene rearrangement)."
            ),
            "deliverable_en": (
                "the principal geometric parameters of methanimine (in Angstrom and "
                "degrees) and its dipole moment in Debye"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C=N"],
            "products": ["C=N"],
            "steps": [],
        },
    },
    # 二硅烯 ⇌ 硅基硅烯：弱 Si=Si π 键（trans-bent、双自由基oid）→ 反应物与 TS 不可达（灰色）
    "J7": {
        "name_zh": "二硅烯 ⇌ 硅基硅烯异构面",
        "name_en": "disilene to silylsilylene isomerization on the Si2H4 surface",
        "kind": "reaction",
        "question_en": (
            "Determine the isomerization barrier between disilene H2Si=SiH2 and "
            "silylsilylene H3Si-SiH on the Si2H4 singlet surface, and the relative "
            "energies of the two isomers."
        ),
        "deliverable_en": (
            "the 1,2-hydrogen migration barrier in kcal/mol and the relative energy of "
            "disilene and silylsilylene in kcal/mol (state which is the global minimum)"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["[SiH2]=[SiH2]"],
        "products": ["[SiH][SiH3]"],
        "mapped_reactants": "[SiH:1]([H:3])=[SiH2:2]",
        "reactant_accessible": False,
        "steps": [
            {
                "out": "[SiH2:2]([H:3])[SiH:1]",
                "type": "1,2-hydrogen migration over the Si=Si bond (silylsilylene formation)",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
            },
        ],
        "wrongly_solve_penalty": "medium",
        "evidence_strength": "gray_zone",
        "sibling": {
            "name_zh": "二硅烯 ⇌ 硅基硅烯异构面",
            "name_en": "ethylene to ethylidene 1,2-hydrogen migration on the C2H4 surface",
            "kind": "reaction",
            "question_en": (
                "Determine the 1,2-hydrogen migration barrier between ethylene and "
                "ethylidene on the C2H4 surface (the carbon analogue of the disilene "
                "rearrangement), and their relative energies."
            ),
            "deliverable_en": (
                "the 1,2-hydrogen migration barrier in kcal/mol and the relative "
                "energy of ethylene and ethylidene in kcal/mol"
            ),
            "conditions_en": "gas phase, thermal",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C=C"],
            "products": ["[CH]C"],
            "mapped_reactants": "[CH:1]([H:3])=[CH2:2]",
            "steps": [
                {
                    "out": "[CH2:2]([H:3])[CH:1]",
                    "type": "1,2-hydrogen migration over the C=C bond (ethylidene formation)",
                    "with_ts": True,
                },
            ],
        },
    },
}
