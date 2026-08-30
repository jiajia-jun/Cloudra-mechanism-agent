"""Y 族 + O 族登记：酰基转移酸碱对偶（Y2/Y3）与氧转移/环氧开环（O2–O5）。

Y2/Y3 为同一底物（甲酸甲酯）的 AAC2/BAC2 对偶；O2 单步协同氧转移；
O3 Baeyer–Villiger 经 Criegee 四面体中间体；O4/O5 为环氧开环酸碱条件对。
竞争通道（AAL1、planar TS、中性水解等）按 normal.md 约定不进 gold。
"""

TASKS = {
    # [OH3+].COC=O.O>>[OH3+].O=CO.CO  (+1/1)  AAC2 酯水解
    "Y2": {
        "name_en": "Acid-catalyzed ester hydrolysis (AAC2): methyl formate + H3O+ -> formic acid + methanol",
        "conditions_en": "dilute aqueous acid, heated",
        "mapped_reactants": "[OH2+:1]([H:2]).[CH3:3][O:4][CH:5]=[O:6].[OH:7]([H:8])",
        "steps": [
            {
                # 羰基 O 质子化：断 O1-H2，成 O6-H2
                "out": "[OH2:1].[CH3:3][O:4][CH:5]=[O+:6][H:2].[OH:7]([H:8])",
                "type": "carbonyl oxygen protonation by hydronium (PT, pre-equilibrium)",
            },
            {
                # 水进攻羰基 C：成 O7-C5，断 C5=O6 π → 质子化四面体中间体
                "out": "[OH2:1].[CH3:3][O:4][CH:5]([O:6][H:2])[OH+:7]([H:8])",
                "type": "water addition to the protonated carbonyl carbon -> protonated tetrahedral intermediate (near rate-determining)",
            },
            {
                # 四面体中间体去质子：断 O7-H8，成 O1-H8，再生 H3O+
                "out": "[OH2+:1]([H:8]).[CH3:3][O:4][CH:5]([O:6][H:2])[OH:7]",
                "type": "deprotonation of the tetrahedral intermediate by water, regenerating H3O+ (PT)",
            },
            {
                # 消除甲醇：断 C5-O4，成 C5=O6 π；O6 的质子分子内转移到离去 MeOH 的 O4（断 O6-H2，成 O4-H2）
                "out": "[OH2+:1]([H:8]).[CH3:3][O:4][H:2].[CH:5](=[O:6])[OH:7]",
                "type": "methanol elimination: C-OMe cleavage with C=O pi reformation and intramolecular proton transfer to the leaving methoxy oxygen",
            },
        ],
    },
    # [OH-].COC=O>>O=C[O-].CO  (−1/1)  BAC2 皂化
    "Y3": {
        "name_en": "Ester saponification (BAC2): methyl formate + OH- -> formate + methanol",
        "conditions_en": "aqueous NaOH",
        "mapped_reactants": "[O-:1][H:6].[CH3:2][O:3][CH:4]=[O:5]",
        "steps": [
            {
                # OH- 加成：成 O1-C4，断 C4=O5 π → 四面体烷氧盐
                "out": "[CH3:2][O:3][CH:4]([O:1][H:6])[O-:5]",
                "type": "hydroxide addition to the carbonyl carbon -> tetrahedral alkoxide intermediate (capturable)",
            },
            {
                # 消除 MeO-：断 C4-O3，成 C4=O5 π → 甲酸 + 甲醇盐
                "out": "[CH3:2][O-:3].[CH:4](=[O:5])[O:1][H:6]",
                "type": "methoxide elimination: C-OMe cleavage with C=O pi reformation -> formic acid + methoxide",
            },
            {
                # 质子转移：断 O1-H6，成 O3-H6 → 甲酸根 + 甲醇
                "out": "[CH3:2][O:3][H:6].[CH:4](=[O:5])[O-:1]",
                "type": "proton transfer from formic acid to methoxide -> formate + methanol",
            },
        ],
    },
    # CC1(C)OO1.C=C>>CC(C)=O.C1CO1  (0/1)  DMDO 环氧化（spiro TS 单步）
    "O2": {
        "name_en": "DMDO epoxidation: dimethyldioxirane + ethylene -> oxirane + acetone (concerted oxygen transfer)",
        "conditions_en": "DMDO in acetone solution, low temperature",
        "mapped_reactants": "[CH3:1][C:3]1([CH3:2])[O:4][O:5]1.[CH2:6]=[CH2:7]",
        "steps": [
            {
                # spiro 蝶形 TS 氧转移：断 O4-O5、C3-O5、C6=C7 π；成 C3=O4 π、O5-C6、O5-C7
                "out": "[CH3:1][C:3](=[O:4])[CH3:2].[CH2:6]1[CH2:7][O:5]1",
                "type": "concerted oxygen transfer via a spiro (butterfly) TS: O-O cleavage with simultaneous formation of both epoxide C-O bonds (spiro preferred over planar TS)",
            },
        ],
    },
    # [OH3+].CC(C)=O.O=COO>>[OH3+].CC(=O)OC.O=CO  (+1/1)  Baeyer–Villiger
    "O3": {
        "name_en": "Baeyer-Villiger oxidation: acetone + performic acid -> methyl acetate + formic acid (acid-catalyzed)",
        "conditions_en": "peracid, inert solvent; acid-catalyzed (H3O+ written into the SMILES on both sides)",
        "mapped_reactants": "[OH2+:1]([H:10]).[CH3:2][C:3](=[O:4])[CH3:5].[CH:6](=[O:7])[O:8][O:9][H:11]",
        "steps": [
            {
                # 羰基 O 质子化：断 O1-H10，成 O4-H10
                "out": "[OH2:1].[CH3:2][C:3](=[O+:4][H:10])[CH3:5].[CH:6](=[O:7])[O:8][O:9][H:11]",
                "type": "carbonyl oxygen protonation by hydronium (PT, pre-equilibrium)",
            },
            {
                # 过甲酸端基 O9 进攻羰基 C3：成 O9-C3，断 C3=O4 π → 质子化 Criegee 四面体中间体
                "out": "[OH2:1].[CH3:2][C:3]([O:4][H:10])([CH3:5])[O+:9]([H:11])[O:8][CH:6]=[O:7]",
                "type": "performic acid terminal oxygen addition to the protonated carbonyl -> protonated Criegee tetrahedral intermediate (rate-determining per computation)",
            },
            {
                # 1,2-甲基迁移伴 O-O 断裂：断 C3-C2、O8-O9、O9-H11；成 C2-O9、O8-H11、C3=O4 π → 质子化乙酸甲酯 + 甲酸
                "out": "[OH2:1].[CH3:5][C:3](=[O+:4][H:10])[O:9][CH3:2].[CH:6](=[O:7])[O:8][H:11]",
                "type": "1,2-methyl migration to the terminal oxygen concerted with O-O cleavage and proton shuffle onto the departing formate oxygen -> protonated methyl acetate + formic acid",
            },
            {
                # 质子归还：断 O4-H10，成 O1-H10，再生 H3O+
                "out": "[OH2+:1]([H:10]).[CH3:5][C:3](=[O:4])[O:9][CH3:2].[CH:6](=[O:7])[O:8][H:11]",
                "type": "deprotonation of the ester carbonyl by water, regenerating H3O+ (PT)",
            },
        ],
    },
    # C1CO1.[OH-]>>OCC[O-]  (−1/1)  环氧碱催化开环（单步 SN2）
    "O4": {
        "name_en": "Base-catalyzed epoxide ring opening: oxirane + OH- -> 2-hydroxyethoxide",
        "conditions_en": "aqueous NaOH",
        "mapped_reactants": "[CH2:1]1[CH2:2][O:3]1.[OH-:4]",
        "steps": [
            {
                # SN2 背面进攻：成 O4-C1，断环 C1-O3
                "out": "[OH:4][CH2:1][CH2:2][O-:3]",
                "type": "SN2 backside attack of hydroxide with concerted ring C-O cleavage (trans opening, single elementary step)",
            },
        ],
    },
    # [OH3+].C1CO1.O>>[OH3+].OCCO  (+1/1)  环氧酸催化开环（A-2）
    "O5": {
        "name_en": "Acid-catalyzed epoxide ring opening (A-2): oxirane + H3O+/water -> ethylene glycol",
        "conditions_en": "dilute aqueous acid",
        "mapped_reactants": "[OH2+:1]([H:5]).[CH2:2]1[CH2:3][O:4]1.[OH:6]([H:7])",
        "steps": [
            {
                # 环氧 O 质子化：断 O1-H5，成 O4-H5
                "out": "[OH2:1].[CH2:2]1[CH2:3][O+:4]([H:5])1.[OH:6]([H:7])",
                "type": "epoxide oxygen protonation by hydronium (PT, pre-equilibrium)",
            },
            {
                # 水进攻伴环 C-O 断裂（决速）：成 O6-C2，断 C2-O4
                "out": "[OH2:1].[OH+:6]([H:7])[CH2:2][CH2:3][O:4][H:5]",
                "type": "water attack on the protonated epoxide with concerted ring C-O cleavage (rate-determining, borderline SN2)",
            },
            {
                # 去质子再生 H3O+：断 O6-H7，成 O1-H7
                "out": "[OH2+:1]([H:7]).[OH:6][CH2:2][CH2:3][O:4][H:5]",
                "type": "deprotonation of the glycol oxonium by water, regenerating H3O+ (PT)",
            },
        ],
    },
}
