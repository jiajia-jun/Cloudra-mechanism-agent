"""Explicit scientific declarations shared by TS regression fixtures."""
from cloudra.tools.core.ts_inputs import TsInput


def calculation_input(*, reactant_smiles, product_smiles, method, basis_set=None, charge=0,
                      multiplicity=1, engine='orca', keywords='',
                      reaction_center=(), atom_map=(), ring_order=(),
                      distance_filters=(), product_geometry=None,
                      path_solvation=None, irc_log=None, scan=None):
    # Concise descriptors remain a test-data convenience, never a public tool grammar.
    if basis_set is None:
        method, separator, basis_set = method.partition('/')
        if not separator:
            basis_set = ''
    calculation = dict(engine=engine, method=method, basis_set=basis_set, keywords=keywords)
    generate = dict(kind='generate', generation='ETKDGv3', seed=42)
    guess = dict(kind='xtb_path', method='GFN2-xTB', solvation=path_solvation)
    if scan is not None:
        scan_method = scan['method']
        scan_basis = scan.get('basis_set')
        if scan_basis is None:
            scan_method, separator, scan_basis = scan_method.partition('/')
            if not separator:
                scan_basis = ''
        guess = dict(kind='scan', calculation=dict(engine=engine, method=scan_method, basis_set=scan_basis, keywords=scan.get('keywords', '')),
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
