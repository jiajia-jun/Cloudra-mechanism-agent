"""Explicit scientific declarations shared by TS regression fixtures."""
from cloudra.tools.core.ts_inputs import TsInput


def native_qm_log(engine, symbols, positions, *, optimization=True, normal=True, frequencies=None):
    """Synthetic native excerpts with explicit, independently testable facts."""
    if engine == 'gaussian':
        from cclib.parser.utils import PeriodicTable

        table = PeriodicTable()
        lines = ['Entering Gaussian System', ' # opt' if optimization is not None else ' # freq',
            ' Standard orientation:', ' -----', ' Center Atomic Atomic Coordinates',
            ' Number Number Type X Y Z', ' -----']
        lines.extend(f' {index} {table.number[symbol]} 0 {point[0]:.8f} {point[1]:.8f} {point[2]:.8f}'
            for index, (symbol, point) in enumerate(zip(symbols, positions, strict=True), 1))
        lines.append(' -----')
        if optimization is not None:
            lines.append('Optimization completed.' if optimization else 'Optimization stopped.')
        if frequencies is not None:
            lines.extend(['Harmonic frequencies', ' Frequencies -- ' + ' '.join(map(str, frequencies))])
        lines.append('Normal termination' if normal else 'Error termination via Lnk1e')
    else:
        lines = ['O   R   C   A', '! Opt' if optimization is not None else '! Freq',
            'CARTESIAN COORDINATES (ANGSTROEM)', '-----']
        lines.extend(f'{symbol} {point[0]:.8f} {point[1]:.8f} {point[2]:.8f}'
            for symbol, point in zip(symbols, positions, strict=True))
        lines.append('')
        if optimization is not None:
            lines.append('THE OPTIMIZATION HAS CONVERGED' if optimization else 'The optimization did not converge')
        if frequencies is not None:
            lines.append('VIBRATIONAL FREQUENCIES')
            lines.extend(f'{index}: {value} cm**-1' for index, value in enumerate(frequencies))
            lines.append('')
        lines.append('ORCA TERMINATED NORMALLY' if normal else 'ORCA finished by error termination in FREQ')
    return '\n'.join(lines) + '\n'


def calculation_input(*, reactant_smiles, product_smiles, method, basis_set=None, charge=0,
                      multiplicity=1, engine='orca', keywords='',
                      reaction_center=(), selected_candidate=None, ring_order=(),
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
                      reaction_center=list(reaction_center), selected_candidate=selected_candidate),
        conformers=dict(reactant=generate, product=product_geometry or generate,
                        guidance=dict(ring_order=list(ring_order), distance_filters=list(distance_filters))),
        guess=guess, ts_optimization=calculation,
        verification=dict(frequency=calculation, irc=calculation, irc_log=irc_log,
            reactant_endpoint=dict(optimization=calculation, frequency=calculation),
            product_endpoint=dict(optimization=calculation, frequency=calculation))))
