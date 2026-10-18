"""Y 族 + O 族登记：Y3 异氰酸单水水解 + O3 Baeyer–Villiger。

v3（2026-09-09）收窄为两条酰基转移/氧转移网络；Y2/O2/O4/O5 剔出定稿名单留档池
（条目见 normal.md）。竞争通道按 normal.md 约定不进 gold。
"""

TASKS = {
    # 2026-10-18：NY3 槽正式换为 HNCO + 单水中性气相水解。
    # 结果已交付到 gold_compute/queue_20261018/results/NY3；当前正式 Gold 参考缺测。
    # 状态见 queue 交接，不自动安排重算；不把拟议两段路径预填为 Gold。
    "Y3": {
        "name_en": "isocyanic acid hydrolysis: HNCO + one water -> ammonia + carbon dioxide",
        "conditions_en": "gas phase, neutral closed-shell system with exactly one water molecule in total; no extra solvent, acid, counterion or catalyst; investigate carbamic-acid intermediates and connecting conformers without assuming a fixed number of elementary steps; source DOI 10.1007/s00894-010-0917-z",
        "mapped_reactants": "[NH:1]=[C:2]=[O:3].[OH2:4]",
        "steps": [],
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
