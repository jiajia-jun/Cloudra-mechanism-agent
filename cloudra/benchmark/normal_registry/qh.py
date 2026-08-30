"""Q 族 + H 族登记：周环/阳离子环化（Q2/Q3）与杂环构建（H1–H3/H5）。

含芳香环的一批：反应物/产物一律芳香写法（[cH]/[nH]/[o]），去芳构化中间体
（H1 的环己二烯亚胺）用 Kekulé 写法——芳香键级 1.5 与单/双键之间的变化由生成器
自动推导为去芳构化/再芳构化的 break/form 信号。竞争通道（Q2 的两性离子/ene 路径、
H1 的 1,2-迁移假说、H3 的无催化通道、H5 的双自由基路径）按 normal.md 约定不进 gold。

H5 注意：池内雷酸 "[C-]#[N+]O" 经 RDKit 解析 H 在 O 上（C 端无 H），故环加成步
内含 O->C 的质子迁移（显式 [H:6]），与芳香异噁唑的三个环 CH 配平。

Q2 注记（2026-08-31 已修正）：池内产物 SMILES 曾误写为 C1=COCCC1（3,4-二氢-2H-
吡喃，烯醇醚异构体），与题名"3,6-二氢-2H-吡喃"不符；normal.md 已改为
C1=CCOCC1（纯 [4+2] 连通性），本条按修正后的池登记。
"""

