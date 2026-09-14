"""A 族 + I 族登记（v3 缩减后）：A2 丙酮自缩合 → 异亚丙基丙酮（E1cb，5 步）、
A5 Mannich 酸催化（5 步）、I1 甲醛+甲胺 → 亚胺（2 步）。

v3（2026-09-09）将本族收窄为这三条多步网络；A1/A4/A7/I3 剔出定稿名单留档池
（条目见 normal.md）。竞争通道（A5 的双烷基化等）按 normal.md 约定不进 gold。
"""

TASKS = {
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
                "barrier": 5.0,
                "weight": 0.5,
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
                "barrier": 8.9,
                "weight": 0.5,
            },
            {
                # 水拔氧鎓质子：断 O10-H11，成 O1-H11，再生 H3O+ → Mannich 碱
                "out": "[OH2+:1]([H:11]).[O:4]([H:2])([H:7]).[CH3:6][NH:5][CH2:3][CH2:8][CH:9]=[O:10]",
                "type": "water deprotonates the oxocarbenium, regenerating H3O+ -> Mannich base",
            },
        ],
    },
    # [OH-].C[N+](=O)[O-].C=CC=O>>[OH-].O=CCCC[N+](=O)[O-]  (−1/1)
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
                "barrier": 3.5,
                "weight": 0.5,
            },
            {
                # 直接脱水：断 C1-O2、断 N3-H6，成 C1=N3 pi、成 O2-H6 → 亚胺 + 水
                "out": "[O:2]([H:5])([H:6]).[CH2:1]=[N:3][CH3:4]",
                "type": "direct dehydration of the carbinolamine: C-O cleavage with the second N-H transferring to the departing oxygen -> N-methylmethanimine + water",
                "barrier": 26.7,
                "weight": 0.5,
            },
        ],
    },
    # [OH3+].COCOC.O>>[OH3+].C=O.CO.CO  (+1/1)  缩醛 A-1 水解
    # H2（H3O+ 质子，步1 转甲氧基 O4 随 MeOH 离去）、H9（水 O8 的 H，步3 接力转 O1、
}
