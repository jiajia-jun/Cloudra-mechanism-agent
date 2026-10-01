import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_wdx9ijs1uncp12_5ae6/temp/RWTemp/2026-09/4300553b027ff358ce63514ee57c6af0/Cloudra答辩20页 2(1).pptx'));
await fs.writeFile('.codex-ppt-build/reference.ndjson',(await p.inspect({kind:'slide,textbox,shape,image',maxChars:500000})).ndjson);
for(let i=0;i<p.slides.items.length;i++) await fs.writeFile(`.codex-ppt-build/reference-${i+1}.png`,new Uint8Array(await (await p.slides.items[i].export({format:'png',scale:0.7})).arrayBuffer()));
console.log('reference slides',p.slides.items.length);
