"""F/G/K 族登记：Henbest 导向环氧化（F1）+ 椅式 TS 周环/aldol 立体选择性（G1/G2/K1）。

F1/G1/G2 为 anchor="selectivity" 题：主线 = 优势面/椅式通道，competing = 同一起点
（反应物络合物）经劣势 TS 到非对映副产物，能垒格数值为竞争 TS 能垒差 ΔΔ。
K1 池内能垒格无数值（dr >95:5 定性），登记 anchor=None，副通道图结构照常。

键变化均由生成器从相邻步映射 SMILES 差集推导（禁止手填），化学口径：
- F1 蝶形 TS 一体完成 O 转移与过酸内质子迁移：断 C=C π / O–O / 端基 O–H
  （显式 [H:12]），成两个环氧 C–O 与羧酸 O–H（派生 break [3,4],[10,11],[11,12]；
  form [3,11],[4,11],[10,12]）。
- G1 Cope [3,3]：同 easy P1 口径——断两个端基 π 与中央 σ（注意 Cope 断的是
  3-4 σ，本登记映射号 3-5），成端基间新 σ 与两个内移 π（break [1,2],[3,5],[7,8]；
  form [1,8],[2,3],[5,7]）。
- G2 Claisen [3,3]：同 easy P3 口径——断两个 π 与 C–O σ，成端碳间新 C–C σ、
  迁移 π 与 C=O π（break [2,3],[4,5],[6,7]；form [2,7],[3,4],[5,6]）；两个甲基
  （映射 1/8）为旁观取代基。
- K1 Zimmerman–Traxler 椅式 aldol：断烯醇 C=C π、醛 C=O π 与烯醇侧 O–B，成
  α-C→醛碳新 C–C、烷氧盐 O→B 新 O–B 与烯醇侧新 C=O π（break [2,3],[4,5],[7,8]；
  form [2,7],[3,4],[5,8]）。硼写作 [BH2:n]——裸 [B:n] 去映射后是零氢 bracket
  原子，与池内有机子集 B 规范化不等。
"""

