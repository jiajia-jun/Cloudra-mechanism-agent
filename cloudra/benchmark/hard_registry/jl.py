"""J/L 族：L1 为 HCNO 与降冰片烯的两面 [3+2] 环加成。

2026-10-18：用户授权替换旧 Beckmann 题。本轮结果已交付，
正式 Gold 参考仍缺测；产物只给连接式，不预填立体身份、能垒或优势面。
"""

TASKS = {
    # 结果已交付到 gold_compute/queue_20261018/results/HL1；当前正式 Gold 参考缺测。
    # 状态见 queue 交接，不自动安排重算。
    "L1": {
        "name_en": "formonitrile oxide + norbornene [3+2] cycloaddition: determine both facial pathways",
        "conditions_en": "gas phase, neutral singlet HCNO plus unsubstituted norbornene; investigate approach from both faces of the C4=C5 bond relative to the methano bridge C10 in the atom mapping; establish each product's stereochemical relationship to that bridge from actual 3D geometries and give explicit stereochemical SMILES rather than relying on an unverified endo/exo or syn/anti name; compare the two pathways using a common qualified reactant reference and establish the relationship between any distinct pre-reaction complexes; investigate C-C and C-O bond formation and the identity of both endpoints; do not substitute benzonitrile oxide or substituted norbornene; reference DOI 10.1039/FT9938900029",
        "anchor": None,
        "score_selectivity": False,
        "mapped_reactants": "[CH:1]#[N+:2][O-:3].[CH:4]1=[CH:5][CH:6]2[CH2:7][CH2:8][CH:9]1[CH2:10]2",
        "steps": [],
    },
}