TASKS = {
    # C=CC=C.C=O>>C1=CCOCC1  (0/1)  杂原子 Diels–Alder（单步协同 [4+2]）
    "Q2": {
        "name_en": "Hetero-Diels-Alder: 1,3-butadiene + formaldehyde -> 3,6-dihydro-2H-pyran (concerted [4+2])",
        "conditions_en": "gas-phase thermal reaction (Lewis acid is the classical accelerating condition, not included in this benchmark)",
        "mapped_reactants": "[CH2:1]=[CH:2][CH:3]=[CH2:4].[CH2:5]=[O:6]",
        "steps": [
            {
                # 纯 [4+2] 键账：成端基两根新 σ (1,5)/(4,6) 与中央新 π (2,3)；
                # 断二烯两根 π (1,2)/(3,4) 与 C=O π (5,6)
                "out": "[CH:2]1=[CH:3][CH2:4][O:6][CH2:5][CH2:1]1",
                "type": "concerted [4+2] hetero-Diels-Alder cycloaddition, asynchronous polar TS (competing stepwise zwitterion and ene channels are background edges only)",
            },
        ],
    },
    # [OH3+].C=CC(=O)C=C>>[OH3+].O=C1C=CCC1  (+1/1)  Nazarov 环化（3 步）
    "Q3": {
        "name_en": "Nazarov cyclization: divinyl ketone under acid activation -> cyclopent-2-enone",
        "conditions_en": "strong Brønsted/Lewis acid, room temperature",
        "mapped_reactants": "[OH2+:1]([H:2]).[CH:3]([H:9])=[CH:4][C:5](=[O:6])[CH:7]=[CH2:8]",
        "steps": [
            {
                # 羰基 O 质子化：断 O1-H2，成 O6-H2；写成可环化的戊二烯基共振式
                # （(5,6) π 断、(5,7) π 成、(7,8) π 断、阳离子移到端基 C8）
                "out": "[OH2:1].[CH:3]([H:9])=[CH:4][C:5]([O:6][H:2])=[CH:7][CH2+:8]",
                "type": "carbonyl oxygen protonation by hydronium -> hydroxypentadienyl cation (drawn in the pentadienyl resonance form that cyclizes)",
            },
            {
                # 4π 顺旋电环化（决速）：成端基间新 σ (3,8)；断 π (3,4)/(5,7)，成 π (4,5)；
                # 阳离子 C8 -> C7（环戊烯基阳离子，烯醇/氧碳鎓共振）
                "out": "[OH2:1].[CH:3]1([H:9])[CH:4]=[C:5]([O:6][H:2])[CH+:7][CH2:8]1",
                "type": "conrotatory 4pi electrocyclization (rate-determining): new terminal C-C sigma bond closes the cyclopentenyl cation (enol/oxocarbenium resonance)",
            },
            {
                # 去质子/互变异构恢复羰基：断 O6-H2、成 O1-H2 再生 H3O+；C3-H9 迁到 C7；
                # π (4,5) 断、(3,4) 成、(5,6) 成 → 环戊-2-烯酮
                "out": "[OH2+:1]([H:2]).[O:6]=[C:5]1[CH:4]=[CH:3][CH2:8][CH:7]1([H:9])",
                "type": "deprotonation/tautomerization cascade regenerating H3O+ and the carbonyl: beta-elimination at C3 with proton relocation onto the cationic C7 -> cyclopent-2-enone",
            },
        ],
    },
    # [OH3+].NNc1ccccc1.CC=O>>[OH3+].c1ccc2[nH]ccc2c1.N.O  (+1/1)  Fischer 吲哚（5 步）
    # H3O+ 全程旁观；苯肼芳环与吲哚苯环共用映射号 3-8（3=ipso，4=受攻邻位）。
    "H1": {
        "name_en": "Fischer indole synthesis core steps: phenylhydrazine + acetaldehyde -> indole + NH3 + H2O (acid-catalyzed)",
        "conditions_en": "AcOH/HCl or ZnCl2 (acid catalysis, H3O+ written into the SMILES on both sides), heated",
        "mapped_reactants": (
            "[OH2+:12]([H:13])."
            "[N:1]([H:14])([H:15])[N:2]([H:17])[c:3]1[c:4]([H:19])[cH:5][cH:6][cH:7][cH:8]1."
            "[CH:9]([H:16])([H:18])[CH:10]=[O:11]"
        ),
        "steps": [
            {
                # 腙形成：端基 N1 与醛缩合，成 N1=C10 π、断 C10=O11 π；
                # 断 N1-H14/H15，成 O11-H14/H15 → H2O；H3O+ 旁观
                "out": (
                    "[OH2+:12]([H:13])."
                    "[N:1](=[CH:10][CH:9]([H:16])([H:18]))[N:2]([H:17])"
                    "[c:3]1[c:4]([H:19])[cH:5][cH:6][cH:7][cH:8]1."
                    "[O:11]([H:14])([H:15])"
                ),
                "type": "hydrazone formation: terminal nitrogen condenses with acetaldehyde, C=O pi becomes C=N pi and water is expelled (H3O+ spectator)",
            },
            {
                # 腙->烯肼互变异构：断 N1=C10 π、断 C9-H16；成 C9=C10 π、成 N1-H16
                "out": (
                    "[OH2+:12]([H:13])."
                    "[CH:9]([H:18])=[CH:10][N:1]([H:16])[N:2]([H:17])"
                    "[c:3]1[c:4]([H:19])[cH:5][cH:6][cH:7][cH:8]1."
                    "[O:11]([H:14])([H:15])"
                ),
                "type": "hydrazone-enehydrazine tautomerization: methyl C-H migrates to the imine nitrogen, C=N pi shifts to C=C pi",
            },
            {
                # [3,3]-σ 迁移（决速）：断 N1-N2；成 C9-C4（烯肼端基到芳环邻位）；
                # 成 N2=C3 与 N1=C10 π、断 C9=C10 π；芳环去芳构化（Kekulé 环己二烯亚胺）
                "out": (
                    "[OH2+:12]([H:13])."
                    "[N:1]([H:16])=[CH:10][CH:9]([H:18])"
                    "[C:4]1([H:19])[CH:5]=[CH:6][CH:7]=[CH:8][C:3]1=[N:2][H:17]."
                    "[O:11]([H:14])([H:15])"
                ),
                "type": "[3,3]-sigmatropic rearrangement (rate-determining): N-N cleavage with new C-C bond from the enehydrazine terminus to the ortho carbon; dearomatized cyclohexadienimine intermediate (capturable)",
            },
            {
                # 关环：芳环所连 N2 进攻亚胺碳 C10 成五元环（成 N2-C10、断 N1=C10 π），
                # 并分子内 PT：断 N2-H17、成 N1-H17 → 环状胺/亚胺中间体（全中性）
                "out": (
                    "[OH2+:12]([H:13])."
                    "[N:2]1(=[C:3]2[CH:8]=[CH:7][CH:6]=[CH:5][C:4]2([H:19])"
                    "[CH:9]([H:18])[CH:10]1[N:1]([H:16])([H:17]))."
                    "[O:11]([H:14])([H:15])"
                ),
                "type": "ring closure: the aryl-bound nitrogen attacks the imine carbon to close the five-membered ring, with intramolecular proton transfer from N2 onto N1 -> cyclic aminal/imine intermediate",
            },
            {
                # 脱 NH3 + 再芳构化：断 C10-N1；C9-H18 与 C4-H19 迁到 N1/N2（成 N1-H18、N2-H19）；
                # 双环 π 重排回芳香吲哚（含断 N2=C3 π）；端基 N1 带三个 H 成 NH3
                "out": (
                    "[OH2+:12]([H:13])."
                    "[cH:5]1[cH:6][cH:7][cH:8][c:3]2[n:2]([H:19])[cH:10][cH:9][c:4]12."
                    "[N:1]([H:16])([H:17])([H:18])."
                    "[O:11]([H:14])([H:15])"
                ),
                "type": "NH3 elimination with rearomatization: C-N cleavage, ring pi rearrangement back to aromatic indole, and proton relocation (C9-H and the former ortho C4-H) onto the two nitrogens -> indole + NH3",
            },
        ],
    },
    # [OH3+].CC(=O)CCC(C)=O.N>>[OH3+].Cc1ccc(C)[nH]1.O.O  (+1/1)  Paal–Knorr 吡咯（4 步）
    # H3O+ 全程旁观；两分子水分别来自羰基 O3（缩合）与羰基 O7（脱水芳构化）。
    "H2": {
        "name_en": "Paal-Knorr pyrrole synthesis: 2,5-hexanedione + ammonia -> 2,5-dimethylpyrrole + 2 H2O (acid-catalyzed)",
        "conditions_en": "AcOH (acid catalysis, H3O+ written into the SMILES on both sides), heated",
        "mapped_reactants": (
            "[OH2+:13]([H:14])."
            "[CH2:1]([H:15])[C:2](=[O:3])[CH:4]([H:17])[CH:5]([H:16])[C:6](=[O:7])[CH3:8]."
            "[NH:9]([H:10])([H:11])"
        ),
        "steps": [
            {
                # 缩合成亚胺 + H2O：成 C2=N9 π、断 C2=O3 π；断 N9-H10/H11，成 O3-H10/H11
                "out": (
                    "[OH2+:13]([H:14])."
                    "[CH2:1]([H:15])[C:2](=[NH:9])[CH:4]([H:17])[CH:5]([H:16])[C:6](=[O:7])[CH3:8]."
                    "[O:3]([H:10])([H:11])"
                ),
                "type": "condensation of ammonia with one carbonyl -> ketimine + first water (C=O pi becomes C=N pi, two N-H protons transferred to the carbonyl oxygen)",
            },
            {
                # 亚胺->烯胺互变异构：断 C2=N9 π、断 C1-H15；成 C1=C2 π、成 N9-H15
                "out": (
                    "[OH2+:13]([H:14])."
                    "[CH2:1]=[C:2]([NH:9][H:15])[CH:4]([H:17])[CH:5]([H:16])[C:6](=[O:7])[CH3:8]."
                    "[O:3]([H:10])([H:11])"
                ),
                "type": "imine-enamine tautomerization: methyl C-H migrates to nitrogen, C=N pi shifts to C=C pi",
            },
            {
                # 烯胺 N9 分子内进攻第二羰基 C6 关环（成 N9-C6、断 C6=O7 π），
                # 并分子内 PT：断 N9-H15、成 O7-H15 → 环状羟基吡咯烷（全中性）
                "out": (
                    "[OH2+:13]([H:14])."
                    "[NH:9]1[C:2](=[CH2:1])[CH:4]([H:17])[CH:5]([H:16])[C:6]1([O:7][H:15])[CH3:8]."
                    "[O:3]([H:10])([H:11])"
                ),
                "type": "intramolecular ring closure of the enamine nitrogen onto the second carbonyl (cyclization is rate-determining per kinetics) with N->O proton transfer -> cyclic hydroxypyrrolidine",
            },
            {
                # 脱水 + 芳构化：断 C6-O7；C5-H16 迁到 O7（第二分子 H2O）、C4-H17 迁到 C1
                # （亚甲基回甲基）；环 π 重排到芳香吡咯（断 C1=C2 π，环键 1->1.5）
                "out": (
                    "[OH2+:13]([H:14])."
                    "[CH2:1]([H:17])[c:2]1[cH:4][cH:5][c:6]([CH3:8])[nH:9]1."
                    "[O:3]([H:10])([H:11]).[O:7]([H:15])([H:16])"
                ),
                "type": "dehydration with aromatization: C-OH cleavage, ring pi rearrangement to the aromatic pyrrole, and proton relocations (C5-H to the departing hydroxyl, C4-H to the exocyclic methylene) -> 2,5-dimethylpyrrole + second water",
            },
        ],
    },
    # [OH3+].CC(=O)CCC(C)=O>>[OH3+].Cc1ccc(C)o1.O  (+1/1)  Paal–Knorr 呋喃（4 步）
    # H3O+ 作质子梭（①给出 H10，②由 C1-H11 再生），③④旁观；只脱 1 分子水（O7）。
    "H3": {
        "name_en": "Paal-Knorr furan synthesis: 2,5-hexanedione -> 2,5-dimethylfuran + H2O (acid-catalyzed)",
        "conditions_en": "acid-catalyzed (H3O+ written into the SMILES on both sides; Lewis acid is the classical alternative), heated",
        "mapped_reactants": (
            "[OH2+:9]([H:10])."
            "[CH2:1]([H:11])[C:2](=[O:3])[CH:4]([H:12])[CH:5]([H:13])[C:6](=[O:7])[CH3:8]"
        ),
        "steps": [
            {
                # 羰基 O3 质子化：断 O9-H10，成 O3-H10（PT，酸催化烯醇化第一步）
                "out": (
                    "[OH2:9]."
                    "[CH2:1]([H:11])[C:2](=[O+:3][H:10])[CH:4]([H:12])[CH:5]([H:13])[C:6](=[O:7])[CH3:8]"
                ),
                "type": "carbonyl oxygen protonation by hydronium (PT, first half of acid-catalyzed enolization)",
            },
            {
                # 水拔 α-C1-H11：断 C1-H11、成 O9-H11 再生 H3O+；断 C2=O3 π、成 C1=C2 π → 烯醇
                "out": (
                    "[OH2+:9]([H:11])."
                    "[CH2:1]=[C:2]([O:3][H:10])[CH:4]([H:12])[CH:5]([H:13])[C:6](=[O:7])[CH3:8]"
                ),
                "type": "water deprotonates the alpha carbon: C=O pi shifts to C=C pi and H3O+ is regenerated -> enol (net acid-catalyzed enolization)",
            },
            {
                # 烯醇 O3 分子内进攻第二羰基 C6 关环（成 O3-C6、断 C6=O7 π），
                # 并分子内 PT：断 O3-H10、成 O7-H10 → 环状半缩醛（全中性）
                "out": (
                    "[OH2+:9]([H:11])."
                    "[CH2:1]=[C:2]1[O:3][C:6]([O:7][H:10])([CH3:8])[CH:5]([H:13])[CH:4]([H:12])1"
                ),
                "type": "intramolecular ring closure of the enol oxygen onto the second carbonyl (cyclization is rate-determining region) with O->O proton transfer -> cyclic hemiketal",
            },
            {
                # 脱水芳构化：断 C6-O7；C5-H13 迁到 O7（唯一一分子 H2O）、C4-H12 迁到 C1
                # （亚甲基回甲基）；环 π 重排到芳香呋喃（断 C1=C2 π，环键 1->1.5）
                "out": (
                    "[OH2+:9]([H:11])."
                    "[CH2:1]([H:12])[c:2]1[cH:4][cH:5][c:6]([CH3:8])[o:3]1."
                    "[O:7]([H:10])([H:13])"
                ),
                "type": "dehydration with aromatization: C-OH cleavage, ring pi rearrangement to the aromatic furan, and proton relocations (C5-H to the departing hydroxyl, C4-H to the exocyclic methylene) -> 2,5-dimethylfuran + water (only one water, unlike the pyrrole series)",
            },
        ],
    },
    # [C-]#[N+]O.C#C>>c1cnoc1  (0/1)  Huisgen 1,3-偶极环加成（单步协同 [3+2]）
    # 池内雷酸 H 在 O 上（RDKit 解析），故步内含 O3-H6 -> C1-H6 迁移。
    "H5": {
        "name_en": "Huisgen 1,3-dipolar cycloaddition: fulminic acid + acetylene -> isoxazole (concerted [3+2])",
        "conditions_en": "gas phase / inert solvent (fulminic acid generated in situ)",
        "mapped_reactants": "[C-:1]#[N+:2][O:3]([H:6]).[CH:4]#[CH:5]",
        "steps": [
            {
                # 协同 [3+2]：成新 σ C5-C1 与 O3-C4；断 C≡N (1,2) 与 C≡C (4,5) 各一根 π
                # （3->1.5 芳香）、成 N2-O3 1->1.5；O3-H6 迁到 C1 → 芳香异噁唑
                "out": "[c:1]1([H:6])[n:2][o:3][cH:4][cH:5]1",
                "type": "concerted [3+2] 1,3-dipolar cycloaddition: new C-C and C-O sigma bonds with pi rearrangement to the aromatic isoxazole (competing stepwise diradical channel is a background edge only)",
            },
        ],
    },
}
