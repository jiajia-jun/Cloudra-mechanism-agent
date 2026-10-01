import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const path='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/output/Cloudra_研发新范式版_仅排版修订_交付.pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(path));
for(let i=0;i<p.slides.items.length;i++)await fs.writeFile(`.codex-ppt-build/layout-delivery-verified-${i+1}.png`,new Uint8Array(await (await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
console.log('Exact final file rendered:',p.slides.items.length);
