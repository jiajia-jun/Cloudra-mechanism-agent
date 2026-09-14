"""D/E 族登记（v3 缩减后）：D2 环氧开环立体专一 + E2/E3 羰基 π-面选择性。

D2 为立体专一体（构象锁死，无竞争通道进 gold）；E2/E3 均为单基元步氢负
转移的面选择性竞争题：主线 = 优势面，competing = 另一面（同一反应物络合物
出发，产物互为非对映体/对映体）。转移的 H 一律显式 [H:2]（map 2）。
v3（2026-09-09）由 20 条缩至 10 条：E1（Felkin–Anh π-面，ΔΔ 0.7–0.9 过小）
剔出定稿名单留档池（条目见 hard.md），registry 只留定稿条目。

芳香环映射约定：带 H 的芳香碳写 [cH:n]，取代的 ipso 碳写 [c:n]——[c:n]
（无 H 计数）或 Kekulé [C:n] 写法在去映射规范化后与池内 SMILES 不一致，已
实测排除。BH4- 写 [BH3-:1]([H:2])（去映射 canon = [BH4-]），BH3 写
[BH2:1]([H:2])（canon = B），产物侧游离 BH3 写 [BH3:1]（裸 [B:n] 去映射后
canon 为 [B]，不等于池内 B，已实测排除）。

E3 归属核对：池写 (S)-催化剂 → (R)-烷氧基硼烷，与 Corey 助记一致
（(S)-oxazaborolidine 催化 BH3 还原苯乙酮实验给 (R)-1-苯乙醇 96–97% ee，
六元环椅式 TS 中 BH3 配位 N、酮氧配位催化剂 B，氢负从位阻较小面——Si
面——转移），无异议。
"""

