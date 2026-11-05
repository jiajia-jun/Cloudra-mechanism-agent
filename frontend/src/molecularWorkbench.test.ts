import assert from 'node:assert/strict';
import { toggleAtomSelection, selectionAfterEdit, measureCoordinate, curvePoints, defineFrozenCoordinate, detectImportFormat, validateSettings, applyGeometry, draftFromFrame, undoDraft } from './molecularWorkbench.ts';
const atoms = [
  { index: 1, symbol: 'C', x: 1, y: 0, z: 0 },
  { index: 2, symbol: 'C', x: 0, y: 0, z: 0 },
  { index: 3, symbol: 'C', x: 0, y: 1, z: 0 },
  { index: 4, symbol: 'H', x: 0, y: 1, z: 1 },
];
assert.deepEqual(toggleAtomSelection([3, 1], 3), [1]);
assert.deepEqual(toggleAtomSelection([3, 1], 2), [3, 1, 2]);
assert.equal(measureCoordinate(atoms, [1, 2]), 1);
assert.equal(measureCoordinate(atoms, [1, 2, 3]), 90);
assert.equal(measureCoordinate(atoms, [1, 2, 3, 4]), -90);
assert.equal(measureCoordinate(atoms, [1, 1]), null);
assert.deepEqual(curvePoints([{ index: 0, step: 1 }, { index: 1, step: 2, energy_hartree: -5 }, { index: 2, step: 3, energy_hartree: -4 }], 'energy_hartree').map(p => p.frame), [1, 2]);
assert.ok(validateSettings({}, true));
assert.equal(validateSettings({}, false), null);
assert.equal(validateSettings({ engine: 'gaussian', method: 'B3LYP', basis_set: '6-31G', charge: 0, multiplicity: 1 }, true), null);
const geometry = { molecule: 'native-old', xyz: '', atoms, bonds: [] };
const previous = { geometry, settings: { method: 'chosen' }, sourcePath: 'calc.log', sourceFrame: 3, frozen: [{ coord_type: 'bond' as const, atoms: [1, 2], value: 1 }], scans: [{ coord_type: 'bond' as const, atoms: [3, 4], scan_start: 1, scan_end: 2, scan_steps: 5 }] };
const edited = applyGeometry(previous, { ...geometry, molecule: 'native-new', changes: { deleted_atoms: [2], index_map: { '1': 1, '3': 2, '4': 3 }, deleted_atom_ids: [], moved_atoms: [] } });
// A deleted selected atom must not become the surviving atom that took its index.
assert.deepEqual(selectionAfterEdit([1, 2, 4], edited.draft.geometry.changes), [1, 3]);
assert.deepEqual(selectionAfterEdit([3, 1]), [3, 1]);
assert.equal(edited.draft.sourceFrame, 3);
assert.equal(edited.draft.frozen.length, 0);
assert.deepEqual(edited.draft.scans[0].atoms, [2, 3]);
assert.equal(edited.invalidated, 1);
const restored = undoDraft([previous], edited.draft);
assert.equal(restored.draft.geometry.molecule, 'native-old');
assert.equal(restored.draft.sourceFrame, 3);
assert.equal(restored.draft.settings.method, 'chosen');
console.log('molecular workbench behavior passed');

assert.deepEqual(curvePoints([{index:0,step:1,energy_hartree:-2,reaction_coordinate:-1},{index:1,step:2,energy_hartree:-1}], 'energy_hartree').map(p=>p.x), [0,1]);
assert.equal(validateSettings({engine:'orca',method:'chosen',basis_set:'',charge:0,multiplicity:0},true), '电荷须为整数，多重度须为正整数。');
assert.equal(undoDraft([], previous).draft, previous);

const newBranch = draftFromFrame(edited.draft, geometry, 'calc.log', 1);
assert.equal(newBranch.sourceFrame, 1);
assert.deepEqual(newBranch.scans, []);
assert.deepEqual(draftFromFrame(previous, geometry, 'calc.log', 1).scans, previous.scans);

// A native scan slice keeps real coordinate values and original document frame IDs.
const scanSlice = [
  {index:0,step:0,energy_hartree:-10,scan_coordinates:[1.1,10]},
  {index:1,step:1,energy_hartree:null,scan_coordinates:[1.1,20]},
  {index:2,step:2,energy_hartree:-11,scan_coordinates:[1.6,10]},
].map(frame=>({...frame,reaction_coordinate:frame.scan_coordinates[1]===10?frame.scan_coordinates[0]:undefined}));
assert.deepEqual(curvePoints(scanSlice,'energy_hartree').map(p=>[p.frame,p.x]),[[0,1.1],[2,1.6]]);

const frozenTarget = defineFrozenCoordinate(previous,[1,2],'1.7');
assert.equal(frozenTarget.geometry, previous.geometry);
assert.equal(frozenTarget.geometry.molecule, 'native-old');
assert.equal(frozenTarget.frozen[0].value,1.7);
assert.equal(frozenTarget.frozen.length,1);
assert.equal(frozenTarget.sourceFrame,3);
assert.equal(defineFrozenCoordinate(previous,[1,2],'').frozen[0].value,1);
assert.equal(previous.frozen[0].value,1);
for (const suffix of ['log','out','gjf','com','inp','pdb','cif']) assert.equal(detectImportFormat(`calculation.${suffix.toUpperCase()}`),suffix);
assert.equal(detectImportFormat('fragment.smi'),'smiles');
assert.equal(detectImportFormat('unknown.zip'),null);
