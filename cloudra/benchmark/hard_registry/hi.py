"""H/I 族：H1 联萘阻转消旋；I1 胺氧化物 Cope 消除的立体映射。

2026-10-18：用户授权用 I1 新题替换旧脯氨酸 aldol。新题仍待计算，
只登记给定反应物；不预设立体产物、路径、能垒或优势通道。
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
    # 两种非对映底物分别构建、分别计算；无立体骨架不表示二者的混合络合物。
    "I1": {
        "name_en": "Cope elimination of threo/erythro N,N-dimethyl-3-phenyl-2-butylamine oxide: determine the stereochemical mapping",
        "conditions_en": "gas phase, isolated neutral singlet amine oxide; construct and compute the threo and erythro substrate forms as two separate cases, not as a mixture or a combined reactant complex; verify each substrate's relative configuration and CIP assignment from its actual 3D geometry before naming it; investigate syn elimination to 2-phenyl-2-butene and dimethylhydroxylamine, and determine each alkene E/Z identity from the computed geometry rather than assuming a cis/trans correspondence; use each substrate's own minimum for its barrier and do not subtract energies across the two substrates; distinguish any alternative regioisomeric elimination; report each case with explicit stereochemical SMILES, separate reactant nodes and evidence; reference DOI 10.1021/ja057523x; reference mechanism and quantitative Gold pending computation",
        "anchor": None,
        "score_selectivity": False,
        "mapped_reactants": "[CH3:1][CH:2]([N+:3]([CH3:4])([CH3:5])[O-:6])[C:7]([H:15])([CH3:8])[c:9]1[cH:10][cH:11][cH:12][cH:13][cH:14]1",
        "steps": [],
    },
}
