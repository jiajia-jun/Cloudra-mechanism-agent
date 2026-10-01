"""Y 族 + O 族登记（v3 缩减后）：Y3 甲酸甲酯 BAC2 皂化 + O3 Baeyer–Villiger。

v3（2026-09-09）收窄为两条酰基转移/氧转移网络；Y2/O2/O4/O5 剔出定稿名单留档池
（条目见 normal.md）。竞争通道按 normal.md 约定不进 gold。
"""

TASKS = {
    # [OH-].COC=O>>O=C[O-].CO  (−1/1)  BAC2 皂化
    "Y3": {
        "name_en": "Ester saponification: methyl formate + NaOH -> sodium formate + methanol",
        "conditions_en": "aqueous NaOH",
        # 2026-09-25 用户裁决：裸 OH⁻ 在 CPCM 里无对离子制衡、加成必跑成无垒
        # （模型失真），改为 Na⁺ 制衡的中性模型（总电荷 0）重算全图。
        # Na⁺ 在 SMILES 里作游离组分（映射号 7），不参与键变化跟踪；
        # 计算中的真实配位位置由 agent 自决。三步能垒待 Na 模型战役回填；
        # 旧值（15.5 文献 ΔG 裸离子 / 12.5、0.0 裸离子自算）全部作废。
        "mapped_reactants": "[Na+:7].[O-:1][H:6].[CH3:2][O:3][CH:4]=[O:5]",
        "steps": [
            {
                # OH- 加成：成 O1-C4，断 C4=O5 π → 四面体烷氧盐（Na+ 旁观）
                "out": "[Na+:7].[CH3:2][O:3][CH:4]([O:1][H:6])[O-:5]",
                "type": "hydroxide addition to the carbonyl carbon -> tetrahedral alkoxide intermediate (capturable; Na+ counterion present)",
            },
            {
                # 消除 MeO-：断 C4-O3，成 C4=O5 π → 甲酸 + 甲醇盐（Na+ 旁观）
                "out": "[Na+:7].[CH3:2][O-:3].[CH:4](=[O:5])[O:1][H:6]",
                "type": "methoxide elimination: C-OMe cleavage with C=O pi reformation -> formic acid + methoxide (Na+ counterion present)",
            },
            {
                # 质子转移：断 O1-H6，成 O3-H6 → 甲酸根 + 甲醇（Na+ 旁观）
                "out": "[Na+:7].[CH3:2][O:3][H:6].[CH:4](=[O:5])[O-:1]",
                "type": "proton transfer from formic acid to methoxide -> formate + methanol (Na+ counterion present)",
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
                "barrier": 0.0,
            },
            {
                # 过甲酸端基 O9 进攻羰基 C3：成 O9-C3，断 C3=O4 π → 质子化 Criegee 四面体中间体
                "out": "[OH2:1].[CH3:2][C:3]([O:4][H:10])([CH3:5])[O+:9]([H:11])[O:8][CH:6]=[O:7]",
                "type": "performic acid terminal oxygen addition to the protonated carbonyl -> protonated Criegee tetrahedral intermediate (rate-determining per computation)",
                "barrier": 14.3,
                "weight": 1.0,
            },
            {
                # 1,2-甲基迁移伴 O-O 断裂：断 C3-C2、O8-O9、O9-H11；成 C2-O9、O8-H11、C3=O4 π → 质子化乙酸甲酯 + 甲酸
                "out": "[OH2:1].[CH3:5][C:3](=[O+:4][H:10])[O:9][CH3:2].[CH:6](=[O:7])[O:8][H:11]",
                "type": "1,2-methyl migration to the terminal oxygen concerted with O-O cleavage and proton shuffle onto the departing formate oxygen -> protonated methyl acetate + formic acid",
                "barrier": 11.4,
                "weight": 1.0,
            },
            {
                # 质子归还：断 O4-H10，成 O1-H10，再生 H3O+
                "out": "[OH2+:1]([H:10]).[CH3:5][C:3](=[O:4])[O:9][CH3:2].[CH:6](=[O:7])[O:8][H:11]",
                "type": "deprotonation of the ester carbonyl by water, regenerating H3O+ (PT)",
                "barrier": 0.332,
            },
        ],
    },
}
