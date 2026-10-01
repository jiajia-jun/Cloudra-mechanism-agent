import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('.deck-work/roundtrip.pptx'));
console.log('remove',p.slides.remove.toString());console.log('delete',p.slides.items[0].shapes.deleteById.toString());console.log('images delete',Object.getOwnPropertyNames(Object.getPrototypeOf(p.slides.items[0].images)));
console.log('shape',p.slides.items[0].shapes.items[0].id,p.slides.items[0].id);
const b=await p.slides.items[2].export({format:'png',scale:1});await (await import('node:fs/promises')).writeFile('.deck-work/roundtrip3.png',new Uint8Array(await b.arrayBuffer()));
