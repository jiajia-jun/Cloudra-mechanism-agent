"""D/E/F/G 族登记：反常键（D2 FOOF）+ 解离曲线（E2 N2）+ 非 Kekulé 烃（F3 三角烯）
+ 重 14 族多重键（G6 二锗炔 / G7 二硅炔）+ 过渡金属六重键（G8 Cr2）。

除 F3 为自旋态题外均为物种/解离性质题：解离类图 = 平衡物种节点 + 解离极限
节点（无一阶鞍点，边 via=None）；G 族"键强度"类问题把成键本身多参考的端点
也标不可达（CGMT 极限/六重键自旋耦合贯穿全曲线）。
"""

TASKS = {
    # FOOF 反常键：F-O σ* 占据导致强静态关联，键长/键能对 post-CCSD(T) 敏感 → 物种不可达
    "D2": {
        "name_zh": "FOOF（F2O2）反常键",
        "name_en": "anomalous bonding in dioxygen difluoride (FOOF)",
        "kind": "property",
        "question_en": (
            "Determine the equilibrium structure of dioxygen difluoride FOOF (the F-O "
            "and O-O bond lengths) and its F-O bond dissociation energy."
        ),
        "deliverable_en": (
            "the equilibrium F-O and O-O bond lengths in Angstrom and the F-O bond "
            "dissociation energy in kcal/mol"
        ),
        "conditions_en": "gas phase, low temperature",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["FOOF"],
        "products": ["FOOF"],
        "steps": [],
        "reactant_accessible": False,
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "FOOF（F2O2）反常键",
            "name_en": "O-O bond dissociation energy of hydrogen peroxide",
            "kind": "property",
            "question_en": (
                "Determine the O-O bond dissociation energy of hydrogen peroxide H2O2 "
                "(homolysis to two hydroxyl radicals)."
            ),
            "deliverable_en": (
                "the O-O bond dissociation energy of H2O2 in kcal/mol"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["OO"],
            "products": ["[OH]", "[OH]"],
            "mapped_reactants": "[OH:1][OH:2]",
            "steps": [
                {
                    "out": "[OH:1].[OH:2]",
                    "type": "O-O bond homolysis to two hydroxyl radicals (dissociation limit)",
                },
            ],
        },
    },
    # N2 解离曲线：平衡区单参考尚可（R 可达），拉伸区组态数爆炸（解离极限不可达）
    "E2": {
        "name_zh": "N2 解离曲线",
        "name_en": "nitrogen triple-bond dissociation curve",
        "kind": "property",
        "question_en": (
            "Compute the ground-state dissociation curve of N2 and its bond "
            "dissociation energy."
        ),
        "deliverable_en": (
            "the N2 bond dissociation energy in kcal/mol, together with the computed "
            "dissociation curve (energy vs bond length)"
        ),
        "conditions_en": "gas phase",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["N#N"],
        "products": ["[N]", "[N]"],
        "mapped_reactants": "[N:1]#[N:2]",
        "reactant_accessible": True,
        "steps": [
            {
                "out": "[N:1].[N:2]",
                "type": "bond stretching to the separated-atom dissociation limit",
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "N2 解离曲线",
            "name_en": "equilibrium bond length and vibrational frequency of N2",
            "kind": "property",
            "question_en": (
                "Determine the equilibrium bond length and the harmonic vibrational "
                "frequency of the N2 ground state."
            ),
            "deliverable_en": (
                "the equilibrium bond length in Angstrom and the harmonic vibrational "
                "frequency in cm-1 of N2"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["N#N"],
            "products": ["N#N"],
            "steps": [],
        },
    },
    # 三角烯：非 Kekulé 子格失衡 → 三线态基态（UKS 可算），开壳单线态双组态（不可达）
    "F3": {
        "name_zh": "三角烯三线态基态",
        "name_en": "triangulene triplet ground state and singlet-triplet gap",
        "kind": "property",
        "question_en": (
            "Determine the ground-state spin multiplicity of triangulene (the smallest "
            "non-Kekulen polycyclic aromatic hydrocarbon) and its singlet-triplet gap."
        ),
        "deliverable_en": (
            "the singlet-triplet gap of triangulene in kcal/mol and which spin state is "
            "the ground state"
        ),
        "conditions_en": "gas phase (surface-synthesis analogue)",
        "charge": 0,
        "multiplicity": 3,
        "closed_shell": False,
        "reactants": ["[CH]1C2=C3C(=CC=C2)[CH]C4=CC=CC5=C4C3=C6C1=CC=CC6=C5"],
        "products": ["[CH]1C2=C3C(=CC=C2)[CH]C4=CC=CC5=C4C3=C6C1=CC=CC6=C5"],
        "mapped_reactants": (
            "[CH:1]1[c:2]2[c:3]3[c:4]([cH:5][cH:6][cH:7]2)[CH:8][c:9]2[cH:10][cH:11]"
            "[cH:12][c:13]4[c:14]2[c:15]-3[c:16]2[c:17]1[cH:18][cH:19][cH:20][c:21]2[cH:22]4"
        ),
        "reactant_accessible": True,
        "steps": [
            {
                "out": (
                    "[CH:1]1[c:2]2[c:3]3[c:4]([cH:5][cH:6][cH:7]2)[CH:8][c:9]2[cH:10]"
                    "[cH:11][cH:12][c:13]4[c:14]2[c:15]-3[c:16]2[c:17]1[cH:18][cH:19]"
                    "[cH:20][c:21]2[cH:22]4"
                ),
                "type": "vertical spin-state change: triplet ground state to open-shell singlet of the same species",
                "conformational": True,
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "三角烯三线态基态",
            "name_en": "equilibrium structure and thermochemistry of pyrene",
            "kind": "property",
            "question_en": (
                "Determine the equilibrium structure and the heat of formation of "
                "pyrene (a closed-shell Kekulen PAH of comparable size)."
            ),
            "deliverable_en": (
                "the heat of formation of pyrene in kcal/mol and its principal "
                "equilibrium geometric parameters"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["c1cc2ccc3cccc4ccc(c1)c2c34"],
            "products": ["c1cc2ccc3cccc4ccc(c1)c2c34"],
            "steps": [],
        },
    },
    # 二锗炔（母体 HGe≡GeH 代替 Ar' 大位阻物）：CGMT 极限，"三键"实为 σ + 近瓦解 π，
    # 键合本身强双自由基oid → 成键端点与解离端点均不可达（灰色证据但条目定稿保留 high？
    # Cr2 六重键：价层 3d/4s 近简并，平衡区即灾难（CASSCF 连极小值都给不出）→ 两端均不可达
    "G8": {
        "name_zh": "铬二聚体六重键解离曲线",
        "name_en": "chromium dimer ground-state dissociation curve",
        "kind": "property",
        "question_en": (
            "Compute the ground-state potential energy curve of the chromium dimer Cr2 "
            "(formal sextuple bond) and its bond dissociation energy."
        ),
        "deliverable_en": (
            "the Cr2 bond dissociation energy in kcal/mol, together with the computed "
            "potential energy curve (energy vs bond length)"
        ),
        "conditions_en": "gas phase",
        "charge": 0,
        "multiplicity": 1,
        "closed_shell": True,
        "reactants": ["[Cr][Cr]"],
        "products": ["[Cr]", "[Cr]"],
        "mapped_reactants": "[Cr:1][Cr:2]",
        "reactant_accessible": False,
        "steps": [
            {
                "out": "[Cr:1].[Cr:2]",
                "type": "Cr-Cr bond stretching to the separated-atom limit (formal sextuple bond dissociation)",
                "node_accessible": False,
            },
        ],
        "wrongly_solve_penalty": "high",
        "evidence_strength": "ironclad",
        "sibling": {
            "name_zh": "铬二聚体六重键解离曲线",
            "name_en": "bond dissociation energy of Na2",
            "kind": "property",
            "question_en": (
                "Determine the bond dissociation energy of the sodium dimer Na2 (a "
                "single-sigma-bond metal dimer)."
            ),
            "deliverable_en": (
                "the Na2 bond dissociation energy in kcal/mol and its equilibrium bond "
                "length in Angstrom"
            ),
            "conditions_en": "gas phase",
            "charge": 0,
            "multiplicity": 1,
            "closed_shell": True,
            "reactants": ["[Na][Na]"],
            "products": ["[Na]", "[Na]"],
            "mapped_reactants": "[Na:1][Na:2]",
            "steps": [
                {
                    "out": "[Na:1].[Na:2]",
                    "type": "Na-Na bond stretching to the separated-atom dissociation limit",
                },
            ],
        },
    },
}
