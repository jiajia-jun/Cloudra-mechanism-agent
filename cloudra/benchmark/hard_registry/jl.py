"""J/L 族登记（v3 缩减后）：Beckmann 肟几何→迁移基团映射（L1）。

L1 照 normal R2（丙酮肟）五步骨架，唯一差别是迁移基团为乙基；(E)-肟中乙基
与 OH 反式 → anti 乙基迁移 → N-乙基乙酰胺（立体专一，无 competing）。
v3（2026-09-09）由 20 条缩至 10 条：J1（二亚胺 syn 还原）/J2（氢硼化）/J4
（anti-E2）与 L4（Mislow–Evans [2,3]）剔出定稿名单留档池（条目见 hard.md），
registry 只留定稿条目。
"""

TASKS = {
    # [OH3+].CC/C(=N/O)/C>>[OH3+].CCNC(C)=O  (+1/1)  (E)-丁酮肟 Beckmann
    # 骨架照 normal R2（丙酮肟）五步，唯一差别：迁移基团为乙基（R2 为甲基）。
    # 映射：1=H3O+ 的 O，2=迁移质子，9/10=H3O+ 其余 H；3=肟碳上的甲基（不迁移），
    # 4=肟 C，5/11=anti 迁移乙基（CH2/CH3），6=N，7=肟 OH 的 O，8=其 H。
    # (E)-肟：乙基与 OH 反式 → 乙基 anti 迁移 → N-乙基乙酰胺；(Z)-肟是另一
    # 底物（非本底物通道），syn 甲基迁移被立体专一性排除 → 无 competing。
    "L1": {
        "name_en": "Beckmann rearrangement of (E)-butanone oxime (oxime geometry selects the migrating group -> N-ethylacetamide)",
        "conditions_en": "concentrated H2SO4 or acid catalysis, heated",
        "anchor": "barrier",
        "mapped_reactants": "[O+:1]([H:2])([H:9])[H:10].[CH3:11][CH2:5]/[C:4](=[N:6]/[O:7][H:8])/[CH3:3]",
        "steps": [
            {
                # PT：H3O+ 质子化肟 OH
                "out": "[O:1]([H:9])[H:10].[CH3:11][CH2:5]/[C:4](=[N:6]/[O+:7]([H:8])[H:2])/[CH3:3]",
                "type": "proton transfer from H3O+ to the oxime OH (leaving-group activation)",
            },
            {
                # 决速：断 N6-O7 与 C4-C5，成 C5-N6（anti 乙基迁移）与 C4≡N6 π → nitrilium + H2O
                "out": "[O:1]([H:9])[H:10].[O:7]([H:8])[H:2].[CH3:3][C:4]#[N+:6][CH2:5][CH3:11]",
                "type": "concerted Beckmann rearrangement (rate-determining): N-O cleavage with anti 1,2-ethyl migration from C to N and C-N pi bond formation -> nitrilium ion + water ((E)-oxime geometry puts the ethyl group anti to OH, so ethyl migrates)",
            },
            {
                # 水 O1 进攻 nitrilium 碳：成 C4-O1，断一根 C≡N π → O-质子化亚胺酸
                "out": "[O+:1]([H:9])([H:10])[C:4](=[N:6][CH2:5][CH3:11])[CH3:3].[O:7]([H:8])[H:2]",
                "type": "water attack on the nitrilium carbon: C-O formation with one C-N pi bond broken -> O-protonated imidic acid",
            },
            {
                # PT：另一分子水拔掉 OH2+ 的一个质子 → 中性亚胺酸 + H3O+
                "out": "[O:1]([H:10])[C:4](=[N:6][CH2:5][CH3:11])[CH3:3].[O+:7]([H:8])([H:2])[H:9]",
                "type": "proton transfer from the imidic acid OH2+ to water -> neutral imidic acid + H3O+",
            },
            {
                # 亚胺酸→酰胺互变异构：分子内 O→N 质子迁移，C=N π 断、C=O π 成
                "out": "[O:1]=[C:4]([CH3:3])[N:6]([H:10])[CH2:5][CH3:11].[O+:7]([H:8])([H:2])[H:9]",
                "type": "imidic acid -> amide tautomerization: intramolecular O-to-N proton shift with C=N pi to C=O pi migration -> N-ethylacetamide",
            },
        ],
    },
}
