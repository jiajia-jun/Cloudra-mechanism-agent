"""X 族登记：取代/消除/取向经典竞争（X1–X4，全部单基元步）。

均为气相 F 离去基或带电离去基消除/取代，写出线即 gold 主线；竞争通道
（X1 的简并 SN2、X2 的 Hofmann 取向、X3 的甲基 SN2、X4 的逆 Cope）按
normal.md 约定不进 gold 图，由 agent 自行探索（子图打分不罚多出边）。
"""

TASKS = {
    # [F-].CC(F)C>>C=CC.F.[F-]  (−1/1)  写出线 anti-E2 → 丙烯
    "X1": {
        "name_en": "F- + 2-fluoropropane: SN2 vs E2 competition (written line: anti-E2 -> propene)",
        "conditions_en": "gas phase",
        "mapped_reactants": "[F-:1].[CH2:2]([H:6])[CH:3]([F:4])[CH3:5]",
        "steps": [
            {
                # anti-E2：断 β-C-H 与 C-F，成 H-F 与 C=C π
                "out": "[F-:1].[CH2:2]=[CH:3][CH3:5].[F:4][H:6]",
                "type": "anti-E2 elimination on secondary carbon, single step (competing identity SN2 channel is degenerate: product = reactant)",
            },
        ],
    },
    # [F-].CCC(F)C>>CC=CC.F.[F-]  (−1/1)  写出线 Zaitsev → 2-丁烯
    "X2": {
        "name_en": "F- + 2-fluorobutane E2: Zaitsev (2-butene, written line) vs Hofmann (1-butene) orientation competition",
        "conditions_en": "gas phase",
        "mapped_reactants": "[F-:1].[CH3:2][CH:3]([H:7])[CH:4]([F:5])[CH3:6]",
        "steps": [
            {
                # Zaitsev 通道：拔 3 位 H，断 C-F，成 H-F 与 C3=C4 π
                "out": "[F-:1].[CH3:2][CH:3]=[CH:4][CH3:6].[F:5][H:7]",
                "type": "anti-E2 elimination toward the more substituted alkene (Zaitsev channel); E1cb-like TS can flip orientation to Hofmann - the discrimination point",
            },
        ],
    },
    # [OH-].CC[N+](C)(C)C>>C=C.O.CN(C)C  (0/1)  Hofmann 消除
    "X3": {
        "name_en": "Hofmann elimination: ethyltrimethylammonium + OH- -> ethylene + trimethylamine + water (E2)",
        "conditions_en": "quaternary ammonium hydroxide, heated (elimination step of the classical exhaustive methylation-elimination sequence)",
        "mapped_reactants": "[OH-:1].[CH2:2]([H:8])[CH2:3][N+:4]([CH3:5])([CH3:6])[CH3:7]",
        "steps": [
            {
                # E2：OH- 拔 β-H，断 Cα-N，成 O-H 与 C=C π，NMe3 离去
                "out": "[OH:1]([H:8]).[CH2:2]=[CH2:3].[N:4]([CH3:5])([CH3:6])[CH3:7]",
                "type": "anti-E2 elimination with a charged NMe3 leaving group (competing SN2 on the N-methyl gives methanol + ethyldimethylamine)",
            },
        ],
    },
    # CC[N+](C)(C)[O-]>>C=C.CN(C)O  (0/1)  Cope 消除（syn Ei）
    "X4": {
        "name_en": "Cope elimination: N,N-dimethylethylamine N-oxide -> ethylene + N,N-dimethylhydroxylamine (syn Ei)",
        "conditions_en": "heated (classical conditions ca. 120-150 degC)",
        "mapped_reactants": "[CH2:1]([H:7])[CH2:2][N+:3]([CH3:4])([CH3:5])[O-:6]",
        "steps": [
            {
                # syn Ei 五中心环状 TS：O 拔 β-H，断 C-N，成 O-H 与 C=C π
                "out": "[CH2:1]=[CH2:2].[N:3]([CH3:4])([CH3:5])[O:6][H:7]",
                "type": "intramolecular syn Ei via a five-center cyclic TS (internal complement to the intermolecular E2 of NX3)",
            },
        ],
    },
}