TASKS = {
    # C1CCC2OC2C1.[OH-]>>O[C@@H]1CCCC[C@H]1[O-]  (−1/1)  trans-1,2-环己二醇盐 (1R,2R)
    # 单基元步：OH- 背面 SN2 进攻环氧碳 C2，断 C2-O3，成 O1-C2；C4 保留环氧氧成
    # 烷氧负离子。椅式构象锁定下反式双轴向开环唯一，cis/双赤道为禁阻背景通道，
    # 不进 gold（无 competing）。池产物 CIP 已核对 = (1R,2R)。
    "D2": {
        "name_en": "cyclohexene oxide + hydroxide: determine the stereochemical outcome of the SN2 epoxide opening",
        "conditions_en": "aqueous NaOH, heat",
        "anchor": "barrier",
        "mapped_reactants": "[OH-:1].[O:3]1[CH:4]2[CH2:8][CH2:7][CH2:6][CH2:5][CH:2]12",
        "steps": [
            {
                "out": "[OH:1][C@@H:2]1[CH2:5][CH2:6][CH2:7][CH2:8][C@H:4]1[O-:3]",
                "type": "backside SN2 attack of hydroxide on one epoxide carbon, trans-diaxial ring opening with C-O cleavage at the attacked carbon -> trans-1,2-diolate (stereospecific, no competing channel)",
                "barrier": 14.3,
                "weight": 0.5,
            },
        ],
    },
    # [BH4-].CC(C)(C)C1CCC(=O)CC1>>CC(C)(C)[C@H]1CC[C@H]([O-])CC1.B  (−1/1)
    # 构象锁定环己酮：小亲核试剂轴向进攻占优（扭转应变控制，Wu–Houk），H2 落轴向、
    # 烷氧盐 O- 落赤道 → trans（与赤道 tBu 反式）为主；赤道进攻给轴向烷氧盐 = cis。
    # 断 B1-H2 与 C10=O11 π，成 C10-H2。两"手性中心"实为对称非手性中心，@ 标记
    # 只编码 cis/trans（RDKit CIP 判定为非立体中心，符合预期）。
    "E2": {
        "name_en": "4-tert-butylcyclohexanone borohydride reduction: axial vs equatorial attack on a conformationally locked ketone",
        "conditions_en": "LiAlH4/Et2O or NaBH4/alcohol",
        "anchor": "selectivity",
        "minor_channel_en": "equatorial hydride attack -> cis-4-tert-butylcyclohexan-1-olate (axial alkoxide)",
        "mapped_reactants": "[BH3-:1]([H:2]).[CH3:3][C:4]([CH3:5])([CH3:6])[CH:7]1[CH2:8][CH2:9][C:10](=[O:11])[CH2:12][CH2:13]1",
        "steps": [
            {
                "out": "[CH3:3][C:4]([CH3:5])([CH3:6])[C@H:7]1[CH2:8][CH2:9][C@:10]([H:2])([O-:11])[CH2:12][CH2:13]1.[BH3:1]",
                "type": "axial hydride attack on the locked chair (torsional-strain control for the small hydride donor) -> equatorial alkoxide = trans-4-tert-butylcyclohexan-1-olate",
                "barrier": 16.1,
                "weight": 1.0,
                "channel": "axial_attack",
            },
        ],
        "competing": [
            {
                "out": "[CH3:3][C:4]([CH3:5])([CH3:6])[C@H:7]1[CH2:8][CH2:9][C@@:10]([H:2])([O-:11])[CH2:12][CH2:13]1.[BH3:1]",
                "type": "equatorial hydride attack -> axial alkoxide = cis diastereomer (minor channel)",
                "barrier": 17.3,
                "weight": 1.0,
                "channel": "equatorial_attack",
            },
        ],
    },
    # B.CC(=O)c1ccccc1.C[C@H]1COBN1>>C[C@@H](OB)c1ccccc1.C[C@H]1COBN1  (0/1)
    # CBS 简化模型：断 B1-H2 与 C4=O5 π，成 C4-H2 与 O5-B1（烷氧基硼烷）；催化剂
    # (S)-5-甲基氧氮硼杂环戊烷（map 12-17）两侧原样旁观。(S)-催化剂 → Si 面转移 →
    # (R)-产物（Corey 助记，与实验 96-97% ee 一致，无异议）；副通道 Re 面 → (S)。
    "E3": {
        "name_en": "CBS reduction of acetophenone, simplified model: (S)-5-methyl-oxazaborolidine-catalyzed BH3 enantioface selection",
        "conditions_en": "THF, -20 degC to rt, catalytic (S)-oxazaborolidine with BH3",
        "anchor": "selectivity",
        "minor_channel_en": "hydride delivery to the opposite (Re) face -> (S)-1-phenylethoxyborane enantiomer",
        "mapped_reactants": "[BH2:1]([H:2]).[CH3:3][C:4](=[O:5])[c:6]1[cH:7][cH:8][cH:9][cH:10][cH:11]1.[CH3:12][C@H:13]1[CH2:14][O:15][BH:16][NH:17]1",
        "steps": [
            {
                "out": "[CH3:3][C@@:4]([H:2])([O:5][BH2:1])[c:6]1[cH:7][cH:8][cH:9][cH:10][cH:11]1.[CH3:12][C@H:13]1[CH2:14][O:15][BH:16][NH:17]1",
                "type": "single-step hydride transfer from N-coordinated BH3 to the Si face of B-coordinated acetophenone via the six-membered chair TS ((S)-catalyst -> (R)-alkoxyborane, Corey mnemonic); oxazaborolidine catalyst is a spectator",
                "channel": "si_face",
            },
        ],
        "competing": [
            {
                "out": "[CH3:3][C@:4]([H:2])([O:5][BH2:1])[c:6]1[cH:7][cH:8][cH:9][cH:10][cH:11]1.[CH3:12][C@H:13]1[CH2:14][O:15][BH:16][NH:17]1",
                "type": "hydride delivery to the opposite (Re) face -> (S)-alkoxyborane enantiomer (minor channel)",
                "channel": "re_face",
            },
        ],
    },
}
