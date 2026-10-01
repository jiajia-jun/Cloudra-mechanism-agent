import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_十分钟答辩_研发新范式版.pptx'));
const rows=(await p.inspect({kind:'slide,textbox,shape,image',maxChars:400000})).ndjson;
await fs.writeFile('.codex-ppt-build/layout-source.ndjson',rows);
console.log(p.slides.items.length);
