import {FileBlob,PresentationFile} from '@oai/artifact-tool';
try {const p=await PresentationFile.importPptx(await FileBlob.load('.deck-work/repaired.pptx'));console.log('pass',p.slides.items.length)}catch(e){console.log('ERROR',String(e).slice(-2500),e.stack?.slice(-1800))}
