"""Q 族 + H 族登记（v4 换血后）：芳香 Claisen（Q1）与 oxy-Cope（Q5，v4 新收）。

含芳香环：反应物/产物一律芳香写法（[cH]/[o]），[3,3] 去芳构化中间体
（邻位环己二烯酮）用 Kekulé 写法——芳香键级 1.5 与单/双键之间的变化由生成器
自动推导为去芳构化/再芳构化的 break/form 信号。

Q1（芳香 Claisen，v3 新收）：烯丙基苯基醚 → 2-烯丙基苯酚，两步：① [3,3]-σ 迁移 →
邻位环己二烯酮（去芳构化、可捕获）；② 烯醇-酚互变异构恢复芳香性。竞争（对位
重排/船式 TS）按 normal.md 约定不进 gold。v3（2026-09-09）将本档收窄为仅 Q1，
原 Q2/Q3/H1-H3/H5 条目剔出定稿名单留档池（条目见 normal.md）。

Q5（oxy-Cope，v4 新收 2026-09-25）：1,5-己二烯-3-醇 → 5-己烯醛，两步：① [3,3]-σ
迁移（椅式 TS 优先）→ 烯醇中间体；② 烯醇 → 醛互变异构。第 2 步是质子转移（PT）
边，按 2026-09-25 PT 边规则留在图里但不挂参考垒；第 1 步已回填自算参考垒。
竞争（船式 TS、分步双自由基）按约定不进 gold。
"""

TASKS = {
    # C=CCOc1ccccc1>>C=CCc1ccccc1O  (0/1)  芳香 Claisen（2 步）
    # 映射：1=烯丙基端基 CH2，2=CH，3=烯丙基 CH2（原连 O），4=醚 O；
    # 5=ipso 芳碳（原连 O4，成酮碳），6=邻位芳碳（接烯丙基），7-10=其余环碳，
    # 14=邻位芳碳原 H（互变时迁到 O4 成酚 OH）。
    "Q1": {
        "name_en": "aromatic Claisen rearrangement: allyl phenyl ether -> 2-allylphenol",
        "conditions_en": "gas phase; thermal, ~200 degC",
        "mapped_reactants": "[CH2:1]=[CH:2][CH2:3][O:4][c:5]1[c:6]([H:14])[cH:7][cH:8][cH:9][cH:10]1",
        "steps": [
            {
                # [3,3]：断 O4-C3 与芳环原 ipso-邻位 π 耦合，成 C1-C6（烯丙基末端到邻位），
                # O4 留在原 ipso 碳 C5 上成羰基 → 邻位环己二烯酮（去芳构化）
                "out": "[CH2:3]=[CH:2][CH2:1][C:6]1([H:14])[CH:7]=[CH:8][CH:9]=[CH:10][C:5](=[O:4])1",
                "type": "[3,3]-sigmatropic rearrangement (allyl vinyl ether substructure): O-allyl bond cleavage with allyl migration to the ortho carbon and dearomatization to the ortho-cyclohexadienone (capturable intermediate)",
                "barrier": 37.75,
            },
            {
                # 烯醇-酚互变异构：C6-H14 迁到羰基 O4，环 π 回排恢复芳香 → 2-烯丙基苯酚
                "out": "[CH2:3]=[CH:2][CH2:1][c:6]1[cH:7][cH:8][cH:9][cH:10][c:5]1[O:4][H:14]",
                "type": "keto-enol tautomerization of the ortho-cyclohexadienone: proton migration from the ring sp3 carbon onto the carbonyl oxygen restores aromaticity -> 2-allylphenol",
                "barrier": 53.3,
            },
        ],
    },
    # C=CC(O)CC=C>>O=CCCCC=C  (0/1)  oxy-Cope + 互变异构
    "Q5": {
        "name_en": "oxy-Cope rearrangement: 1,5-hexadien-3-ol -> hex-5-enal ([3,3] then enol-keto tautomerization)",
        "conditions_en": "gas phase, heated",
        "mapped_reactants": "[CH2:1]=[CH:2][CH:3]([O:7][H:8])[CH2:4][CH:5]=[CH2:6]",
        "steps": [
            {
                # 骨架为 [3,3] 判定的 C3=C2-C1-C6-C5=C4（断 C3-C4、成 C1-C6）：
                # 烯醇 = C3(OH)=C2 双键 + C3 原 carbinol H，闭壳
                "out": "[CH:3]([O:7][H:8])=[CH:2][CH2:1][CH2:6][CH:5]=[CH2:4]",
                "type": "[3,3]-sigmatropic shift (chair TS preferred) -> hex-5-enal enol intermediate",
                "barrier": 30.96,
            },
            {
                # 2026-09-25 PT 边规则：质子转移步保留在图里但不挂参考垒、gold 战役不花算力
                "out": "[O:7]=[CH:3][CH:2]([H:8])[CH2:1][CH2:6][CH:5]=[CH2:4]",
                "type": "enol -> aldehyde tautomerization (intramolecular proton transfer; barrier deliberately unanchored per 2026-09-25 PT-edge rule)",
            },
        ],
    },
}
