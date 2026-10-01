import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const src='/Users/cloudrayyy/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_wdx9ijs1uncp12_5ae6/temp/drag/Cloudra_省自科(2).pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(src));
await fs.writeFile('.deck-work/inspect.ndjson',(await p.inspect({kind:'slide,textbox,shape,image,layout',maxChars:500000})).ndjson);
for(let i=0;i<p.slides.items.length;i++) {try {const b=await p.slides.items[i].export({format:'png',scale:1});await fs.writeFile(`.deck-work/before-${i+1}.png`,new Uint8Array(await b.arrayBuffer()));console.log(i+1)}catch(e){console.log('ERR',i+1,e.message)}}
