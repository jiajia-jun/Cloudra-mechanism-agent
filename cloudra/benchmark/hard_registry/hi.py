"""H/I 族登记（v3 缩减后）：H1 联萘阻转消旋（绝对能垒锚点）+ I1 脯氨酸 Aldol（选择性锚点）。
v3（2026-09-09）由 20 条缩至 10 条：I4（硫脲 Strecker）剔出定稿名单留档池（条目见 hard.md）。

H1：池 SMILES 左右相同（消旋体表示，轴手性由 query 文本与 gold 3D 锚定），20 个碳全部
映射、无键变化。两条 peri-H 对穿路径共享 P/M 端点，以独立 TS 和 channel 区分。

I1：三步网络（① 烯胺生成 ② C–C 加成（立体决定步）③ 水解）。粒度判断：N–C 成键与
C–O 断键并成一条边（羟胺/亚铵不单独成节点，同 normal A4 直接缩合的处理），脯氨酸
羧基的质子接力并入相邻边；副产水写进步① out 并随装配体带入步②，步③被水消耗，
净反应不写水。立体归属：(S)-脯氨酸 + Houk–List 椅式 TS 主面进攻（羧基氢键网络
定位苯甲醛、烯胺从位阻较小面进攻）→ 新立体中心 C6 为 (S)，与池主产物
`CC(=O)C[C@H](O)c1ccccc1` 的 RDKit CIP 核对一致（(S)），与 List 2000 实验
（(S)-脯氨酸给 (S)-aldol）同号。competing 用 "from_step": 1, "is_product": false：
副面进攻从主线步①输出（烯胺装配体）出发 → (R)-构型亚铵-醇盐副中间体（与主面
中间体仅在 C6 构型相反，校验可区分）。

I4：单基元步协同氰基转移（C–C 成、N–H 成、C–H 断、C=N π 断，C≡N 不动；HCN 的 H
显式 [H:2]）；截短硫脲催化剂旁观写两侧、映射号不变。归属核对（RDKit CIP）：池
主产物 `CN[C@H](C#N)c1ccccc1` 实为 (R)，副面通道 `CN[C@@H](C#N)c1ccccc1` 为 (S)
——池字符串是权威，保持不动；hard.md 已标注"产物构型归属待 gold 核对"，按池原样
登记并在此留痕。
"""

