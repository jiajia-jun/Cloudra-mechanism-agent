"""A/B 族登记：电环化 torquoselection（A1/A2/A6）+ DA π-面选择性（B7）。

A 族三条均为 4π 顺旋开环的竞争方向题：主线 = 优势旋转方向，competing =
另一旋转方向（同一步骤、同一反应物络合物出发，产物互为 E/Z 异构）。
B7 为 5-甲基环戊二烯 + 顺丁烯二酸酐的 π-面 syn/anti 竞争。

A1 是框架参考条目（已随 gen_hard_tasks 框架验证通过）；其余按同款登记。
"""

TASKS = {
    # CC1CC=C1>>C=C/C=C/C  (0/1)  甲基外向旋转 → (E)-1,3-戊二烯
    # 断 sp3-sp3 σ（甲基所在碳–CH2）与旧 π，成两个新 π
    "A1": {
        "name_en": "3-methylcyclobutene conrotatory ring opening (torquoselectivity: donor outward)",
        "conditions_en": "gas phase or inert solvent, ~150-200 degC, thermal",
        "anchor": "selectivity",
        "minor_channel_en": "inward methyl rotation -> (Z)-1,3-pentadiene",
        "mapped_reactants": "[CH3:1][CH:2]1[CH2:3][CH:4]=[CH:5]1",
        "steps": [
            {
                "out": "[CH3:1]/[CH:2]=[CH:5]/[CH:4]=[CH2:3]",
                "type": "4pi conrotatory electrocyclic ring opening, outward rotation of the methyl group (torquoselection) -> (E)-1,3-pentadiene",
            },
        ],
        "competing": [
            {
                "out": "[CH3:1]/[CH:2]=[CH:5]\\[CH:4]=[CH2:3]",
                "type": "conrotatory opening with inward methyl rotation -> (Z)-1,3-pentadiene (minor channel of the torquoselection)",
            },
        ],
    },
    # O=CC1CC=C1>>C=C/C=C\C=O  (0/1)  受体内向旋转 → (Z)-2,4-戊二烯醛
    # 断环上 sp3-sp3 σ（CHO 所在碳–CH2），旧 π 位移，成两个新 π
    "A2": {
        "name_en": "3-formylcyclobutene conrotatory ring opening (reverse torquoselectivity: acceptor inward)",
        "conditions_en": "gas phase or inert solvent, ~120-180 degC, thermal",
        "anchor": "selectivity",
        "minor_channel_en": "outward CHO rotation -> (E)-2,4-pentadienal",
        "mapped_reactants": "[O:6]=[CH:1][CH:2]1[CH2:3][CH:4]=[CH:5]1",
        "steps": [
            {
                "out": "[O:6]=[CH:1]/[CH:2]=[CH:5]\\[CH:4]=[CH2:3]",
                "type": "4pi conrotatory electrocyclic ring opening, inward rotation of the electron-acceptor formyl group (acceptor-inward torquoselection) -> (Z)-2,4-pentadienal",
            },
        ],
        "competing": [
            {
                "out": "[O:6]=[CH:1]/[CH:2]=[CH:5]/[CH:4]=[CH2:3]",
                "type": "conrotatory opening with outward CHO rotation -> (E)-2,4-pentadienal (minor channel of the torquoselection)",
            },
        ],
    },
    # C[C@H]1C=C[C@@H]1C>>C/C=C/C=C/C  (0/1)  (3S,4S) 底物双甲基外向 → (E,E)-2,4-己二烯
    # 断两个甲基所在 sp3 碳之间的 σ，旧 π 位移，成两个新 π
    # 注：池机理格副产物 SMILES C/C=C\C=C\C 实为 (Z,E)；双内向顺旋的化学
    # 产物是 (Z,Z)（RDKit 枚举核对，canonical C/C=C\C=C/C），按化学正确登记。
    "A6": {
        "name_en": "trans-3,4-dimethylcyclobutene conrotatory ring opening (torquoselectivity: double outward methyl rotation)",
        "conditions_en": "gas phase or inert solvent, heating, thermal",
        "anchor": "selectivity",
        "minor_channel_en": "double inward methyl rotation -> (Z,Z)-2,4-hexadiene",
        "mapped_reactants": "[CH3:1][C@H:2]1[CH:3]=[CH:4][C@@H:5]1[CH3:6]",
        "steps": [
            {
                "out": "[CH3:1]/[CH:2]=[CH:3]/[CH:4]=[CH:5]/[CH3:6]",
                "type": "4pi conrotatory electrocyclic ring opening, both methyl groups rotating outward (steric torquoselection) -> (E,E)-2,4-hexadiene",
            },
        ],
        "competing": [
            {
                "out": "[CH3:1]\\[CH:2]=[CH:3]/[CH:4]=[CH:5]\\[CH3:6]",
                "type": "conrotatory opening with both methyl groups rotating inward -> (Z,Z)-2,4-hexadiene (minor channel of the torquoselection)",
            },
        ],
    },
    # CC1C=CC=C1.O=C1OC(=O)C=C1>>O=C1OC(=O)C2C1C1C=CC2C1C  (0/1)
    # DA [4+2]，endo，亲双烯体从 5-甲基异面（anti）进攻为主；syn 面为副通道。
    # 池产物无立体标记 → 主线末步 out 必须无立体（连接性级校验），anti 归属
    # 记录在 step type；副通道带完整立体标记（syn-7-甲基 endo 加成物）。
    # syn/anti 归属经 RDKit ETKDG+MMFF 3D 核对：endo-cis 非对映体中
    # d(Me, mid(C12-C13))=2.89 A 者 = syn（甲基朝酸酐桥侧），3.73 A 者 = anti。
    "B7": {
        "name_en": "Diels-Alder cycloaddition of 5-methylcyclopentadiene with maleic anhydride (pi-face anti/syn selectivity)",
        "conditions_en": "low temperature, rapid trapping of the 5-methylcyclopentadiene isomer (before 1,5-H-shift equilibration)",
        "anchor": None,
        "mapped_reactants": "[CH3:1][CH:2]1[CH:3]=[CH:4][CH:5]=[CH:6]1.[O:7]=[C:8]1[O:9][C:10](=[O:11])[CH:12]=[CH:13]1",
        "steps": [
            {
                "out": "[O:7]=[C:8]1[O:9][C:10](=[O:11])[CH:12]2[CH:13]1[CH:3]1[CH:4]=[CH:5][CH:6]2[CH:2]1[CH3:1]",
                "type": "Diels-Alder [4+2] cycloaddition, endo, dienophile attacking the pi-face anti to the 5-methyl group -> anti-7-methyl endo-norbornene adduct (pool product SMILES is connectivity-level; anti configuration: [CH3:1][C@H:2]1[C@H:3]2[CH:4]=[CH:5][C@@H:6]1[C@@H:12]1[C:10](=[O:11])[O:9][C:8](=[O:7])[C@H:13]21)",
            },
        ],
        "competing": [
            {
                "out": "[CH3:1][C@@H:2]1[C@H:3]2[CH:4]=[CH:5][C@@H:6]1[C@@H:12]1[C:10](=[O:11])[O:9][C:8](=[O:7])[C@H:13]21",
                "type": "Diels-Alder [4+2] cycloaddition, endo, dienophile attacking the pi-face syn to the 5-methyl group -> syn-7-methyl endo-norbornene adduct (minor channel of the pi-face selection)",
            },
        ],
    },
}
