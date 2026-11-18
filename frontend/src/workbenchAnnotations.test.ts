import assert from 'node:assert/strict';
import test from 'node:test';
import { sceneAtoms, displayMarkers, cellEdges, markerLabel, atomImageLabel } from './workbenchAnnotations.ts';
import { detectImportFormat, workbenchLink } from './molecularWorkbench.ts';
import type { GeometryView } from './workbenchTypes.ts';

const geometry: GeometryView = {molecule:'', xyz:'', atoms:[{index:1,symbol:'Ag',x:1,y:2,z:3}], bonds:[],
  cell:[[4,1,0],[0,3,0],[0,0,12]], pbc:[true,true,false]};

test('a bridge keeps the original atom and image across a skew cell boundary', () => {
  const atoms = sceneAtoms(geometry,true);
  assert.equal(atoms.length,9);
  assert.equal(new Set(atoms.map(atom => atom.index)).size,9);
  const neighbor = atoms.find(atom => String(atom.image) === '1,0,0')!;
  assert.deepEqual([neighbor.x,neighbor.y,neighbor.z],[5,3,3]);
  assert.equal(atomImageLabel(neighbor),'Ag1 [1,0,0]');
  const [site] = displayMarkers([{label:'B',kind:'site',atoms:[{index:1,image:[0,0,0]},{index:1,image:neighbor.image}]}],geometry);
  assert.deepEqual(site.center,[3,2.5,3]);
  assert.equal(cellEdges(geometry.cell!).length,12);
  assert.equal(markerLabel(26),'AA');
  assert.equal(sceneAtoms(geometry,false).length,1);
});

test('workspace links accept local structures and leave external URLs as hyperlinks', () => {
  for (const file of ['POSCAR','CONTCAR','sample.vasp','sample.poscar']) assert.equal(detectImportFormat(file),'poscar');
  assert.equal(workbenchLink('outputs/test%20one.extxyz'),'outputs/test one.extxyz');
  assert.equal(workbenchLink('https://example.org/output.xyz'),null);
  assert.equal(workbenchLink('notes.md'),null);
});