TASKS = {
    # OC1C=CCCC1.O=COO>>O[C@H]1[C@H]2O[C@H]2CCC1.O=CO  (0/1)
    # 烯丙位 OH 氢键缔合导向 syn 面环氧化（Henbest），主产物 cis（OH 与环氧同侧，
    # 池内 3D 嵌入已核对）；副通道 = 非导向面 → trans。
    "F1": {
        "name_en": "cyclohex-2-en-1-ol peracid epoxidation (Henbest hydrogen-bond-directed, cis)",
        "conditions_en": "performic or perbenzoic acid, CH2Cl2 or benzene, 0-25 degC",
        "anchor": "selectivity",
        "minor_channel_en": "undirected opposite-face epoxidation -> trans-2,3-epoxycyclohexanol",
        "mapped_reactants": "[OH:2][CH:1]1[CH:3]=[CH:4][CH2:5][CH2:6][CH2:7]1.[O:9]=[CH:8][O:10][O:11][H:12]",
        "steps": [
            {
                "out": "[OH:2][C@H:1]1[C@H:3]2[O:11][C@H:4]2[CH2:5][CH2:6][CH2:7]1.[O:9]=[CH:8][O:10][H:12]",
                "type": "concerted epoxidation via butterfly TS, allylic OH...OOH hydrogen bond directs O delivery to the syn face: O-O and terminal O-H cleavage with internal proton transfer to the carbonyl-side oxygen, C=C pi cleavage, two epoxide C-O formations -> cis-2,3-epoxycyclohexanol",
            },
        ],
        "competing": [
            {
                "out": "[OH:2][C@H:1]1[C@@H:3]2[O:11][C@H:4]2[CH2:5][CH2:6][CH2:7]1.[O:9]=[CH:8][O:10][H:12]",
                "type": "same concerted epoxidation on the undirected (opposite) face -> trans-2,3-epoxycyclohexanol (minor channel)",
            },
        ],
    },
    # C=C[C@H](C)[C@H](C)C=C>>C/C=C\CC/C=C/C  (0/1)  meso (3S,4R) 底物椅式
    # 立体专一 → (2E,6Z)-辛-2,6-二烯（对称分子 (E,Z)≡(Z,E)，池内 RDKit 已核对）；
    # 副通道 = 船式 TS → (E,E)（另一条船式给 (Z,Z)，step type 中注明）。
    "G1": {
        "name_en": "meso-3,4-dimethyl-1,5-hexadiene Cope rearrangement (chair TS stereospecificity)",
        "conditions_en": "gas-phase pyrolysis, ~200-250 degC",
        "anchor": "selectivity",
        "minor_channel_en": "boat TS -> (E,E)-octa-2,6-diene",
        "mapped_reactants": "[CH2:1]=[CH:2][C@H:3]([CH3:4])[C@H:5]([CH3:6])[CH:7]=[CH2:8]",
        "steps": [
            {
                "out": "[CH3:4]/[CH:3]=[CH:2]\\[CH2:1][CH2:8]/[CH:7]=[CH:5]/[CH3:6]",
                "type": "[3,3]-sigmatropic Cope rearrangement via chair TS: central C3-C4 sigma and two terminal pi cleavages, new terminal-terminal sigma and two inward-migrated pi bonds -> (2E,6Z)-octa-2,6-diene",
            },
        ],
        "competing": [
            {
                "out": "[CH3:4]/[CH:3]=[CH:2]/[CH2:1][CH2:8]/[CH:7]=[CH:5]/[CH3:6]",
                "type": "Cope via boat TS -> (E,E)-octa-2,6-diene (minor channel; the alternative boat conformer gives (Z,Z))",
            },
        ],
    },
    # C/C=C/CO/C=C/C>>C=C[C@H](C)[C@H](C)C=O  (0/1)  (E,E) 底物椅式（双甲基假
    # 赤道）→ syn = (2S,3S) 型（池内经 Fischer-CIP 推导核对）；副通道 = 船式 → anti。
    "G2": {
        "name_en": "(E,E)-crotyl propenyl ether Claisen rearrangement (chair preference, syn)",
        "conditions_en": "thermal, ~150-200 degC",
        "anchor": "selectivity",
        "minor_channel_en": "boat TS -> anti-2,3-dimethylpent-4-enal",
        "mapped_reactants": "[CH3:1]/[CH:2]=[CH:3]/[CH2:4][O:5]/[CH:6]=[CH:7]/[CH3:8]",
        "steps": [
            {
                "out": "[CH2:4]=[CH:3][C@H:2]([CH3:1])[C@H:7]([CH3:8])[CH:6]=[O:5]",
                "type": "[3,3]-sigmatropic Claisen rearrangement via chair TS with both methyls pseudo-equatorial: allyl/vinyl pi and C-O sigma cleavage, new terminal C-C sigma between the two methyl-bearing termini, migrated allyl pi and C=O pi formation -> syn-2,3-dimethylpent-4-enal",
            },
        ],
        "competing": [
            {
                "out": "[CH2:4]=[CH:3][C@H:2]([CH3:1])[C@@H:7]([CH3:8])[CH:6]=[O:5]",
                "type": "Claisen via boat TS -> anti-2,3-dimethylpent-4-enal (minor channel)",
            },
        ],
    },
    # C/C=C\OB.CC=O>>C[C@@H](OB)[C@@H](C)C=O  (0/1)  (Z)-硼烯醇盐椅式
    # Zimmerman–Traxler（甲基假赤道）→ syn = (2R,3R) 型（池内经 Fischer-CIP 推导
    # 核对）；副通道 = 船式/扭船式 → anti。
    "K1": {
        "name_en": "(Z)-propanal boron enolate + acetaldehyde aldol (Zimmerman-Traxler chair, Z(O)->syn)",
        "conditions_en": "boron enolate model (gas phase / inert solvent computation target)",
        # 池内能垒格"能垒数值未核"（只有 dr >95:5 的定性锚点）——按框架 fail-loud
        # 规则登记 anchor=None（accuracy disable）；minor_channel_en 留档备查。
        "anchor": None,
        "minor_channel_en": "boat/twist-boat TS -> anti aldol boronate",
        "mapped_reactants": "[CH3:1]/[CH:2]=[CH:3]\\[O:4][BH2:5].[CH3:6][CH:7]=[O:8]",
        "steps": [
            {
                "out": "[CH3:6][C@@H:7]([O:8][BH2:5])[C@@H:2]([CH3:1])[CH:3]=[O:4]",
                "type": "concerted aldol via six-membered Zimmerman-Traxler chair TS (aldehyde methyl pseudo-equatorial): enol C=C pi, aldehyde C=O pi and enol-side O-B cleavage; new alpha-C to aldehyde-C bond, new alkoxide-O to B bond and enol-side C=O pi formation -> syn-3-(boryloxy)-2-methylbutanal boronate",
            },
        ],
        "competing": [
            {
                "out": "[CH3:6][C@@H:7]([O:8][BH2:5])[C@H:2]([CH3:1])[CH:3]=[O:4]",
                "type": "aldol via boat/twist-boat TS -> anti aldol boronate (minor channel)",
            },
        ],
    },
}
