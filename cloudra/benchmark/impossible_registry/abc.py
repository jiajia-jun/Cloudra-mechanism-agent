"""A/B/C 族登记：断键/价互变 TS（A1/A5/A7/A8/A9/A11）+ 双自由基能隙（B5）+ 开壳单线态（C3）。

A 族全为反应题（R→TS→P，TS 不可达）；B5/C3 为自旋态能量题（同物种双态
节点 + 无 TS 的态变化边，参考态可达、目标态不可达）。
"""

TASKS = {
    # C1=CC=C1  环丁二烯矩形基态 → D4h TS → 矩形自异构产物（同分子键式互换）
    # D4h TS 两组态严格简并 → ts_accessible=False
    "A1": {
        "name_zh": "环丁二烯 D4h 自动异构化",
        "name_en": "cyclobutadiene D4h automerization",
        "kind": "reaction",
        "question_en": (
            "Determine the mechanism and activation barrier of the thermal automerization "
            "of cyclobutadiene (rectangular ground state interconverting through the square "
            "transition structure)."
        ),
        "deliverable_en": (
            "the automerization barrier in kcal/mol (transition state relative to the "
            "rectangular ground-state minimum)"
        ),
        "conditions_en": "gas phase, low temperature (matrix isolation regime)",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C1=CC=C1"],
        "products": ["C1=CC=C1"],
        "mapped_reactants": "[CH:1]1=[CH:2][CH:3]=[CH:4]1",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[CH:1]1[CH:2]=[CH:3][CH:4]=1",
                "type": "thermal automerization through the D4h square transition state (double-bond pattern interchange)",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "环丁二烯 D4h 自动异构化",
            "name_en": "cyclooctatetraene bond-shift valence tautomerization",
            "kind": "reaction",
            "question_en": (
                "Determine the mechanism and activation barrier of the bond-shift valence "
                "tautomerization of cyclooctatetraene (tub ground state interconverting "
                "through the planar transition region)."
            ),
            "deliverable_en": (
                "the bond-shift barrier in kcal/mol (transition state relative to the tub "
                "ground-state minimum)"
            ),
            "conditions_en": "gas phase, room temperature",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C1=CC=CC=CC=C1"],
            "products": ["C1=CC=CC=CC=C1"],
            "mapped_reactants": "[CH:1]1=[CH:2][CH:3]=[CH:4][CH:5]=[CH:6][CH:7]=[CH:8]1",
            "steps": [
                {
                    "out": "[CH:1]1[CH:2]=[CH:3][CH:4]=[CH:5][CH:6]=[CH:7][CH:8]=1",
                    "type": "bond-shift valence tautomerization through the planar transition region (double-bond pattern interchange)",
                    "with_ts": True,
                },
            ],
        },
    },
    # C1=CCC1  环丁烯反旋（热禁阻）开环 → 1,3-丁二烯
    # 反旋 TS 处 HOMO/LUMO 组态交叉 → ts_accessible=False
    "A5": {
        "name_zh": "环丁烯反旋（禁阻）开环",
        "name_en": "cyclobutene disrotatory ring opening",
        "kind": "reaction",
        "question_en": (
            "Determine the mechanism and activation barrier of the disrotatory ring "
            "opening of cyclobutene to 1,3-butadiene (the ring-opening mode that rotates "
            "the two termini in opposite directions)."
        ),
        "deliverable_en": (
            "the activation barrier in kcal/mol for the disrotatory ring-opening pathway "
            "(transition state relative to the cyclobutene minimum)"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C1=CCC1"],
        "products": ["C=CC=C"],
        "mapped_reactants": "[CH:1]1=[CH:2][CH2:3][CH2:4]1",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[CH2:4]=[CH:1][CH:2]=[CH2:3]",
                "type": "disrotatory electrocyclic ring opening to 1,3-butadiene",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "环丁烯反旋（禁阻）开环",
            "name_en": "cyclobutene conrotatory ring opening",
            "kind": "reaction",
            "question_en": (
                "Determine the mechanism and activation barrier of the conrotatory thermal "
                "ring opening of cyclobutene to 1,3-butadiene (the thermally allowed mode "
                "that rotates both termini in the same direction)."
            ),
            "deliverable_en": (
                "the activation barrier in kcal/mol for the conrotatory ring-opening "
                "pathway (transition state relative to the cyclobutene minimum)"
            ),
            "conditions_en": "gas phase, thermal",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C1=CCC1"],
            "products": ["C=CC=C"],
            "mapped_reactants": "[CH:1]1=[CH:2][CH2:3][CH2:4]1",
            "steps": [
                {
                    "out": "[CH2:4]=[CH:1][CH:2]=[CH2:3]",
                    "type": "conrotatory electrocyclic ring opening to 1,3-butadiene (thermally allowed 4pi mode)",
                    "with_ts": True,
                },
            ],
        },
    },
    # C#C/C=C\C#C  (Z)-3-己烯-1,5-二炔 Bergman 环化 → p-苯炔双自由基
    # 产物 p-苯炔开壳双自由基 + TS 已双自由基化 → TS 与中间体均不可达
    "A7": {
        "name_zh": "Bergman 环化",
        "name_en": "Bergman cyclization of (Z)-hex-3-ene-1,5-diyne",
        "kind": "reaction",
        "question_en": (
            "Determine the mechanism and activation barrier of the Bergman cyclization "
            "of (Z)-hex-3-ene-1,5-diyne to p-benzyne (1,4-didehydrobenzene)."
        ),
        "deliverable_en": (
            "the cyclization barrier in kcal/mol (transition state relative to the "
            "enediyne minimum) and the reaction energy to the p-benzyne product"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C#C/C=C\\C#C"],
        "products": ["[c]1cc[c]cc1"],
        "mapped_reactants": "[CH:1]#[C:2]/[CH:3]=[CH:4]\\[C:5]#[CH:6]",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[CH:1]1=[C:2][CH:3]=[CH:4][C:5]=[CH:6]1",
                "type": "Bergman cyclization: C1-C6 bond formation to the p-benzyne diradical",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "Bergman 环化",
            "name_en": "6pi electrocyclic ring closure of 1,3,5-hexatriene",
            "kind": "reaction",
            "question_en": (
                "Determine the mechanism and activation barrier of the thermal 6pi "
                "electrocyclic ring closure of 1,3,5-hexatriene to 1,3-cyclohexadiene."
            ),
            "deliverable_en": (
                "the ring-closure barrier in kcal/mol (transition state relative to the "
                "hexatriene minimum)"
            ),
            "conditions_en": "gas phase, thermal",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C=CC=CC=C"],
            "products": ["C1=CCCC=C1"],
            "mapped_reactants": "[CH2:1]=[CH:2][CH:3]=[CH:4][CH:5]=[CH2:6]",
            "steps": [
                {
                    "out": "[CH2:1]1[CH:2]=[CH:3][CH:4]=[CH:5][CH2:6]1",
                    "type": "6pi disrotatory electrocyclic ring closure to 1,3-cyclohexadiene",
                    "with_ts": True,
                },
            ],
        },
    },
    # C=[O+][O-]  Criegee 中间体 CH2OO → 二氧杂环甲烷
    # CH2OO 本身 T1=0.043 强 MR，TS 静态关联贯穿路径 → 反应物与 TS 均不可达
    "A8": {
        "name_zh": "Criegee 中间体 CH2OO 单分子异构化",
        "name_en": "Criegee intermediate CH2OO isomerization to dioxirane",
        "kind": "reaction",
        "question_en": (
            "Determine the mechanism and barrier for the unimolecular isomerization of "
            "the simplest Criegee intermediate CH2OO (carbonyl oxide) to dioxirane."
        ),
        "deliverable_en": (
            "the isomerization barrier in kcal/mol (transition state relative to the "
            "CH2OO minimum) and the isomerization energy"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C=[O+][O-]"],
        "products": ["C1OO1"],
        "mapped_reactants": "[CH2:1]=[O+:2][O-:3]",
        "reactant_accessible": False,
        "steps": [
            {
                "out": "[CH2:1]1[O:2][O:3]1",
                "type": "ring closure of the carbonyl oxide to dioxirane",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "Criegee 中间体 CH2OO 单分子异构化",
            "name_en": "relative energies of the closed-shell C1H2O2 isomers (formic acid vs dioxirane)",
            "kind": "property",
            "question_en": (
                "Determine the relative energies of the two closed-shell C1H2O2 isomers: "
                "formic acid and dioxirane."
            ),
            "deliverable_en": (
                "the energy difference in kcal/mol between dioxirane and formic acid "
                "(state which isomer is the global minimum)"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C(=O)O"],
            "products": ["C1OO1"],
            "mapped_reactants": "[CH:1](=[O:2])[O:3][H:4]",
            "steps": [
                {
                    "out": "[H:4][CH:1]1[O:2][O:3]1",
                    "type": "isomerization (hydrogen shift plus ring closure) between formic acid and dioxirane",
                },
            ],
        },
    },
    # C1COO1  1,2-二氧环丁烷 → 2 甲醛：O-O 断裂 TS 进入双自由基相 → TS 不可达
    "A9": {
        "name_zh": "1,2-二氧环丁烷热解",
        "name_en": "1,2-dioxetane thermolysis to two formaldehyde",
        "kind": "reaction",
        "question_en": (
            "Determine the mechanism and activation barrier of the thermolysis of "
            "1,2-dioxetane to two formaldehyde molecules (the model chemiluminescent "
            "reaction)."
        ),
        "deliverable_en": (
            "the activation barrier in kcal/mol (transition state relative to the "
            "1,2-dioxetane minimum)"
        ),
        "conditions_en": "gas phase, thermal",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["C1COO1"],
        "products": ["C=O", "C=O"],
        "mapped_reactants": "[CH2:1]1[CH2:2][O:3][O:4]1",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[CH2:1]=[O:4].[CH2:2]=[O:3]",
                "type": "concerted O-O and C-C bond cleavage to two formaldehyde (chemiluminescent decomposition)",
                "with_ts": True,
                "ts_accessible": False,
                "node_accessible": True,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "1,2-二氧环丁烷热解",
            "name_en": "ring strain and thermochemistry of oxetane",
            "kind": "property",
            "question_en": (
                "Determine the ring strain energy and heat of formation of oxetane "
                "(trimethylene oxide)."
            ),
            "deliverable_en": (
                "the ring strain energy and heat of formation of oxetane in kcal/mol"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["C1COC1"],
            "products": ["C1COC1"],
            "steps": [],
        },
    },
    # C=C + O=O(1Δg)  单线态氧 ene 反应 → 乙烯基过氧化氢
    # 苯基氮烯：三线态基态（UKS 可算）→ 开壳单线态（σπ 开壳，不可达）
    "C3": {
        "name_zh": "苯基氮烯开壳单线态",
        "name_en": "phenylnitrene open-shell singlet state",
        "kind": "property",
        "question_en": (
            "Determine the singlet-triplet energy gap of phenylnitrene and the "
            "electronic structure of its lowest singlet state."
        ),
        "deliverable_en": (
            "the singlet-triplet gap of phenylnitrene in kcal/mol, which state lies "
            "lower, and the character of the lowest singlet state"
        ),
        "conditions_en": "gas phase",
        "charge": 0,
        "multiplicity": 3,
        "closed_shell": False,
        "reactants": ["[N]c1ccccc1"],
        "products": ["[N]c1ccccc1"],
        "mapped_reactants": "[N:1][c:2]1[cH:3][cH:4][cH:5][cH:6][cH:7]1",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[N:1][c:2]1[cH:3][cH:4][cH:5][cH:6][cH:7]1",
                "type": "vertical spin-state change: triplet ground state to open-shell singlet of the same species",
                "conformational": True,
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "苯基氮烯开壳单线态",
            "name_en": "equilibrium geometry and frequencies of triplet phenylnitrene",
            "kind": "property",
            "question_en": (
                "Determine the equilibrium geometry and harmonic vibrational frequencies "
                "of triplet phenylnitrene (the ground state of C6H5N)."
            ),
            "deliverable_en": (
                "the principal geometric parameters (in Angstrom and degrees) and a "
                "characterization of the harmonic vibrational frequencies of triplet "
                "phenylnitrene"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 3,
            "closed_shell": False,
            "reactants": ["[N]c1ccccc1"],
            "products": ["[N]c1ccccc1"],
            "steps": [],
        },
    },
}
