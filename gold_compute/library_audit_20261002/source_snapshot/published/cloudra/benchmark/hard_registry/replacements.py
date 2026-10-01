"""2026-10-01 independently curated, same-method verified replacements; original E3/G2 retained in history.

A8 = H6PI (replaces HE3); B10 = HDA_CN (replaces HG2).
IRC native limits and reference/conformer caveats: gold_compute/hard_replacements_verified_2026-10-01.md.
The 0.22 kcal/mol HDA electronic gap does not define a robust favored channel.
"""

TASKS = {'A8': {'name_en': '(2E,4Z,6E)-octa-2,4,6-triene thermal 6-pi electrocyclization: determine the '
                   'stereochemical outcome',
        'conditions_en': 'gas phase; thermal ground-state first electrocyclization only; exclude '
                         'subsequent hydrogen shifts and photochemistry',
        'anchor': 'barrier',
        'score_selectivity': False,
        'mapped_reactants': '[CH3:1]/[CH:2]=[CH:3]/[CH:4]=[CH:5]\\[CH:6]=[CH:7]\\[CH3:8]',
        'steps': [{'out': '[CH3:1][C@@H:2]1[CH:3]=[CH:4][CH:5]=[CH:6][C@@H:7]1[CH3:8]',
                   'type': 'concerted thermally allowed disrotatory 6-pi ring closure with C2-C7 bond '
                           'formation and three pi-bond shifts -> cis/meso '
                           '5,6-dimethylcyclohexa-1,3-diene',
                   'barrier': 29.48}]},
 'B10': {'name_en': 'cyclopentadiene + acrylonitrile Diels-Alder reaction: determine both '
                    'stereochemical pathways',
         'conditions_en': 'gas phase; concerted Diels-Alder addition; compare both endo/exo channels '
                          'using a common reactant-complex reference',
         'anchor': 'barrier',
         'score_selectivity': False,
         'mapped_reactants': '[CH2:6]=[CH:7][C:8]#[N:9].[CH:1]1=[CH:2][CH2:3][CH:4]=[CH:5]1',
         'steps': [{'out': '[CH:1]1=[CH:5][C@@H:4]2[CH2:3][C@H:2]1[CH2:6][C@@H:7]2[C:8]#[N:9]',
                    'type': 'concerted asynchronous [4+2] addition forming C2-C6 and C4-C7 -> endo '
                            'bicyclic adduct (CN anti to methano bridge C3)',
                    'barrier': 14.34,
                    'channel': 'endo',
                    'favored': None,
                    'node_label': 'endo product'}],
         'competing': [{'out': '[CH:1]1=[CH:5][C@@H:4]2[CH2:3][C@H:2]1[CH2:6][C@H:7]2[C:8]#[N:9]',
                        'type': 'concerted asynchronous [4+2] addition -> exo bicyclic adduct (CN syn '
                                'to methano bridge C3)',
                        'barrier': 14.12,
                        'channel': 'exo',
                        'favored': None,
                        'node_label': 'exo product'}]}}
