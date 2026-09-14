"""R 族 + U 族登记（v3 缩减后）：R1 pinacol、U3 Wittig（新收）、U5 Passerini、U6 Staudinger。

v3（2026-09-09）收窄为四条多步/中间体网络；R2/R3/U1/U7 剔出定稿名单留档池
（条目见 normal.md）。竞争通道（R1 分步碳正离子路径、U6 协同 [2+2] 等）按
normal.md 约定不进 gold，由 agent 自行探索。
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
                "barrier": 26.2,
                "weight": 0.5,
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
    # CC(=O)N=[N+]=[N-]>>CN=C=O.N#N  (0/1)  Curtius 重排（单步协同）
    # [OH-].C=O.C=O>>CO.O=C[O-]  (−1/1)  Cannizzaro
    # 映射：1=OH- 的 O，7=其 H；2=受体醛 C，3=其 O，6=转移的氢负 H；
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
                "barrier": 19.9,
                "weight": 0.5,
            },
            {
                # 甲酸根 O 捕获 nitrilium C：成 O5-C9，断一根 C≡N π → 亚氨酸酯
                "out": "[CH2:1]([O:2][H:6])[C:9](=[N:8][CH3:7])[O:5][CH:3]=[O:4]",
                "type": "formate oxygen capture of the nitrilium carbon -> imidate (acyloxyimine) intermediate",
                "barrier": 16.6,
                "weight": 0.5,
            },
            {
                # Mumm 重排：断 C3-O5，成 O2-C3，断 N=C π，成 C9=O5 π，O2-H 迁到 N8
                "out": "[CH3:7][N:8]([H:6])[C:9](=[O:5])[CH2:1][O:2][CH:3]=[O:4]",
                "type": "Mumm rearrangement: acyl transfer from the imidate oxygen to the alkoxy oxygen (C-O cleavage/formation, C=N pi to C=O pi) with intramolecular O-H -> N-H proton shift",
                "barrier": 13.8,
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
            },
            {
                # 顺旋 4π 关环：成 C1-C4，断 C4=N5 π 与 C1=C2 π，烯醇盐回塌成 C2=O3 π
                "out": "[O:3]=[C:2]1[CH2:1][CH2:4][NH:5]1",
                "type": "conrotatory 4pi electrocyclization: terminal-C to imine-C bond formation, C=N pi cleavage and enolate collapse to the lactam C=O",
            },
        ],
    },
    # [CH2-][PH3+].C=O>>C=C.O=[PH3]  (0/1)  Wittig 简化版（两步：oxaphosphetane 中间体）
    # 映射：1=叶立德 C（CH2-），2=P（PH3+），3=甲醛 C，4=甲醛 O。
    # 步①异步 [2+2]：成 C1-C3 与 P2-O4（断 C3=O4 π）→ 氧磷杂环丁烷；步②环消除：成
    # C1=C3 与 P2=O4（断 P2-C1、C3-O4）→ 乙烯 + H3P=O。电荷账：反应物 -1/+1（净 0）
    # → 中间体中性磷烷 → 产物中性。betaine 路径为背景通道不进 gold。
    "U3": {
        "name_en": "Wittig reaction simplified model: H3P=CH2 ylide + formaldehyde -> ethylene + H3P=O (via oxaphosphetane)",
        "conditions_en": "salt-free model conditions (gas-phase ylide, closest to model chemistry)",
        "mapped_reactants": "[CH2-:1][PH3+:2].[CH2:3]=[O:4]",
        "steps": [
            {
                "out": "[PH3:2]1[O:4][CH2:3][CH2:1]1",
                "type": "asynchronous [2+2] addition of the ylide carbon to the aldehyde carbon with P-O bond formation -> oxaphosphetane intermediate (four-membered ring; betaine is the bypassed background channel)",
            },
            {
                "out": "[CH2:1]=[CH2:3].[O:4]=[PH3:2]",
                "type": "oxaphosphetane cycloreversion: P-C and C-O ring cleavage with C=C and P=O pi formation -> ethylene + phosphine oxide",
                "barrier": 19.1,
                "weight": 0.5,
            },
        ],
    },
    # [CH2-][N+](C)(C)CC=CC>>CN(C)CC(C)C=C  (0/1)  铵叶立德 [2,3]-σ 迁移（单步）
}
