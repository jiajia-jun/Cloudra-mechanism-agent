import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_LLM_Automated_Workflow.pptx'));
await fs.writeFile('.codex-ppt-build/inspect.ndjson',(await p.inspect({kind:'slide,textbox,shape,image,table,layout',maxChars:500000})).ndjson);
for(let i=0;i<p.slides.items.length;i++) {
 const s=p.slides.items[i];
 try{const img=await s.export({format:'png',scale:0.7});await fs.writeFile(`.codex-ppt-build/source-${i+1}.png`,new Uint8Array(await img.arrayBuffer()));}catch(e){console.log('render',i+1,e.message)}
}
console.log('slides',p.slides.items.length);
console.log('slide methods',Object.getOwnPropertyNames(Object.getPrototypeOf(p.slides)));
console.log('shape methods',Object.getOwnPropertyNames(Object.getPrototypeOf(p.slides.items[0].shapes)));
