"""J/L 族登记（v3 缩减后）：Beckmann 肟几何→迁移基团映射（L1）。

L1 由四步组成，含已验证的 O-质子化亚胺酸水合中间体；(E)-肟中乙基
与 OH 反式 → anti 乙基迁移 → N-乙基乙酰胺（立体专一，无 competing）。
v3（2026-09-09）由 20 条缩至 10 条：J1（二亚胺 syn 还原）/J2（氢硼化）/J4
（anti-E2）与 L4（Mislow–Evans [2,3]）剔出定稿名单留档池（条目见 hard.md），
registry 只留定稿条目。
"""

TASKS = {
    # [OH3+].CC/C(=N/O)/C>>CCNC(C)=[OH+].O  (+1/1)  (E)-丁酮肟 Beckmann
    # 四步骨架：OH 质子化、anti 乙基迁移、水加成、O→N 质子转移。
    # 映射：1=H3O+ 的 O，2=迁移质子，9/10=H3O+ 其余 H；3=肟碳上的甲基（不迁移），
    # 4=肟 C，5/11=anti 迁移乙基（CH2/CH3），6=N，7=肟 OH 的 O，8=其 H。
    # (E)-肟：乙基与 OH 反式 → 乙基 anti 迁移 → N-乙基乙酰胺；(Z)-肟是另一
    # 底物（非本底物通道），syn 甲基迁移被立体专一性排除 → 无 competing。
    "L1": {
        "name_en": "Beckmann rearrangement of (E)-butanone oxime: determine which group migrates",
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
                "barrier": 23.13,
                "weight": 0.5,
            },
            {
                # ORCA 6.1.1 气相无约束 TS/频率、IRC 31 与端点 42/43 验证。
                # I3prime 是 O-质子化亚胺酸+水的真实极小值（job 9），
                # 并非先前未成功优化的旧 I3/I4 初猜。证据见 hard_hl1_2026-10-01.md。
                "out": "[O+:1]([H:9])([H:10])[C:4]([CH3:3])=[N:6][CH2:5][CH3:11].[O:7]([H:8])[H:2]",
                "type": "water addition to nitrilium with C-N triple-to-double bond reduction -> stable O-protonated imidic acid plus water",
                "barrier": 10.44,
            },
            {
                # TS 37/IRC 44/端点 46、47；采用较低 P 构象（job 46）。
                # ΔE‡ 相对 I3prime job 9；不是反应能，也不混减旧 ORCA 能量。
                "out": "[O+:1]([H:9])=[C:4]([CH3:3])[N:6]([H:10])[CH2:5][CH3:11].[O:7]([H:8])[H:2]",
                "type": "O-to-N proton transfer with C-O double bond formation and C-N double-to-single bond reduction -> O-protonated N-ethylacetamide plus water",
                "barrier": 13.46,
            },
        ],
    },
}
