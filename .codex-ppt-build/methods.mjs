import{FileBlob,PresentationFile}from'@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_LLM_Automated_Workflow.pptx'));
for(const n of ['remove','keep','reorder'])console.log(n,p.slides[n].toString().slice(0,4000));
console.log('slide',p.slides.items[0].id);
