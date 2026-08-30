"""A 族 + I 族登记：烯醇（盐）缩合网络（A1/A2/A4/A5/A7）与羰基-胺/缩醛化学（I1/I3）。

A1 乙醛自缩合 aldol 加成（3 步）；A2 丙酮自缩合 → 异亚丙基丙酮（E1cb 脱水，5 步）；
A4 Knoevenagel 缩合+脱羧串联（亚铵路径，二甲胺建模哌啶，5 步）；A5 Mannich 酸催化
（羟胺 → 亚铵 → 烯醇进攻 → 氧鎓去质子，5 步）；A7 硝基甲烷对丙烯醛 1,4-Michael（3 步）；
I1 甲醛+甲胺 → 亚胺（无显式催化剂，2 步）；I3 二甲氧基甲烷 A-1 水解（5 步）。
竞争通道（A1 的 E1cb 脱水、A5 的双烷基化、A7 的 1,2-加成、I3 的 A-2 等）按 normal.md
约定不进 gold。
"""

TASKS = {
    # [OH-].CC=O.CC=O>>[OH-].CC(O)CC=O  (−1/1)  乙醛自缩合 aldol 加成
    "A1": {
        "name_en": "acetaldehyde self-aldol addition -> 3-hydroxybutanal",
        "conditions_en": "dilute NaOH, water, 0-25 degC",
        "mapped_reactants": "[OH-:1].[CH2:2]([H:8])[CH:3]=[O:4].[CH3:5][CH:6]=[O:7]",
        "steps": [
            {
                "out": "[OH:1]([H:8]).[CH2:2]=[CH:3][O-:4].[CH3:5][CH:6]=[O:7]",
                "type": "enolate formation: OH- deprotonates the alpha-C (C=O pi shifts to C=C)",
            },
            {
                "out": "[OH:1]([H:8]).[CH3:5][CH:6]([O-:7])[CH2:2][CH:3]=[O:4]",
                "type": "rate-determining C-C addition: enolate carbon attacks the second aldehyde carbonyl (Burgi-Dunitz), giving the alkoxide",
            },
            {
                "out": "[OH-:1].[CH3:5][CH:6]([O:7]([H:8]))[CH2:2][CH:3]=[O:4]",
                "type": "alkoxide reprotonation by water, regenerating OH-",
            },
        ],
    },
    # [OH-].CC(=O)C.CC(=O)C>>[OH-].CC(=O)C=C(C)C.O  (−1/1)
    # 丙酮自缩合 → 异亚丙基丙酮；α-C（C2）上两个参与键变化的 H（H3 步1、H11 步4）全程显式
    "A2": {
        "name_en": "acetone self-aldol condensation -> mesityl oxide (4-methylpent-3-en-2-one)",
        "conditions_en": "NaOH or Ba(OH)2, heated",
        "mapped_reactants": "[OH-:1].[CH:2]([H:3])([H:11])[C:4](=[O:5])[CH3:6].[CH3:7][C:8](=[O:9])[CH3:10]",
        "steps": [
            {
                # OH- 拔 H3：断 C2-H3，成 O1-H3，C2-C4 1->2，C4-O5 2->1 → 烯醇盐 + 水
                "out": "[OH:1]([H:3]).[CH:2]([H:11])=[C:4]([O-:5])[CH3:6].[CH3:7][C:8](=[O:9])[CH3:10]",
                "type": "enolate formation: OH- deprotonates the alpha-C of acetone (C=O pi shifts to C=C)",
            },
            {
                # 烯醇盐 C2 进攻第二分子丙酮羰基 C8：成 C2-C8，断 C8=O9 pi、C2=C4 pi，成 C4=O5 pi → 双丙酮醇烷氧盐
                "out": "[OH:1]([H:3]).[CH3:7][C:8]([O-:9])([CH3:10])[CH:2]([H:11])[C:4](=[O:5])[CH3:6]",
                "type": "C-C addition: enolate carbon attacks the second acetone carbonyl -> diacetone alcohol alkoxide (capturable)",
            },
            {
                # 烷氧盐 O9 从水夺回 H3：断 O1-H3，成 O9-H3 → 双丙酮醇 + OH-
                "out": "[OH-:1].[CH3:7][C:8]([O:9]([H:3]))([CH3:10])[CH:2]([H:11])[C:4](=[O:5])[CH3:6]",
                "type": "alkoxide reprotonation by water -> diacetone alcohol, regenerating OH-",
            },
            {
                # E1cb 第一步：OH- 拔 C2 上另一个 alpha-H（H11）：断 C2-H11，成 O1-H11，C2-C4 1->2，C4-O5 2->1
                "out": "[OH:1]([H:11]).[CH3:7][C:8]([O:9]([H:3]))([CH3:10])[CH:2]=[C:4]([O-:5])[CH3:6]",
                "type": "E1cb deprotonation: OH- removes the alpha-H on the other side of the carbinol -> enolate + water",
            },
            {
                # 消除：断 C8-O9，成 C2=C8 pi，C2=C4 pi 回落、C4=O5 pi 重建 → 异亚丙基丙酮 + OH- + 水
                "out": "[OH:1]([H:11]).[O-:9]([H:3]).[CH3:7][C:8]([CH3:10])=[CH:2][C:4](=[O:5])[CH3:6]",
                "type": "E1cb elimination: hydroxide leaves with C=C formation (enolate collapse), giving mesityl oxide",
            },
        ],
    },
    # C=O.O=C(O)CC(=O)O.CNC>>C=CC(=O)O.C(=O)=O.O.CNC  (0/1)
    # Knoevenagel 亚铵路径；丙二酸中央 C（C3）的 H4（步2 被拔）与羧基 O7 的 H8
    # （步4 转到中央 C、步5 再转到 N）全程显式；二甲胺 N-H（H13）步1 转到甲醛 O
    "A4": {
        "name_en": "Knoevenagel condensation with decarboxylation: formaldehyde + malonic acid -> acrylic acid + CO2 + water (dimethylamine catalyst model)",
        "conditions_en": "piperidine/acetic acid catalysis (modeled here as dimethylamine CNC, written into the SMILES on both sides), reflux",
        "mapped_reactants": "[CH2:1]=[O:2].[CH:3]([H:4])([C:5](=[O:6])[O:7][H:8])[C:9](=[O:10])[OH:11].[CH3:14][N:12]([H:13])[CH3:15]",
        "steps": [
            {
                # 直接缩合（羟胺不单独成节点）：成 C1-N12（0->2），断 C1-O2（2->0），断 N12-H13，成 O2-H13 → 亚铵 + OH-
                "out": "[CH2:1]=[N+:12]([CH3:14])[CH3:15].[O-:2]([H:13]).[CH:3]([H:4])([C:5](=[O:6])[O:7][H:8])[C:9](=[O:10])[OH:11]",
                "type": "direct condensation of formaldehyde with dimethylamine -> iminium [CH2=NMe2]+ + OH- (C=N forms, C=O and N-H break, carbinolamine not a separate node)",
            },
            {
                # OH- 拔丙二酸中央 C3 的 H4：断 C3-H4，成 O2-H4 → 水 + alpha-碳负离子
                "out": "[CH2:1]=[N+:12]([CH3:14])[CH3:15].[O:2]([H:13])([H:4]).[CH-:3]([C:5](=[O:6])[O:7][H:8])[C:9](=[O:10])[OH:11]",
                "type": "OH- deprotonates the central C-H of malonic acid -> water + malonic alpha-carbanion (-1)",
            },
            {
                # 碳负离子 C3 进攻亚铵 C1：成 C1-C3，断 C1=N12 pi → 加合物 (HOOC)2CH-CH2-NMe2，电荷归 0
                "out": "[O:2]([H:13])([H:4]).[CH:3]([C:5](=[O:6])[O:7][H:8])([C:9](=[O:10])[OH:11])[CH2:1][N:12]([CH3:14])[CH3:15]",
                "type": "carbanion attacks the iminium carbon (C-C bond formation, C=N pi breaks) -> 3-(dimethylamino)malonic acid adduct",
            },
            {
                # 六元环 TS 脱羧：断 C3-C5、断 O7-H8，成 CO2 第二根 C=O（C5-O7 1->2）、成 C3-H8 → 3-(二甲氨基)丙酸 + CO2
                "out": "[O:2]([H:13])([H:4]).[O:6]=[C:5]=[O:7].[CH:3]([H:8])([C:9](=[O:10])[OH:11])[CH2:1][N:12]([CH3:14])[CH3:15]",
                "type": "decarboxylation via a six-membered cyclic TS: C-C(OOH) cleavage with concerted proton transfer from the carboxyl O-H to the central carbon -> 3-(dimethylamino)propanoic acid + CO2",
            },
            {
                # 消除二甲胺：断 C1-N12、断 C3-H8，成 C1=C3 pi、成 N12-H8 → 丙烯酸 + HNMe2
                "out": "[O:2]([H:13])([H:4]).[O:6]=[C:5]=[O:7].[CH2:1]=[CH:3][C:9](=[O:10])[OH:11].[CH3:14][N:12]([H:8])[CH3:15]",
                "type": "elimination of dimethylamine: C-N cleavage with alpha-C-H transfer onto nitrogen and C=C pi formation -> acrylic acid",
            },
        ],
    },
    # [OH3+].C=O.CN.CC=O>>[OH3+].CNCCC=O.O  (+1/1)
    # Mannich 酸催化；H2（H3O+ 的质子，步2 转给羟胺 O 随水离去）、H7（甲胺 N-H，步1 转 O）、
    # H11（乙醛 alpha-H，步3 转烯醇 O、步5 转回 H3O+）全程显式
    "A5": {
        "name_en": "Mannich reaction: formaldehyde + methylamine + acetaldehyde -> 3-(methylamino)propanal (acid-catalyzed)",
        "conditions_en": "weakly acidic water/alcohol solution (acid catalysis written as [OH3+] into the SMILES on both sides)",
        "mapped_reactants": "[OH2+:1]([H:2]).[CH2:3]=[O:4].[CH3:6][NH:5]([H:7]).[CH2:8]([H:11])[CH:9]=[O:10]",
        "steps": [
            {
                # 甲胺 N5 进攻甲醛 C1...（成 C3-N5），断 C3=O4 pi；N-H->O-H 分子内 PT 并入（断 N5-H7，成 O4-H7）→ 羟胺
                "out": "[OH2+:1]([H:2]).[O:4]([H:7])[CH2:3][NH:5][CH3:6].[CH2:8]([H:11])[CH:9]=[O:10]",
                "type": "methylamine addition to formaldehyde with merged intramolecular N-H -> O-H proton transfer -> carbinolamine",
            },
            {
                # H3O+ 质子化羟胺 O4 并脱水：断 O1-H2、成 O4-H2、断 C3-O4、成 C3=N5 pi → 亚铵 + 2 水
                "out": "[OH2:1].[O:4]([H:2])([H:7]).[CH2:3]=[NH+:5][CH3:6].[CH2:8]([H:11])[CH:9]=[O:10]",
                "type": "carbinolamine O protonation by H3O+ with dehydration -> iminium [CH2=NHMe]+ (Eschenmoser salt parent) + 2 water",
            },
            {
                # 乙醛互变异构为烯醇（净步）：断 C8-H11、断 C9=O10 pi、成 C8=C9 pi、成 O10-H11
                "out": "[OH2:1].[O:4]([H:2])([H:7]).[CH2:3]=[NH+:5][CH3:6].[CH2:8]=[CH:9][O:10][H:11]",
                "type": "acetaldehyde tautomerizes to the enol (net step: alpha-C-H breaks, C=O pi shifts to C=C, O-H forms)",
            },
            {
                # 烯醇 alpha-C（C8）进攻亚铵 C3（决速）：成 C3-C8，断 C8=C9 pi、C3=N5 pi，成 C9=O10+ pi（氧鎓，N 变中性）
                "out": "[OH2:1].[O:4]([H:2])([H:7]).[CH3:6][NH:5][CH2:3][CH2:8][CH:9]=[O+:10][H:11]",
                "type": "rate-determining C-C formation: enol alpha-carbon attacks the iminium carbon -> oxocarbenium (neutral amine)",
            },
            {
                # 水拔氧鎓质子：断 O10-H11，成 O1-H11，再生 H3O+ → Mannich 碱
                "out": "[OH2+:1]([H:11]).[O:4]([H:2])([H:7]).[CH3:6][NH:5][CH2:3][CH2:8][CH:9]=[O:10]",
                "type": "water deprotonates the oxocarbenium, regenerating H3O+ -> Mannich base",
            },
        ],
    },
    # [OH-].C[N+](=O)[O-].C=CC=O>>[OH-].O=CCCC[N+](=O)[O-]  (−1/1)
    # Michael 1,4-共轭加成；硝基 alpha-H（H6，步1 被拔、步3 转给烯醇盐 alpha-C）全程显式
    "A7": {
        "name_en": "Michael addition: nitromethane + acrolein -> 4-nitrobutanal",
        "conditions_en": "catalytic base, alcohol/water",
        "mapped_reactants": "[OH-:1].[CH2:2]([H:6])[N+:3](=[O:4])[O-:5].[CH2:7]=[CH:8][CH:9]=[O:10]",
        "steps": [
            {
                # OH- 拔硝基 alpha-H（H6）：断 C2-H6，成 O1-H6 → 水 + nitronate
                "out": "[OH:1]([H:6]).[CH2-:2][N+:3](=[O:4])[O-:5].[CH2:7]=[CH:8][CH:9]=[O:10]",
                "type": "OH- deprotonates the nitro alpha-C -> water + nitronate",
            },
            {
                # 1,4-共轭加成（决速）：nitronate C2 进攻 beta-C（C7），成 C2-C7；pi 迁移
                # （断 C7=C8 pi、断 C9=O10 pi、成 C8=C9 pi）→ 烯醇盐
                "out": "[OH:1]([H:6]).[O-:10][CH:9]=[CH:8][CH2:7][CH2:2][N+:3](=[O:4])[O-:5]",
                "type": "rate-determining 1,4-conjugate addition: nitronate carbon attacks the beta-carbon with pi shift to the enolate (1,2-addition is the competing reversible channel)",
            },
            {
                # 烯醇盐 alpha-C（C8）从水夺 H6：断 O1-H6、成 C8-H6，断 C8=C9 pi、成 C9=O10 pi → 4-硝基丁醛 + OH-
                "out": "[OH-:1].[O:10]=[CH:9][CH:8]([H:6])[CH2:7][CH2:2][N+:3](=[O:4])[O-:5]",
                "type": "enolate reprotonation at the alpha-carbon by water -> 4-nitrobutanal, regenerating OH-",
            },
        ],
    },
    # C=O.CN>>C=NC.O  (0/1)  亚胺形成（无显式催化剂）；甲胺两个 N-H（H5/H6）均参与键变化，全程显式
    "I1": {
        "name_en": "imine formation: formaldehyde + methylamine -> N-methylmethanimine + water",
        "conditions_en": "optimal around pH 4-6 (bell-shaped rate profile)",
        "mapped_reactants": "[CH2:1]=[O:2].[CH3:4][N:3]([H:5])([H:6])",
        "steps": [
            {
                # 加成 + 分子内 PT 并入：成 C1-N3，断 C1=O2 pi、断 N3-H5、成 O2-H5 → 羟胺 HOCH2NHMe
                "out": "[O:2]([H:5])[CH2:1][N:3]([H:6])[CH3:4]",
                "type": "amine addition to the carbonyl with merged intramolecular N-H -> O-H proton transfer -> carbinolamine (capturable)",
            },
            {
                # 直接脱水：断 C1-O2、断 N3-H6，成 C1=N3 pi、成 O2-H6 → 亚胺 + 水
                "out": "[O:2]([H:5])([H:6]).[CH2:1]=[N:3][CH3:4]",
                "type": "direct dehydration of the carbinolamine: C-O cleavage with the second N-H transferring to the departing oxygen -> N-methylmethanimine + water",
            },
        ],
    },
    # [OH3+].COCOC.O>>[OH3+].C=O.CO.CO  (+1/1)  缩醛 A-1 水解
    # H2（H3O+ 质子，步1 转甲氧基 O4 随 MeOH 离去）、H9（水 O8 的 H，步3 接力转 O1、
    # 步4 转甲氧基 O6 随第二分子 MeOH 离去）、H10（水 O8 另一 H，步5 转回 O1 再生 H3O+）全程显式
    "I3": {
        "name_en": "acetal hydrolysis (A-1 mechanism): dimethoxymethane + H3O+/water -> formaldehyde + 2 methanol",
        "conditions_en": "dilute aqueous acid",
        "mapped_reactants": "[OH2+:1]([H:2]).[CH3:5][O:4][CH2:3][O:6][CH3:7].[O:8]([H:9])([H:10])",
        "steps": [
            {
                # 一个甲氧基 O4 质子化：断 O1-H2，成 O4-H2（H3O+ -> H2O）
                "out": "[OH2:1].[CH3:5][O+:4]([H:2])[CH2:3][O:6][CH3:7].[O:8]([H:9])([H:10])",
                "type": "methoxy oxygen protonation by hydronium (PT, pre-equilibrium)",
            },
            {
                # C-O 断裂（决速）：断 C3-O4，成 C3=O6 pi → 氧碳鎓 [CH2=O(Me)]+ + 第一分子 MeOH
                "out": "[OH2:1].[CH3:5][O:4][H:2].[CH2:3]=[O+:6][CH3:7].[O:8]([H:9])([H:10])",
                "type": "rate-determining C-O cleavage -> oxocarbenium [CH2=O(Me)]+ + methanol (A-1 unimolecular cleavage of the conjugate acid)",
            },
            {
                # 水 O8 进攻氧碳鎓 C3 + 另一分子水（O1）接力去质子：成 C3-O8，断 C3=O6 pi、
                # 断 O8-H9、成 O1-H9 → 半缩醛 CH3OCH2OH + H3O+
                "out": "[OH2+:1]([H:9]).[CH3:5][O:4][H:2].[CH3:7][O:6][CH2:3][O:8]([H:10])",
                "type": "water attack on the oxocarbenium with relay deprotonation by the second water -> hemiacetal + H3O+",
            },
            {
                # 半缩醛甲氧基 O6 质子化：断 O1-H9，成 O6-H9（PT）
                "out": "[OH2:1].[CH3:5][O:4][H:2].[CH3:7][O+:6]([H:9])[CH2:3][O:8]([H:10])",
                "type": "hemiacetal methoxy oxygen protonation by hydronium (PT, pre-equilibrium)",
            },
            {
                # 断 C3-O6、断 O8-H10，成 C3=O8 pi、成 O1-H10（再生 H3O+）→ 甲醛 + 第二分子 MeOH
                "out": "[OH2+:1]([H:10]).[CH3:5][O:4][H:2].[CH3:7][O:6][H:9].[CH2:3]=[O:8]",
                "type": "second C-OMe cleavage with C=O pi formation and proton return to water, regenerating H3O+ -> formaldehyde + methanol",
            },
        ],
    },
}
