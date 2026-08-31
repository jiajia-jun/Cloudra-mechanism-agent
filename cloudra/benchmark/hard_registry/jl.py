"""J/L 族登记：双分子协同立体专一（J1/J2/J4）+ 重排手性转移（L1/L4）。

J1（二亚胺顺式还原）与 J4（构象锁定 anti-E2）为立体专一题：副通道被对称性/
反式双轴向要求禁阻，不带 competing 边，立体匹配本身即判别器。J2 带
Markovnikov 区域异构副通道（无立体中心，做区域选择性判别；池能垒格无数值
锚点故 anchor=None，不生成 gold.selectivity）。L1 照 normal R2（丙酮肟）
五步骨架，唯一差别是迁移基团为乙基。L4 带另一面 [2,3] TS 的差向副通道。
"""

TASKS = {
    # N=N.CC#CC>>N#N.C/C=C\C  (0/1)  二亚胺顺式还原 2-丁炔 → (Z)-2-丁烯
    # 映射：1/2=二亚胺两个 N，3/4=两个转移 H（显式），5/8=炔两个甲基，6/7=炔碳。
    # 键变化同 easy G2：断两个 N-H 与 C≡C 的一根 π，成两个 C-H 与 N≡N 第三键。
    # syn 加成 → (Z)；trans 通道对称禁阻，无 competing。
    "J1": {
        "name_en": "diimide syn reduction of 2-butyne -> (Z)-2-butene (stereospecific concerted double H transfer)",
        "conditions_en": "gas phase or solution, mild heating",
        "anchor": None,
        "mapped_reactants": "[N:1]([H:3])=[N:2]([H:4]).[CH3:5][C:6]#[C:7][CH3:8]",
        "steps": [
            {
                "out": "[N:1]#[N:2].[CH3:5]/[C:6]([H:3])=[C:7]([H:4])\\[CH3:8]",
                "type": "concerted [sigma2s+sigma2s+pi2s] double hydrogen transfer from cis-diimide: both N-H bonds and one alkyne pi bond cleaved, both C-H bonds formed on the same face (syn) and N=N -> N#N; stereospecific -> (Z)-2-butene (trans channel symmetry-forbidden)",
            },
        ],
    },
    # B.CC1=CCCCC1>>C[C@H]1[C@H](B)CCCC1  (0/1)  1-甲基环己烯氢硼化
    # 映射：1=BH2（转移 H 显式为 2，同 easy G1 口径），3=甲基，4=烯的叔碳
    # （带甲基），5=烯的 CH，6–9=环上四个 CH2。
    # syn + anti-Markovnikov：B 到 5 位（少取代碳），H2 到 4 位（叔碳），
    # 同面加成 → 甲基与 B trans。产物立体经 RDKit 规范化比对锁定为池内 trans。
    "J2": {
        "name_en": "hydroboration of 1-methylcyclohexene with BH3 (syn, anti-Markovnikov -> trans-2-methylcyclohexylborane)",
        "conditions_en": "BH3.THF, 0 degC to room temperature",
        "anchor": None,
        "mapped_reactants": "[BH2:1][H:2].[CH3:3][C:4]1=[CH:5][CH2:6][CH2:7][CH2:8][CH2:9]1",
        "steps": [
            {
                "out": "[CH3:3][C@@:4]1([H:2])[C@H:5]([BH2:1])[CH2:6][CH2:7][CH2:8][CH2:9]1",
                "type": "concerted four-center cyclic TS: B-H cleavage and C=C pi cleavage, C-B formation at the less substituted carbon (anti-Markovnikov) and C-H formation at the tertiary carbon, syn addition (B and H delivered to the same face) -> trans-2-methylcyclohexylborane (methyl and B trans)",
            },
        ],
        "competing": [
            {
                # Markovnikov 区域异构：B 加到叔碳 4、H 加到 5 → 无立体中心
                "out": "[CH3:3][C:4]1([BH2:1])[CH:5]([H:2])[CH2:6][CH2:7][CH2:8][CH2:9]1",
                "type": "Markovnikov regioisomeric channel: B adds to the tertiary alkene carbon and H to the less substituted one -> 1-boro-1-methylcyclohexane (achiral); regioselectivity discriminator, no numerical selectivity anchor in the pool",
            },
        ],
    },
    # [F-].C[C@@H]1CCCC[C@H]1F>>CC1C=CCCC1.F.[F-]  (−1/1)  trans-2-甲基环己基氟 anti-E2
    # 映射：1=外部 F⁻ 碱，2=甲基，3=甲基所在环碳，4–7=环上四个 CH2
    # （7=被拔氢碳，轴向 H 显式为 10），8=C-F 碳，9=离去 F。
    # trans-diaxial：F 轴向的椅式中 3 位轴向被甲基占据 → 只能向 7 位消除 →
    # 双键在 7=8 之间 → 3-甲基环己烯（Hofmann）；Zaitsev 通道无轴向 H 被禁阻，
    # 无 competing。3 号碳在新产物中仍是立体中心但池产物未标注立体 → out 不带 @。
    "J4": {
        "name_en": "anti-E2 elimination of trans-2-methylcyclohexyl fluoride by fluoride (conformationally locked trans-diaxial requirement -> Hofmann product 3-methylcyclohexene)",
        "conditions_en": "gas phase (benchmark model conditions); solution is the classical setting",
        "anchor": None,
        "mapped_reactants": "[F-:1].[CH3:2][C@@H:3]1[CH2:4][CH2:5][CH2:6][CH:7]([H:10])[C@H:8]1[F:9]",
        "steps": [
            {
                "out": "[F:1][H:10].[F-:9].[CH3:2][CH:3]1[CH2:4][CH2:5][CH2:6][CH:7]=[CH:8]1",
                "type": "concerted anti-E2 elimination: external fluoride abstracts the axial H on the ring carbon adjacent to the C-F carbon on the non-methyl side (trans-diaxial geometry), C-F cleavage and C=C pi formation -> 3-methylcyclohexene + HF + F- (Zaitsev channel toward the methyl-bearing carbon has no axial H and is forbidden)",
            },
        ],
    },
    # [OH3+].CC/C(=N/O)/C>>[OH3+].CCNC(C)=O  (+1/1)  (E)-丁酮肟 Beckmann
    # 骨架照 normal R2（丙酮肟）五步，唯一差别：迁移基团为乙基（R2 为甲基）。
    # 映射：1=H3O+ 的 O，2=迁移质子，9/10=H3O+ 其余 H；3=肟碳上的甲基（不迁移），
    # 4=肟 C，5/11=anti 迁移乙基（CH2/CH3），6=N，7=肟 OH 的 O，8=其 H。
    # (E)-肟：乙基与 OH 反式 → 乙基 anti 迁移 → N-乙基乙酰胺；(Z)-肟是另一
    # 底物（非本底物通道），syn 甲基迁移被立体专一性排除 → 无 competing。
    "L1": {
        "name_en": "Beckmann rearrangement of (E)-butanone oxime (oxime geometry selects the migrating group -> N-ethylacetamide)",
        "conditions_en": "concentrated H2SO4 or acid catalysis, heated",
        "anchor": None,
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
    # C/C=C/C[S@@](=O)C>>C=C[C@@H](C)OSC  (0/1)  Mislow–Evans [2,3] 重排
    # 映射：1=γ 位甲基，2=γ-C（新手性中心，带甲基），3=β-C，4=α-CH2（连 S），
    # 5=S，6=O，7=S-甲基。
    # [2,3]-σ 迁移：断 S5=O6 π 与 S5-C4 σ，断 C2=C3 π；成 O6-C2 与 C3=C4 π。
    # 归属备注：池写定主产物为 C=C[C@@H](C)OSC、副产物为 @@ 的差向体；endo/exo
    # TS 与产物构型的对应关系标注待核对——按池 SMILES 登记，主线=池产物构型，
    # competing=其差向体；对归属的异议属遗留不确定性，不改 SMILES。
    "L4": {
        "name_en": "Mislow-Evans [2,3]-sigmatropic rearrangement of (S,E)-crotyl methyl sulfoxide (S-to-C chirality transfer)",
        "conditions_en": "room temperature to mild heating",
        "anchor": None,
        "mapped_reactants": "[CH3:1]/[CH:2]=[CH:3]/[CH2:4][S@@:5](=[O:6])[CH3:7]",
        "steps": [
            {
                "out": "[CH2:4]=[CH:3][C@@H:2]([CH3:1])[O:6][S:5][CH3:7]",
                "type": "concerted [2,3]-sigmatropic rearrangement (Mislow-Evans): S=O pi and S-C(allyl) sigma cleavage, allylic C=C pi shift, new O-C bond at the gamma-carbon bearing the methyl group; S-to-C chirality transfer through the favored TS face -> allyl sulfenate with the new stereocenter as written in the pool product",
            },
        ],
        "competing": [
            {
                # 另一面（内/外型 TS 竞争）→ 差向副产物
                "out": "[CH2:4]=[CH:3][C@H:2]([CH3:1])[O:6][S:5][CH3:7]",
                "type": "opposite-face [2,3] TS (the disfavored endo/exo alternative) -> epimeric allyl sulfenate C=C[C@H](C)OSC (minor channel of the chirality transfer)",
            },
        ],
    },
}
