"""F/G/K 族登记（v3 缩减后）：Henbest 导向环氧化（F1）+ Claisen 椅式立体选择性（G2）。

F1/G2 为 anchor="selectivity" 题：主线 = 优势面/椅式通道，competing = 同一起点
（反应物络合物）经劣势 TS 到非对映副产物，能垒格数值为竞争 TS 能垒差 ΔΔ。
v3（2026-09-09）由 20 条缩至 10 条：G1（meso-Cope 椅/船，TS 边缘 MR）与
K1（Z–T 硼 aldol）剔出定稿名单留档池（条目见 hard.md），registry 只留定稿条目。

键变化均由生成器从相邻步映射 SMILES 差集推导（禁止手填），化学口径：
- F1 蝶形 TS 一体完成 O 转移与过酸内质子迁移：断 C=C π / O–O / 端基 O–H
  （显式 [H:12]），成两个环氧 C–O 与羧酸 O–H（派生 break [3,4],[10,11],[11,12]；
  form [3,11],[4,11],[10,12]）。
- G2 Claisen [3,3]：同 easy P3 口径——断两个 π 与 C–O σ，成端碳间新 C–C σ、
  迁移 π 与 C=O π（break [2,3],[4,5],[6,7]；form [2,7],[3,4],[5,6]）；两个甲基
  （映射 1/8）为旁观取代基。
"""

TASKS = {
    # OC1C=CCCC1.O=COO>>O[C@H]1[C@H]2O[C@H]2CCC1.O=CO  (0/1)
    # 烯丙位 OH 氢键缔合导向 syn 面环氧化（Henbest），主产物 cis（OH 与环氧同侧，
    # 池内 3D 嵌入已核对）；副通道 = 非导向面 → trans。
    "F1": {
        "name_en": "cyclohex-2-en-1-ol peracid epoxidation: determine the diastereoselectivity",
        "conditions_en": "performic or perbenzoic acid, CH2Cl2 or benzene, 0-25 degC",
        "anchor": "selectivity",
        "minor_channel_en": "undirected opposite-face epoxidation -> trans-2,3-epoxycyclohexanol",
        "mapped_reactants": "[OH:2][CH:1]1[CH:3]=[CH:4][CH2:5][CH2:6][CH2:7]1.[O:9]=[CH:8][O:10][O:11][H:12]",
        "steps": [
            {
                "out": "[OH:2][C@H:1]1[C@H:3]2[O:11][C@H:4]2[CH2:5][CH2:6][CH2:7]1.[O:9]=[CH:8][O:10][H:12]",
                "type": "concerted epoxidation via butterfly TS, allylic OH...OOH hydrogen bond directs O delivery to the syn face: O-O and terminal O-H cleavage with internal proton transfer to the carbonyl-side oxygen, C=C pi cleavage, two epoxide C-O formations -> cis-2,3-epoxycyclohexanol",
                "channel": "directed_face",
            },
        ],
        "competing": [
            {
                "out": "[OH:2][C@H:1]1[C@@H:3]2[O:11][C@H:4]2[CH2:5][CH2:6][CH2:7]1.[O:9]=[CH:8][O:10][H:12]",
                "type": "same concerted epoxidation on the undirected (opposite) face -> trans-2,3-epoxycyclohexanol (minor channel)",
                "channel": "opposite_face",
            },
        ],
    },
    # C/C=C/CO/C=C/C>>C=C[C@H](C)[C@H](C)C=O  (0/1)  (E,E) 底物椅式（双甲基假
    # 赤道）→ syn = (2S,3S) 型（池内经 Fischer-CIP 推导核对）；副通道 = 船式 → anti。
    "G2": {
        "name_en": "(E,E)-crotyl propenyl ether Claisen rearrangement: determine the preferred TS geometry and diastereoselectivity",
        "conditions_en": "thermal, ~150-200 degC",
        "anchor": "selectivity",
        "minor_channel_en": "boat TS -> anti-2,3-dimethylpent-4-enal",
        "mapped_reactants": "[CH3:1]/[CH:2]=[CH:3]/[CH2:4][O:5]/[CH:6]=[CH:7]/[CH3:8]",
        "steps": [
            {
                "out": "[CH2:4]=[CH:3][C@H:2]([CH3:1])[C@H:7]([CH3:8])[CH:6]=[O:5]",
                "type": "[3,3]-sigmatropic Claisen rearrangement via chair TS with both methyls pseudo-equatorial: allyl/vinyl pi and C-O sigma cleavage, new terminal C-C sigma between the two methyl-bearing termini, migrated allyl pi and C=O pi formation -> syn-2,3-dimethylpent-4-enal",
                "channel": "chair_ts",
            },
        ],
        "competing": [
            {
                "out": "[CH2:4]=[CH:3][C@H:2]([CH3:1])[C@@H:7]([CH3:8])[CH:6]=[O:5]",
                "type": "Claisen via boat TS -> anti-2,3-dimethylpent-4-enal (minor channel)",
                "channel": "boat_ts",
            },
        ],
    },
}
