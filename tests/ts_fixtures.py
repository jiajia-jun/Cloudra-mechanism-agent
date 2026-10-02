"""Explicit scientific declarations shared by TS regression fixtures."""
from cloudra.tools.core.ts_inputs import TsInput


def calculation_input(*, reactant_smiles, product_smiles, method, charge=0,
                      multiplicity=1, engine='orca', extra_keywords='',
                      reaction_center=(), atom_map=(), ring_order=(),
                      distance_filters=(), product_geometry=None,
                      path_solvation=None, irc_log=None, scan=None):
    calculation = dict(engine=engine, method=method, keywords=extra_keywords)
    generate = dict(kind='generate', generation='ETKDGv3', seed=42)
    guess = dict(kind='xtb_path', method='GFN2-xTB', solvation=path_solvation)
    if scan is not None:
        guess = dict(kind='scan', calculation=dict(engine=engine, method=scan['method'], keywords=scan.get('extra_route', '')),
                     scans=scan['scans'], freeze=scan.get('freeze', []))
    return TsInput.model_validate(dict(
        reaction=dict(reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                      charge=charge, multiplicity=multiplicity,
                      atom_map=list(atom_map), reaction_center=list(reaction_center)),
        conformers=dict(reactant=generate, product=product_geometry or generate,
                        guidance=dict(ring_order=list(ring_order), distance_filters=list(distance_filters))),
        guess=guess, ts_optimization=calculation,
        verification=dict(frequency=calculation, irc=calculation, irc_log=irc_log,
            reactant_endpoint=dict(optimization=calculation, frequency=calculation),
            product_endpoint=dict(optimization=calculation, frequency=calculation))))
