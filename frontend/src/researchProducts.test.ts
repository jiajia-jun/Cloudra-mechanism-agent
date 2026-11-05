import assert from 'node:assert/strict';
import { groupProducts, productSource, filterProducts, associationOperation } from './researchProducts.ts';
import type { ResearchProduct } from './researchProducts.ts';
const base: ResearchProduct = {id:'a',kind:'artifact',title:'reactant.xyz',path:'same.xyz',state:'saved',can_open:true,associations:[],files:[]};
assert.deepEqual(productSource({...base,artifact_id:'snapshot'}),{artifact_id:'snapshot'});
assert.deepEqual(productSource({...base,kind:'calculation',path:'job/out.log'}),{path:'job/out.log'});
const associated = {...base,id:'b',associations:[{kind:'node' as const,id:'n1',label:'A',ref_type:'file',ref_id:'same.xyz'}]};
assert.equal(filterProducts([base,associated],{kind:'node',id:'n1'},'').length,1);
assert.equal(filterProducts([base,associated],null,'reactant').length,2);
const groups=groupProducts([base,associated]);
assert.equal(groups.length,2);
assert.equal(groups.find(g=>g.key==='node:n1')?.products.length,1);
assert.equal(groups.find(g=>g.key==='node:n1')?.products[0].id,'b');
assert.ok(groups.some(g=>g.label.includes('未关联')));
assert.equal(groupProducts([{...base,id:'a',job_id:'j'}, {...base,id:'b',job_id:'j'}]).length,1);
assert.equal(filterProducts([{...base,title:'n1 is only a filename'}],{kind:'node',id:'n1'},'').length,0);
console.log('research product association and routing passed');

assert.deepEqual(associationOperation({...base,artifact_id:'original-snapshot',association_ref:{ref_type:'artifact',ref_id:'original-snapshot',content_hash:'program-sha256'}},{kind:'edge',id:'e2'}),{
  op:'attach_ref',graph:'delivery',target_type:'edge',target_id:'e2',ref:{ref_type:'artifact',ref_id:'original-snapshot',content_hash:'program-sha256'}
});
assert.deepEqual(associationOperation({...base,job_id:'parent-job',association_ref:{ref_type:'compute_job',ref_id:'parent-job'}},{kind:'node',id:'n2'}),{
  op:'attach_ref',graph:'delivery',target_type:'node',target_id:'n2',ref:{ref_type:'compute_job',ref_id:'parent-job'}
});
const canonicalFileRef={ref_type:'file' as const,ref_id:'registered-file-evidence-id',content_hash:'registered-file-sha'};
assert.equal(associationOperation({...base,association_ref:canonicalFileRef},{kind:'node',id:'n2'}).ref,canonicalFileRef);
assert.throws(()=>associationOperation(base,{kind:'node',id:'n2'}));