TASKS = {
    # C1=CC=C2C(=C1)C=CC=C2C3=CC=CC4=CC=CC=C43>>同左  (0/1)
    # 1,1′-联萘消旋化：无键变化的两条纯构象路径，电子能垒逐边承载
    "H1": {
        "name_en": "1,1'-binaphthyl thermal racemization",
        "conditions_en": "thermal racemization, ~50 degC, DMF",
        "anchor": "barrier",
        "mapped_reactants": "[cH:1]1[cH:2][cH:3][c:4]2[c:5]([cH:6]1)[cH:7][cH:8][cH:9][c:10]2-[c:11]1[cH:12][cH:13][cH:14][c:15]2[cH:16][cH:17][cH:18][cH:19][c:20]12",
        "steps": [
            {
                "out": "[cH:1]1[cH:2][cH:3][c:4]2[c:5]([cH:6]1)[cH:7][cH:8][cH:9][c:10]2-[c:11]1[cH:12][cH:13][cH:14][c:15]2[cH:16][cH:17][cH:18][cH:19][c:20]12",
                "type": "atropisomerization through the lower syn peri-H crossing (torsion near 0 deg)",
                "barrier": 23.01,
                "weight": 0.5,
                "conformational": True,
                "channel": "syn",
            },
        ],
        "competing": [
            {
                "out": "[cH:1]1[cH:2][cH:3][c:4]2[c:5]([cH:6]1)[cH:7][cH:8][cH:9][c:10]2-[c:11]1[cH:12][cH:13][cH:14][c:15]2[cH:16][cH:17][cH:18][cH:19][c:20]12",
                "type": "atropisomerization through the higher anti peri-H crossing (torsion near 180 deg)",
                "barrier": 32.36,
                "weight": 0.5,
                "conformational": True,
                "same_endpoint": True,
                "channel": "anti",
            },
        ],
    },
    # CC(C)=O.O=Cc1ccccc1.O=C(O)[C@@H]1CCCN1>>CC(=O)C[C@H](O)c1ccccc1.O=C(O)[C@@H]1CCCN1  (0/1)
    # 脯氨酸催化直接 Aldol；脯氨酸 N-H（H21）与丙酮 alpha-H（H22）参与键变化、全程显式，
    # 两质子先在步①随羰基 O4 成副产水，步③水裂解时分别归还 N20 与醇盐 O5
    # 同一 map16 催化剂中心全程为 S；从 N20 反向遍历环时须用 [C@H:16] 保持绝对构型。
    "I1": {
        "name_en": "(S)-proline-catalyzed direct aldol reaction of acetone with benzaldehyde: determine the stereochemical outcome",
        "conditions_en": "20-30 mol% (S)-proline, DMSO, room temperature",
        "anchor": "selectivity",
        "minor_channel_en": "opposite-face enamine attack on benzaldehyde via the minor Houk-List chair TS -> (R)-iminium-aldolate (the (R)-aldol channel)",
        "mapped_reactants": "[CH3:1][C:2](=[O:4])[CH2:3]([H:22]).[O:5]=[CH:6][c:7]1[cH:8][cH:9][cH:10][cH:11][cH:12]1.[O:13]=[C:14]([OH:15])[C@@H:16]1[CH2:17][CH2:18][CH2:19][N:20]1([H:21])",
        "steps": [
            {
                # 直接缩合（羟胺/亚铵不单独成节点）：成 C2-N20，断 C2=O4、断 N20-H21、断 C3-H22，
                # 成 C2=C3 pi，两质子经羧基接力转到离去的 O4 成水 → 烯胺 + H2O（苯甲醛旁观）
                "out": "[CH3:1][C:2](=[CH2:3])[N:20]2[CH2:19][CH2:18][CH2:17][C@H:16]2[C:14](=[O:13])[OH:15].[O:4]([H:21])([H:22]).[O:5]=[CH:6][c:7]1[cH:8][cH:9][cH:10][cH:11][cH:12]1",
                "type": "enamine condensation (merged edge): proline N attacks the acetone carbonyl, C-O cleaves and the N-H/alpha-C-H protons are relayed onto the departing oxygen by the carboxyl shuttle -> enamine + water (carbinolamine/iminium not separate nodes)",
                "barrier": None,
                "weight": 0.5,
            },
            {
                # 立体决定步：烯胺 beta-C（C3）经 Houk-List 椅式 TS 从主面进攻苯甲醛 C6，
                # 成 C3-C6，断 C2=C3 pi、断 C6=O5 pi，成 C2=N20 pi → (S)-构型亚铵-醇盐
                "out": "[CH3:1][C:2](=[N+:20]2[CH2:19][CH2:18][CH2:17][C@H:16]2[C:14](=[O:13])[OH:15])[CH2:3][C@H:6]([O-:5])[c:7]1[cH:8][cH:9][cH:10][cH:11][cH:12]1.[O:4]([H:21])([H:22])",
                "type": "stereo-determining C-C addition: enamine beta-carbon attacks benzaldehyde through the major-face Houk-List chair TS (carboxyl H-bond network positions the aldehyde) -> (S)-configured iminium-aldolate",
                "barrier": 13.36,
                "weight": 0.5,
                "channel": "major_face",
            },
            {
                # 水解：水 O4 进攻亚铵 C2 并裂解，成 C2=O4，断 C2-N20、断 O4-H21/O4-H22，
                # 成 N20-H21（脯氨酸再生）、成 O5-H22（醇盐质子化）→ (S)-aldol + (S)-脯氨酸
                "out": "[CH3:1][C:2](=[O:4])[CH2:3][C@H:6]([O:5][H:22])[c:7]1[cH:8][cH:9][cH:10][cH:11][cH:12]1.[O:13]=[C:14]([OH:15])[C@@H:16]1[CH2:17][CH2:18][CH2:19][N:20]1([H:21])",
                "type": "hydrolysis: water cleaves the iminium (C=O restored, C-N breaks), one water proton regenerates the proline N-H and the other protonates the aldolate -> (S)-aldol + (S)-proline",
                "barrier": None,
                "weight": 0.5,
            },
        ],
        "competing": [
            {
                # 副面进攻：同一烯胺装配体（from_step=1）经另一条 Houk-List 椅式 TS →
                # (R)-构型亚铵-醇盐副中间体（is_product=false，仅 C6 构型相反）
                "out": "[CH3:1][C:2](=[N+:20]2[CH2:19][CH2:18][CH2:17][C@H:16]2[C:14](=[O:13])[OH:15])[CH2:3][C@@H:6]([O-:5])[c:7]1[cH:8][cH:9][cH:10][cH:11][cH:12]1.[O:4]([H:21])([H:22])",
                "type": "opposite-face enamine attack via the minor Houk-List chair TS -> (R)-configured iminium-aldolate (minor intermediate, hydrolysis not traced in the reference graph)",
                "barrier": 15.52,
                "weight": 0.5,
                "from_step": 1,
                "is_product": False,
                "channel": "minor_face",
            },
        ],
    },
}
