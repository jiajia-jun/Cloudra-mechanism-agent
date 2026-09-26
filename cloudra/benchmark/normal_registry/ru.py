"""R 族 + U 族登记：R1 pinacol、R4 Wolff 重排、
U3 磷叶立德+甲醛、U5 Passerini、U6 Staudinger。

v3（2026-09-09）收窄为四条多步/中间体网络；R2/R3/U1/U7 剔出定稿名单留档池
（条目见 normal.md）。v4（2026-09-25）换血：R4/U8 入正选替 A5/O3 槽——两条
构建期各边暂不写 barrier；R4 第 2 步已回填自算参考垒。U8 于 2026-09-26
移入 impossible B9。竞争通道（R1 分步碳正离子路径、U6 协同 [2+2]、
R4 协同 Wolff 通道与 oxirene 等）
按 normal.md 约定不进 gold，由 agent 自行探索。
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
                "barrier": 0.0,
            },
            {
                # 决速：脱水与 1,2-甲基迁移协同（半频哪醇式），断 C4-O6/C7-C8，
                # 成 C4-C8 与 C7=O10 π → 质子化频哪酮 + H2O
                "out": "[OH2:1].[OH:6][H:2].[CH3:3][C:4]([CH3:5])([CH3:8])[C:7](=[O+:10][H:11])[CH3:9]",
                "type": "concerted semipinacol rearrangement (rate-determining): C-OH2+ cleavage with simultaneous 1,2-methyl shift and C=O pi formation; no free carbocation",
                "barrier": 26.2,
                "weight": 0.5,
            },
            {
                # PT：质子化羰基把质子还给水，再生 H3O+
                "out": "[OH2+:1][H:11].[OH:6][H:2].[CH3:3][C:4]([CH3:5])([CH3:8])[C:7](=[O:10])[CH3:9]",
                "type": "proton transfer from protonated pinacolone to water, regenerating H3O+",
                "barrier": 5.74,
            },
        ],
    },
    # O=CC=[N+]=[N-]>>C=C=O.N#N  (0/1)  Wolff 重排（分步经甲酰卡宾；协同通道按约定不进 gold）
    "R4": {
        "name_en": "Wolff rearrangement: diazoacetaldehyde -> ketene + N2 (stepwise via formylcarbene)",
        "conditions_en": "gas-phase thermolysis",
        "mapped_reactants": "[N-:1]=[N+:2]=[CH:3][C:4]([H:6])=[O:5]",
        "steps": [
            {
                "out": "[N:1]#[N:2].[CH:3][C:4]([H:6])=[O:5]",
                "type": "N2 extrusion -> singlet formylcarbene (stepwise Wolff path)",
            },
            {
                "out": "[N:1]#[N:2].[CH:3]([H:6])=[C:4]=[O:5]",
                "type": "1,2-H shift from the formyl carbon to the carbene carbon -> ketene",
                "barrier": 4.34,
            },
        ],
    },
    # [OH3+].CC(C)=NO>>[OH3+].CNC(C)=O  (+1/1)  Beckmann 重排
    # 映射：1=H3O+ 的 O，2/9/10=其三个 H；3=保留甲基，4=肟 C，5=anti 迁移甲基，
    # CC(=O)N=[N+]=[N-]>>CN=C=O.N#N  (0/1)  Curtius 重排（单步协同）
    # [OH-].C=O.C=O>>CO.O=C[O-]  (−1/1)  Cannizzaro
    # 映射：1=OH- 的 O，7=其 H；2=受体醛 C，3=其 O，6=转移的氢负 H；
    # C=O.O=CO.C[N+]#[C-]>>CNC(=O)COC=O  (0/1)  Passerini
    # 映射：1=醛 C，2=醛 O；3=甲酸羰基 C，4=其羰基 O，5=其羟基 O，6=酸性 H；
    # 7=异腈甲基，8=N，9=异腈 C。首步把酸质子转移与异腈加成合并。
    "U5": {
        "name_en": "Passerini reaction: formaldehyde + formic acid + methyl isocyanide -> N-methyl-alpha-formyloxyacetamide",
        "conditions_en": "dichloromethane (DCM), room temperature, high concentration",
        "mapped_reactants": "[CH2:1]=[O:2].[O:4]=[CH:3][O:5][H:6].[CH3:7][N+:8]#[C-:9]",
        "steps": [
            {
                # 联合：甲酸 O5-H6 断裂、O2-H6/C1-C9 成键、C1=O2 π 回落 → nitrilium/formate
                "out": "[CH2:1]([O:2][H:6])[C:9]#[N+:8][CH3:7].[O-:5][CH:3]=[O:4]",
                "type": "concerted formic-acid proton transfer and isocyanide C attack on formaldehyde -> nitrilium/formate contact ion pair",
                "barrier": 8.21,
                "weight": 0.5,
            },
            {
                # 甲酸根 O 捕获 nitrilium C：成 O5-C9，断一根 C≡N π → 亚氨酸酯
                "out": "[CH2:1]([O:2][H:6])[C:9](=[N:8][CH3:7])[O:5][CH:3]=[O:4]",
                "type": "formate oxygen capture of the nitrilium carbon -> imidate (acyloxyimine) intermediate",
                "barrier": 0.0,
                "weight": 0.5,
            },
            {
                # Mumm 重排：断 C3-O5，成 O2-C3，断 N=C π，成 C9=O5 π，O2-H 迁到 N8
                "out": "[CH3:7][N:8]([H:6])[C:9](=[O:5])[CH2:1][O:2][CH:3]=[O:4]",
                "type": "Mumm rearrangement: acyl transfer from the imidate oxygen to the alkoxy oxygen (C-O cleavage/formation, C=N pi to C=O pi) with intramolecular O-H -> N-H proton shift",
                "barrier": 31.7,
                "weight": 0.5,
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
                "barrier": 2.66,
            },
            {
                # 顺旋 4π 关环：成 C1-C4，断 C4=N5 π 与 C1=C2 π，烯醇盐回塌成 C2=O3 π
                "out": "[O:3]=[C:2]1[CH2:1][CH2:4][NH:5]1",
                "type": "conrotatory 4pi electrocyclization: terminal-C to imine-C bond formation, C=N pi cleavage and enolate collapse to the lactam C=O",
                "barrier": 15.72,
            },
        ],
    },
    # [CH2-][PH3+].C=O>>C=C.O=[PH3]  (0/1)  磷叶立德+甲醛（三步真实路径，本机 B3LYP-D3(BJ)/def2-SVP 自算）
    # 映射：1=叶立德 C（CH2-），2=P（PH3+），3=甲醛 C，4=甲醛 O，5=迁移的 P-H 氢。
    # 步①叶立德 C 进攻甲醛 C 成 C1-C3，同时 P2-H5 质子转移到羰基 O4 → H2P-CH2-CH2-OH
    # 加成物（深阱，相对 RC −59.5 kcal；本模型 PES 上该 TS 不生成氧磷杂环丁烷）。
    # 步②该加成物分子内 O4->P2 质子回传 + P2-O4 关环 → 氧磷杂环丁烷（+55.8）。
    # 步③氧磷杂环丁烷环消除 → 乙烯 + H3P=O。电荷账：净 0 → 各中间体中性 → 产物中性。
    "U3": {
        "name_en": "H3P=CH2 ylide + formaldehyde -> ethylene + H3P=O",
        "conditions_en": "salt-free model conditions (gas-phase ylide, closest to model chemistry)",
        "mapped_reactants": "[CH2-:1][PH2+:2][H:5].[CH2:3]=[O:4]",
        "steps": [
            {
                "out": "[CH2:1]([PH2:2])[CH2:3][O:4][H:5]",
                "type": "nucleophilic addition of the ylide carbon to the aldehyde carbon (C-C bond formation) concerted with proton transfer from phosphorus to the carbonyl oxygen -> H2P-CH2-CH2-OH adduct (a deep minimum on this model PES; the four-membered oxaphosphetane is a separate minimum not connected to this saddle)",
                "barrier": 1.7,
                "weight": 1.0,
            },
            {
                "out": "[CH2:1]1[CH2:3][O:4][PH2:2]1([H:5])",
                "type": "intramolecular proton transfer from the hydroxyl oxygen back to phosphorus (H5 O->P) concerted with P-O ring closure -> oxaphosphetane",
                "barrier": 55.81,
                "weight": 1.0,
            },
            {
                "out": "[CH2:1]=[CH2:3].[O:4]=[PH2:2][H:5]",
                "type": "oxaphosphetane cycloreversion: C-P and C-O cleavage with C=C and P=O pi formation -> ethylene + phosphine oxide",
                "barrier": 23.76,
                "weight": 1.0,
            },
        ],
    },
    # [CH2-][N+](C)(C)CC=CC>>CN(C)CC(C)C=C  (0/1)  铵叶立德 [2,3]-σ 迁移（单步）
}
