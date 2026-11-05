import assert from 'node:assert/strict';
import { toRenderAtoms, initializeRenderModel, fitProjectedScale, validModeDisplacements, parseXyz } from './moleculeRendering.ts';
const atoms=[{index:3,symbol:'C',x:0,y:0,z:0},{index:8,symbol:'O',x:1.2,y:0,z:0},{index:11,symbol:'H',x:1.7,y:1,z:0}];
const rendered=toRenderAtoms(atoms,[{atom1:3,atom2:8,order:2}]);
assert.deepEqual(rendered.map(a=>a.serial),[3,8,11]);
assert.deepEqual(rendered[0].bonds,[1]);
assert.deepEqual(rendered[1].bonds,[0]);
assert.deepEqual(rendered[0].bondOrder,[2]);
assert.deepEqual(rendered[2].bonds,[]);
assert.deepEqual(toRenderAtoms(atoms,[]).map(a=>a.bonds),[[],[],[]]);
const vectors=[[1,0,0],[0,-2,0],[0,0,3]];
assert.equal(validModeDisplacements(atoms,vectors),true);
assert.equal(validModeDisplacements(atoms,[[1,0,0]]),false);
const vibrating=toRenderAtoms(atoms,[],vectors);
assert.equal(vibrating[1].dy,-2);
assert.equal(vibrating[2].dz,3);
assert.equal(vibrating[1].y,atoms[1].y);
assert.deepEqual(toRenderAtoms(atoms,[]).map(a=>a.dx),[undefined,undefined,undefined]);
assert.deepEqual(parseXyz('2\nwater fragment\nO 0 0 0\nH 0.9 0 0').map(a=>a.index),[0,1]);
assert.throws(()=>toRenderAtoms(atoms,[{atom1:3,atom2:99,order:1}]));
console.log('molecular WebGL topology, numbering and real modes passed');

// Exercise the actual library's addAtoms -> vibrate path without constructing WebGL.
Object.assign(globalThis,{window:{navigator:{userAgent:''}},document:{}});
const {GLModel}=await import('3dmol/build/3Dmol.es6-min.js');
const realModel=new GLModel(0);
initializeRenderModel(realModel,toRenderAtoms(atoms,[{atom1:3,atom2:8,order:2}],vectors));
assert.equal(realModel.getNumFrames(),1);
assert.doesNotThrow(()=>realModel.vibrate(20,0.7,true));
await realModel.setFrame(20);
assert.deepEqual(realModel.selectedAtoms({}).map(atom=>[atom.x,atom.y,atom.z]),atoms.map(atom=>[atom.x,atom.y,atom.z]));
assert.deepEqual(realModel.selectedAtoms({})[0].bondOrder,[2]);

assert.equal(fitProjectedScale([{x:0,y:0},{x:200,y:130}],900,600,0.6),2.7);
assert.equal(fitProjectedScale([{x:0,y:0},{x:1800,y:300}],900,600,0.6),0.3);
