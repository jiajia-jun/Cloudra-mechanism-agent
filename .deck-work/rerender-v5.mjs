import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('output/Cloudra_省自科_绿黄统一版.pptx'));
for(let i=0;i<p.slides.items.length;i++){const b=await p.slides.items[i].export({format:'png',scale:1});await fs.writeFile(`.deck-work/final-${i+1}.png`,new Uint8Array(await b.arrayBuffer()));console.log(i+1)}
