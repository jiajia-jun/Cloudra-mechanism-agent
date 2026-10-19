"""Read-only repository audit; temporary inputs and outputs live below /tmp."""
# ruff: noqa: E402 -- initialize isolated config before importing Cloudra.


# Audit bootstrap: locate the checkout and keep generated files/configuration in /tmp.
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.dont_write_bytecode = True
_AUDIT_CONTEXT = Path(tempfile.mkdtemp(prefix="cloudra-audit-context-", dir="/tmp"))
os.environ["CLOUDRA_CONFIG_FILE"] = str(_AUDIT_CONTEXT / "absent.yaml")
os.environ["CLOUDRA_DATA_DIR"] = str(_AUDIT_CONTEXT / "runtime")
os.environ["CLOUDRA_DAEMON_WATCHDOG"] = "off"
os.chdir(_AUDIT_CONTEXT)

import asyncio
import json
import shutil
from tempfile import TemporaryDirectory

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import native_input_geometry
from cloudra.tools.core.molecule import read_molecule
from cloudra.tools.core.native_input_sections import gaussian_coordinate_units, gaussian_sections, orca_coordinate_units

CASES = [
    ('orca_angstrom', 'orca', '', None),
    ('orca_keyword_bohrs', 'orca', 'Bohrs', None),
    ('orca_inline_coords_bohrs', 'orca', '', '%coords Units Bohrs end'),
    ('orca_multiline_coords_bohrs', 'orca', '', '%coords\n Units Bohrs\nend'),
    ('orca_keyword_and_coords_bohrs', 'orca', 'Bohrs', '%coords Units Bohrs end'),
    ('orca_conflicting_units', 'orca', 'Bohrs', '%coords Units Angs end'),
    ('orca_unknown_units', 'orca', '', '%coords Units nonsense end'),
    ('gaussian_angstrom', 'gaussian', '', None),
    ('gaussian_units_bohr', 'gaussian', 'units=bohr', None),
    ('gaussian_units_parenthesized_bohr', 'gaussian', 'units=( bohr )', None),
    ('gaussian_units_au', 'gaussian', 'units=au', None),
    ('gaussian_conflicting_units', 'gaussian', 'units=bohr units=angstrom', None),
]

async def main():
    print(json.dumps({'binaries': {name: shutil.which(name) for name in ['orca', 'g16', 'g09']}}, ensure_ascii=False))
    with TemporaryDirectory(prefix='cloudra-unit-audit-', dir="/tmp") as directory:
        root = Path(directory)
        source = root / 'h2.xyz'
        source.write_text('2\nSource H-H distance is 1 Angstrom\nH 0 0 0\nH 1 0 0\n')
        for name, engine, keywords, blocks in CASES:
            target = root / (name + ('.gjf' if engine == 'gaussian' else '.inp'))
            request = QmInputWriter_input_schema(engine=engine, method='HF', basis_set='STO-3G',
                keywords=keywords, orca_blocks=blocks, source_type='xyz_file', source_value=str(source),
                output_path=str(target), charge=0)
            result = await QmInputWriter().tool_call(request, None)
            receipt = {'case': name, 'is_success': result.is_success, 'message': result.message,
                'unapplied_options': result.unapplied_options, 'warnings': result.warnings}
            if target.exists():
                content = target.read_text()
                receipt['validation_errors'] = QmInputWriter.validate_rendered_input(request, content, charge=0)
                receipt['detected_units'] = (orca_coordinate_units(content) if engine == 'orca' else
                    gaussian_coordinate_units(gaussian_sections(content)[0].route))
                try:
                    geometry = native_input_geometry(content, engine=engine)
                    molecule = read_molecule(input_path=target)
                    receipt['native_geometry_h2_x_angstrom'] = geometry[1][1][0]
                    receipt['read_molecule_h2_x_angstrom'] = molecule.GetConformer().GetAtomPosition(1).x
                except ValueError as error:
                    receipt['roundtrip_error'] = str(error)
            print(json.dumps(receipt, ensure_ascii=False))

asyncio.run(main())
