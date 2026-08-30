"""R 族（重排：R1–R3）与 U 族（多组分/其他：U1, U5–U7）登记。

竞争通道（R1 分步碳正离子路径、R2 碎裂副反应、R3 分步酰基氮宾、U6 协同
[2+2]、U7 [1,2]-Stevens）按 normal.md 约定不进 gold，由 agent 自行探索。
"""

TASKS = {
    # [OH3+].CC(C)(O)C(C)(C)O>>[OH3+].CC(=O)C(C)(C)C.O  (+1/1)  频哪醇重排
    # 映射：1=H3O+ 的 O，2=酸性 H；3/5=离去侧甲基，4=离去侧 C，6=离去 OH；
    # 7=羰基侧 C，8=迁移甲基，9=保留甲基，10=羰基 O，11=羰基侧 OH 的 H。
    "R1": {
        "name_en": "pinacol rearrangement: pinacol -> pinacolone (acid-catalyzed)",
        "conditions_en": "concentrated H2SO4, heated",
        "mapped_reactants": "[OH2+:1]([H:2]).[CH3:3][C:4]([CH3:5])([OH:6])[C:7]([CH3:8])([CH3:9])[O:10][H:11]",
        "steps": [
            {
                # PT：H3O+ 质子化 4 号碳上的 OH
                "out": "[OH2:1].[CH3:3][C:4]([CH3:5])([OH+:6][H:2])[C:7]([CH3:8])([CH3:9])[O:10][H:11]",
                "type": "proton transfer from H3O+ to one pinacol OH (leaving-group activation)",
            },
            {
                # 决速：脱水与 1,2-甲基迁移协同（半频哪醇式），断 C4-O6/C7-C8，
                # 成 C4-C8 与 C7=O10 π → 质子化频哪酮 + H2O
                "out": "[OH2:1].[OH:6][H:2].[CH3:3][C:4]([CH3:5])([CH3:8])[C:7](=[O+:10][H:11])[CH3:9]",
                "type": "concerted semipinacol rearrangement (rate-determining): C-OH2+ cleavage with simultaneous 1,2-methyl shift and C=O pi formation; no free carbocation",
            },
            {
                # PT：质子化羰基把质子还给水，再生 H3O+
                "out": "[OH2+:1][H:11].[OH:6][H:2].[CH3:3][C:4]([CH3:5])([CH3:8])[C:7](=[O:10])[CH3:9]",
                "type": "proton transfer from protonated pinacolone to water, regenerating H3O+",
            },
        ],
    },
    # [OH3+].CC(C)=NO>>[OH3+].CNC(C)=O  (+1/1)  Beckmann 重排
    # 映射：1=H3O+ 的 O，2/9/10=其三个 H；3=保留甲基，4=肟 C，5=anti 迁移甲基，
    # 6=N，7=肟 OH 的 O，8=肟 OH 的 H。
    "R2": {
        "name_en": "Beckmann rearrangement: acetone oxime -> N-methylacetamide (acid-catalyzed)",
        "conditions_en": "concentrated H2SO4 or PCl5; industrial oleum (caprolactam process)",
        "mapped_reactants": "[O+:1]([H:2])([H:9])[H:10].[CH3:3][C:4]([CH3:5])=[N:6][O:7][H:8]",
        "steps": [
            {
                # PT：H3O+ 质子化肟 OH
                "out": "[O:1]([H:9])[H:10].[CH3:3][C:4]([CH3:5])=[N:6][O+:7]([H:8])[H:2]",
                "type": "proton transfer from H3O+ to the oxime OH (leaving-group activation)",
            },
            {
                # 决速：断 N6-O7 与 C4-C5，成 C5-N6（anti 甲基迁移）与 C4≡N6 π → nitrilium + H2O
                "out": "[O:1]([H:9])[H:10].[O:7]([H:8])[H:2].[CH3:3][C:4]#[N+:6][CH3:5]",
                "type": "concerted Beckmann rearrangement (rate-determining): N-O cleavage with anti 1,2-methyl migration from C to N and C-N pi bond formation -> nitrilium ion + water",
            },
            {
                # 水 O1 进攻 nitrilium 碳：成 C4-O1，断一根 C≡N π → O-质子化亚胺酸
                "out": "[O+:1]([H:9])([H:10])[C:4](=[N:6][CH3:5])[CH3:3].[O:7]([H:8])[H:2]",
                "type": "water attack on the nitrilium carbon: C-O formation with one C-N pi bond broken -> O-protonated imidic acid",
            },
            {
                # PT：另一分子水拔掉 OH2+ 的一个质子 → 中性亚胺酸 + H3O+
                "out": "[O:1]([H:10])[C:4](=[N:6][CH3:5])[CH3:3].[O+:7]([H:8])([H:2])[H:9]",
                "type": "proton transfer from the imidic acid OH2+ to water -> neutral imidic acid + H3O+",
            },
            {
                # 亚胺酸→酰胺互变异构：分子内 O→N 质子迁移，C=N π 断、C=O π 成
                "out": "[O:1]=[C:4]([CH3:3])[N:6]([H:10])[CH3:5].[O+:7]([H:8])([H:2])[H:9]",
                "type": "imidic acid -> amide tautomerization: intramolecular O-to-N proton shift with C=N pi to C=O pi migration",
            },
        ],
    },
    # CC(=O)N=[N+]=[N-]>>CN=C=O.N#N  (0/1)  Curtius 重排（单步协同）
    # 映射：1=甲基，2=酰基 C，3=羰基 O，4=Nα，5=Nβ，6=Nγ。
    "R3": {
        "name_en": "Curtius rearrangement: acetyl azide -> methyl isocyanate + N2",
        "conditions_en": "heated to ca. 80 degC, inert solvent",
        "mapped_reactants": "[CH3:1][C:2](=[O:3])[N:4]=[N+:5]=[N-:6]",
        "steps": [
            {
                # 断 C1-C2 与 Nα-Nβ，成 C1-Nα 与 Nβ≡Nγ 第三根键；C=O 不动
                "out": "[CH3:1][N:4]=[C:2]=[O:3].[N:5]#[N:6]",
                "type": "concerted Curtius rearrangement: 1,2-methyl migration from the acyl carbon to N(alpha) with simultaneous N2 extrusion (C-C and N(alpha)-N(beta) cleavage, C-N(alpha) formation, N(beta)=N(gamma) -> N#N)",
            },
        ],
    },
    # [OH-].C=O.C=O>>CO.O=C[O-]  (−1/1)  Cannizzaro
    # 映射：1=OH- 的 O，7=其 H；2=受体醛 C，3=其 O，6=转移的氢负 H；
    # 4=第二醛 C，5=其 O。
    "U1": {
        "name_en": "Cannizzaro reaction: 2 formaldehyde + OH- -> methanol + formate",
        "conditions_en": "concentrated aqueous NaOH",
        "mapped_reactants": "[O-:1][H:7].[CH:2]([H:6])=[O:3].[CH2:4]=[O:5]",
        "steps": [
            {
                # OH- 加成第一个甲醛：成 C2-O1，断 C2=O3 π → HOCH2O-
                "out": "[O:1]([H:7])[CH:2]([H:6])[O-:3].[CH2:4]=[O:5]",
                "type": "hydroxide addition to the first formaldehyde -> tetrahedral alkoxide HOCH2O-",
            },
            {
                # 决速：分子间氢负转移——断 C2-H6，成 C4-H6，第一碳回塌 C=O π，第二碳断 C=O π
                "out": "[O:1]([H:7])[CH:2]=[O:3].[CH2:4]([H:6])[O-:5]",
                "type": "rate-determining intermolecular hydride transfer from the alkoxide carbon to the second formaldehyde -> formic acid + methoxide",
            },
            {
                # PT：CH3O- 拔甲酸质子 → 甲酸根 + 甲醇
                "out": "[O-:1][CH:2]=[O:3].[CH2:4]([H:6])[O:5][H:7]",
                "type": "proton transfer from formic acid to methoxide -> formate + methanol",
            },
        ],
    },
    # C=O.O=CO.C[N+]#[C-]>>CNC(=O)COC=O  (0/1)  Passerini
    # 映射：1=醛 C，2=醛 O；3=甲酸羰基 C，4=其羰基 O，5=其羟基 O，6=酸性 H；
    # 7=异腈甲基，8=N，9=异腈 C。
    "U5": {
        "name_en": "Passerini reaction: formaldehyde + formic acid + methyl isocyanide -> N-methyl-alpha-formyloxyacetamide",
        "conditions_en": "nonpolar solvent, room temperature, high concentration",
        "mapped_reactants": "[CH2:1]=[O:2].[O:4]=[CH:3][O:5][H:6].[CH3:7][N+:8]#[C-:9]",
        "steps": [
            {
                # PT：甲酸向甲醛质子转移 → 质子化甲醛 + 甲酸根
                "out": "[CH2:1]=[O+:2][H:6].[O-:5][CH:3]=[O:4].[CH3:7][N+:8]#[C-:9]",
                "type": "proton transfer from formic acid to formaldehyde -> protonated formaldehyde + formate",
            },
            {
                # 异腈 C α-加成醛碳：成 C9-C1，断 C1=O2 π → nitrilium
                "out": "[CH2:1]([O:2][H:6])[C:9]#[N+:8][CH3:7].[O-:5][CH:3]=[O:4]",
                "type": "alpha-addition of the isocyanide carbon to the aldehyde carbon -> nitrilium ion",
            },
            {
                # 甲酸根 O 捕获 nitrilium C：成 O5-C9，断一根 C≡N π → 亚氨酸酯
                "out": "[CH2:1]([O:2][H:6])[C:9](=[N:8][CH3:7])[O:5][CH:3]=[O:4]",
                "type": "formate oxygen capture of the nitrilium carbon -> imidate (acyloxyimine) intermediate",
            },
            {
                # Mumm 重排：断 C3-O5，成 O2-C3，断 N=C π，成 C9=O5 π，O2-H 迁到 N8
                "out": "[CH3:7][N:8]([H:6])[C:9](=[O:5])[CH2:1][O:2][CH:3]=[O:4]",
                "type": "Mumm rearrangement: acyl transfer from the imidate oxygen to the alkoxy oxygen (C-O cleavage/formation, C=N pi to C=O pi) with intramolecular O-H -> N-H proton shift",
            },
        ],
    },
    # C=C=O.C=N>>O=C1CCN1  (0/1)  Staudinger β-内酰胺
    # 映射：1=乙烯酮端基 C，2=中心 C，3=O；4=亚胺 C，5=N。
    "U6": {
        "name_en": "Staudinger beta-lactam synthesis: ketene + methanimine -> 2-azetidinone",
        "conditions_en": "ketene generated in situ; inert solvent",
        "mapped_reactants": "[CH2:1]=[C:2]=[O:3].[CH2:4]=[NH:5]",
        "steps": [
            {
                # 亚胺 N 进攻乙烯酮中心 C：成 N5-C2，断 C2=O3 π → 两性离子烯醇盐
                "out": "[O-:3][C:2](=[CH2:1])[NH+:5]=[CH2:4]",
                "type": "imine nitrogen attack on the ketene central carbon: C-N formation with C=O pi cleavage -> zwitterionic enolate",
            },
            {
                # 顺旋 4π 关环：成 C1-C4，断 C4=N5 π 与 C1=C2 π，烯醇盐回塌成 C2=O3 π
                "out": "[O:3]=[C:2]1[CH2:1][CH2:4][NH:5]1",
                "type": "conrotatory 4pi electrocyclization: terminal-C to imine-C bond formation, C=N pi cleavage and enolate collapse to the lactam C=O",
            },
        ],
    },
    # [CH2-][N+](C)(C)CC=CC>>CN(C)CC(C)C=C  (0/1)  铵叶立德 [2,3]-σ 迁移（单步）
    # 映射：1=叶立德 C，2=N，3/4=N-甲基，5=烯丙基 α-C，6=β-C，7=γ-C，8=γ 上甲基。
    "U7": {
        "name_en": "ammonium ylide [2,3]-sigmatropic rearrangement (Sommelet-Hauser type) vs [1,2]-Stevens competition: crotyltrimethylammonium ylide (written line: [2,3] product)",
        "conditions_en": "salt-free model conditions (gas-phase ylide, closest to model chemistry)",
        "mapped_reactants": "[CH2-:1][N+:2]([CH3:3])([CH3:4])[CH2:5][CH:6]=[CH:7][CH3:8]",
        "steps": [
            {
                # 成 C1-C7（叶立德 C 到 γ 位），断 N2-C5（α 位），π 迁移 β=γ → α=β
                "out": "[CH3:3][N:2]([CH3:4])[CH2:1][CH:7]([CH3:8])[CH:6]=[CH2:5]",
                "type": "concerted closed-shell [2,3]-sigmatropic rearrangement: new C-C bond between the ylide carbon and the allyl gamma-carbon, N-C(alpha) cleavage, pi shift to the terminal alkene (competing [1,2]-Stevens channel not in gold)",
            },
        ],
    },
}
