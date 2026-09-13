"""A/B 族登记（v3 缩减后）：电环化 torqueselection（A1/A6）。

A 族两条均为 4π 顺旋开环的竞争方向题：主线 = 优势旋转方向，competing =
另一旋转方向（同一步骤、同一反应物络合物出发，产物互为 E/Z 异构）。
v3（2026-09-09）由 20 条缩至 10 条：A2（受体内向）、B7（DA π-面）剔出名单
留档池（条目仍见 hard.md），registry 只留定稿条目。

A1 是框架参考条目（已随 gen_hard_tasks 框架验证通过）；A6 同款登记。
"""

TASKS = {
    # CC1CC=C1>>C=C/C=C/C  (0/1)  甲基外向旋转 → (E)-1,3-戊二烯
    # 断 sp3-sp3 σ（甲基所在碳–CH2）与旧 π，成两个新 π
    "A1": {
        "name_en": "3-methylcyclobutene conrotatory ring opening: determine the torquoselectivity",
        "conditions_en": "gas phase or inert solvent, ~150-200 degC, thermal",
        "anchor": "selectivity",
        "minor_channel_en": "inward methyl rotation -> (Z)-1,3-pentadiene",
        "mapped_reactants": "[CH3:1][CH:2]1[CH2:3][CH:4]=[CH:5]1",
        "steps": [
            {
                "out": "[CH3:1]/[CH:2]=[CH:5]/[CH:4]=[CH2:3]",
                "type": "4pi conrotatory electrocyclic ring opening, outward rotation of the methyl group (torquoselection) -> (E)-1,3-pentadiene",
                "channel": "outward_rotation",
            },
        ],
        "competing": [
            {
                "out": "[CH3:1]/[CH:2]=[CH:5]\\[CH:4]=[CH2:3]",
                "type": "conrotatory opening with inward methyl rotation -> (Z)-1,3-pentadiene (minor channel of the torquoselection)",
                "channel": "inward_rotation",
            },
        ],
    },
    # C[C@H]1C=C[C@@H]1C>>C/C=C/C=C/C  (0/1)  (3S,4S) 底物双甲基外向 → (E,E)-2,4-己二烯
    # 断两个甲基所在 sp3 碳之间的 σ，旧 π 位移，成两个新 π
    # 注：池机理格副产物 SMILES C/C=C\C=C\C 实为 (Z,E)；双内向顺旋的化学
    # 产物是 (Z,Z)（RDKit 枚举核对，canonical C/C=C\C=C/C），按化学正确登记。
    "A6": {
        "name_en": "trans-3,4-dimethylcyclobutene conrotatory ring opening: determine the torquoselectivity",
        "conditions_en": "gas phase or inert solvent, heating, thermal",
        "anchor": "selectivity",
        "minor_channel_en": "double inward methyl rotation -> (Z,Z)-2,4-hexadiene",
        "mapped_reactants": "[CH3:1][C@H:2]1[CH:3]=[CH:4][C@@H:5]1[CH3:6]",
        "steps": [
            {
                "out": "[CH3:1]/[CH:2]=[CH:3]/[CH:4]=[CH:5]/[CH3:6]",
                "type": "4pi conrotatory electrocyclic ring opening, both methyl groups rotating outward (steric torquoselection) -> (E,E)-2,4-hexadiene",
                "channel": "double_outward_rotation",
            },
        ],
        "competing": [
            {
                "out": "[CH3:1]\\[CH:2]=[CH:3]/[CH:4]=[CH:5]\\[CH3:6]",
                "type": "conrotatory opening with both methyl groups rotating inward -> (Z,Z)-2,4-hexadiene (minor channel of the torquoselection)",
                "channel": "double_inward_rotation",
            },
        ],
    },
}
