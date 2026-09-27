"""B 族登记：丙二酸热脱羧与后续烯醇互变。"""

TASKS = {
    "B1": {
        "name_en": "malonic acid thermal decarboxylation: malonic acid -> acetic acid + CO2",
        "conditions_en": "gas-phase thermolysis",
        "mapped_reactants": "[O:1]=[C:2]([O:3][H:8])[CH2:4][C:5](=[O:6])[O:7][H:11]",
        "steps": [
            {
                "out": "[O:1]=[C:2]=[O:3].[CH2:4]=[C:5]([O:6][H:8])[O:7][H:11]",
                "type": "six-membered cyclic decarboxylation with C-C cleavage and O-H transfer -> 1,1-ethenediol + CO2",
                "barrier": 27.94,
            },
            {
                "out": "[O:1]=[C:2]=[O:3].[CH2:4]([H:8])[C:5](=[O:6])[O:7][H:11]",
                "type": "1,1-ethenediol -> acetic acid keto-enol tautomerization (PT edge without a reference barrier)",
            },
        ],
    },
}
